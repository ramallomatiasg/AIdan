"""
train_confidence_model.py — Entrena modelo de confidence empírico (Fase A).

v2 (23 May): cambio de Logistic Regression -> Random Forest.
Razon: experimento compare_models.py mostro que LR (lineal) capta AUC 0.48
(peor que random). RF/GB no-lineales captan AUC 0.54-0.56. El problema NO
era de data sino de algoritmo.

Features (todas disponibles en trade_archive):
- Categoricas (one-hot): trigger_type, session, htf_bias, direction, market_trend,
  trend_strength, volatility
- Numericas: rsi_at_entry, avg_range_pips, hour_utc, day_of_week
- Enriched (de enrich_archive_features.py): velocity_5c/10c, body_atr_ratio,
  dist_prev_high/low, mins_since_high_impact_news

Target: result IN ('win', 'loss') -> binary (1 = win)

Validation: walk-forward chronological (no random shuffle).
Compara Brier + AUC: RF nuevo vs LR vs confidence vieja.

Output:
- config/confidence_model.joblib (modelo RF + scaler + feature names)
- config/confidence_weights.json (legacy metadata + metrics)
- Reporte en consola con: Brier/AUC scores, feature importance, calibration

Uso:
    python tools/train_confidence_model.py                  # full training
    python tools/train_confidence_model.py --model rf       # default
    python tools/train_confidence_model.py --model lr       # legacy
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'financial_news.db')
OUTPUT_DEFAULT = ROOT / 'config' / 'confidence_weights.json'


# Categorical features con sus valores conocidos (one-hot)
CATEGORICAL_FEATURES = {
    'trigger_type': ['structure', 'm15_structure', 'h1_structure', 'news', 'smc', 'pre_planned'],
    'session': ['london', 'ny', 'late_ny', 'overlap', 'asia', 'off'],
    'htf_bias': ['bullish', 'bearish', 'neutral'],
    'direction': ['CALL', 'PUT'],
    'market_trend': ['bullish', 'bearish', 'neutral'],
    'trend_strength': ['strong', 'moderate', 'weak'],
    'volatility': ['high', 'normal', 'low'],
}

NUMERIC_FEATURES = ['rsi_at_entry', 'avg_range_pips', 'hour_utc', 'day_of_week']

# v3.33.0 — Features predictivos adicionales (de enrich_archive_features.py)
# Si el CSV existe, se cargan estos features adicionales (Fase B validation).
ENRICHED_FEATURES = [
    # V1 sabado
    'velocity_5c_aligned', 'velocity_10c_aligned',  # momentum reciente alineado a direction
    'body_atr_ratio',                                # fuerza de la vela de entry
    'dist_prev_high_pips', 'dist_prev_low_pips',    # multi-day structure
    'mins_since_high_impact_news',                   # tiempo desde news high-impact
    # V2 domingo
    'volume_zscore',                                 # tick_volume vs media reciente
    'multi_tf_score',                                # alineacion M5+M15+H1+H4 (0-4)
    'dist_round_pips',                               # dist a numero redondo
    'dist_5d_high_pips', 'dist_5d_low_pips',        # rango semanal
    'spread_entry_pips',                             # fricción al entrar
]
ENRICHED_CSV = 'trade_archive_enriched.csv'

# Confidence VIEJA (para benchmarking)
OLD_CONF_FEATURE = 'confidence'


def load_data():
    """Load trade_archive con todos los features completos.
    Si existe enriched CSV, hace merge con features adicionales."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    sql = """
        SELECT id as trade_id, direction, result, mt5_pnl,
               confidence, trigger_type, setup_type,
               htf_bias, session, hour_utc, day_of_week,
               rsi_at_entry, avg_range_pips, market_trend,
               trend_strength, volatility, created_at
        FROM trade_archive
        WHERE result IN ('win', 'loss') AND mt5_pnl IS NOT NULL
          AND confidence IS NOT NULL AND trigger_type IS NOT NULL
          AND direction IS NOT NULL
        ORDER BY created_at ASC
    """
    df = pd.read_sql_query(sql, conn)
    conn.close()

    # Merge enriched features if available
    enriched_path = ROOT / ENRICHED_CSV
    if enriched_path.exists():
        enriched = pd.read_csv(enriched_path)
        df = df.merge(enriched, on='trade_id', how='left')
        print(f"  Merged enriched features from {enriched_path.name}")
    else:
        print(f"  (No enriched CSV found at {enriched_path}, training with base features only)")
    return df


def engineer_features(df):
    """Convert categoricals to one-hot, fill missing values."""
    X = pd.DataFrame(index=df.index)

    # Categóricas: one-hot encoding
    for col, levels in CATEGORICAL_FEATURES.items():
        for level in levels:
            X[f'{col}__{level}'] = (df[col].fillna('') == level).astype(int)

    # Numéricas: fillna con mediana, no scaling todavía (lo hace el scaler después)
    for col in NUMERIC_FEATURES:
        median = df[col].median()
        X[col] = df[col].fillna(median if pd.notna(median) else 0).astype(float)

    # v3.33.0 — Enriched features (si disponibles)
    enriched_added = []
    for col in ENRICHED_FEATURES:
        if col in df.columns:
            median = df[col].median()
            X[col] = df[col].fillna(median if pd.notna(median) else 0).astype(float)
            enriched_added.append(col)
    if enriched_added:
        print(f"  Enriched features incluidos ({len(enriched_added)}): {', '.join(enriched_added)}")

    # Target
    y = (df['result'] == 'win').astype(int).values

    return X, y, df['confidence'].values


def walk_forward_split(X, y, test_frac=0.20):
    """Chronological split: primer 1-test_frac para train, último test_frac para eval."""
    n = len(X)
    split = int(n * (1 - test_frac))
    return (X.iloc[:split], y[:split]), (X.iloc[split:], y[split:])


def train_model(X_train, y_train, model_type='rf'):
    """Train modelo segun model_type:
    - 'rf': Random Forest depth=3 (default v2, AUC 0.54 confirmed)
    - 'rf_deep': Random Forest depth=8 (AUC 0.56 pero mas overfit)
    - 'lr': Logistic Regression (legacy, AUC 0.48)
    """
    if model_type == 'lr':
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_train)
        model = LogisticRegression(C=0.5, max_iter=1000, random_state=42, solver='lbfgs')
        model.fit(X_scaled, y_train)
        return model, scaler
    elif model_type == 'rf_deep':
        # No scaling needed for tree models
        model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1, class_weight='balanced')
        model.fit(X_train, y_train)
        return model, None
    else:  # 'rf' default
        # Modelo sano: depth limitado para evitar memorize, balanced para WR 37%
        model = RandomForestClassifier(
            n_estimators=100, max_depth=4, min_samples_leaf=10,
            random_state=42, n_jobs=-1, class_weight='balanced'
        )
        model.fit(X_train, y_train)
        return model, None


def benchmark_old_confidence(confidence_old, y):
    """La conf vieja es 0-100. Para Brier necesitamos P(win) ∈ [0,1].
    Asumimos calibración lineal: P = conf / 100. Esto es lo más generoso para la vieja."""
    p_old = np.clip(confidence_old / 100.0, 0.001, 0.999)
    return {
        'brier': brier_score_loss(y, p_old),
        'log_loss': log_loss(y, p_old),
        'auc': roc_auc_score(y, p_old) if len(np.unique(y)) > 1 else 0.5,
    }


def evaluate_model(model, scaler, X, y):
    """Compute metrics on a dataset. Scaler optional (None for tree models)."""
    X_use = scaler.transform(X) if scaler is not None else X
    p_pred = model.predict_proba(X_use)[:, 1]
    return {
        'brier': brier_score_loss(y, p_pred),
        'log_loss': log_loss(y, p_pred),
        'auc': roc_auc_score(y, p_pred) if len(np.unique(y)) > 1 else 0.5,
    }, p_pred


def calibration_curve(y, p, n_buckets=10):
    """Compute calibration: P(win) predicho vs observado por bucket."""
    buckets = []
    edges = np.linspace(0, 1, n_buckets + 1)
    for i in range(n_buckets):
        mask = (p >= edges[i]) & (p < edges[i+1])
        if mask.sum() == 0:
            continue
        buckets.append({
            'range': (round(edges[i], 2), round(edges[i+1], 2)),
            'n': int(mask.sum()),
            'mean_pred': round(float(p[mask].mean()), 3),
            'actual_wr': round(float(y[mask].mean()), 3),
        })
    return buckets


def feature_importance(model, feature_names):
    """Return features ranked by importance.
    LR uses coef_, RF/GB use feature_importances_."""
    if hasattr(model, 'feature_importances_'):
        # Tree-based models
        importances = model.feature_importances_
        items = [(name, float(importances[i])) for i, name in enumerate(feature_names)]
    else:
        # Linear (logistic regression)
        coefs = model.coef_[0]
        items = [(name, float(coefs[i])) for i, name in enumerate(feature_names)]
    items.sort(key=lambda x: abs(x[1]), reverse=True)
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(OUTPUT_DEFAULT))
    parser.add_argument('--test-frac', type=float, default=0.20)
    parser.add_argument('--model', default='rf', choices=['rf', 'rf_deep', 'lr'],
                        help='Modelo: rf (default), rf_deep, lr (legacy)')
    args = parser.parse_args()

    print("=" * 70)
    print(f"TRAIN CONFIDENCE MODEL ({args.model}) — {datetime.now()}")
    print("=" * 70)

    # 1. Load data
    df = load_data()
    print(f"\nTrades cargados: {len(df)}")
    if len(df) < 100:
        print("ERROR: muestra muy chica para training.")
        sys.exit(1)

    # 2. Features + target
    X, y, conf_old = engineer_features(df)
    n_features = X.shape[1]
    print(f"Features: {n_features} (categóricas one-hot + numéricas)")
    print(f"Target distribution: {y.sum()} wins / {len(y)} total (WR {y.mean()*100:.1f}%)")

    # 3. Walk-forward split (chronological)
    (X_train, y_train), (X_test, y_test) = walk_forward_split(X, y, args.test_frac)
    print(f"\nWalk-forward split: train={len(X_train)} | test={len(X_test)}")

    # 4. Train model
    model_descriptions = {
        'rf': 'Random Forest (100 trees, depth=4, balanced)',
        'rf_deep': 'Random Forest (200 trees, depth=8)',
        'lr': 'Logistic Regression (C=0.5, L2)',
    }
    print(f"\nEntrenando {model_descriptions[args.model]}...")
    model, scaler = train_model(X_train, y_train, model_type=args.model)

    # 5. Evaluate train + test
    train_metrics, p_train = evaluate_model(model, scaler, X_train, y_train)
    test_metrics, p_test = evaluate_model(model, scaler, X_test, y_test)

    # 6. Benchmark contra conf vieja
    n_train = len(X_train)
    conf_old_train = conf_old[:n_train]
    conf_old_test = conf_old[n_train:]
    old_train_metrics = benchmark_old_confidence(conf_old_train, y_train)
    old_test_metrics = benchmark_old_confidence(conf_old_test, y_test)

    print("\n=== METRICS (lower Brier = better; higher AUC = better) ===")
    print(f"{'Metric':>12s} {'NEW (train)':>14s} {'NEW (test)':>14s} {'OLD (train)':>14s} {'OLD (test)':>14s}")
    print(f"{'Brier':>12s} {train_metrics['brier']:>14.4f} {test_metrics['brier']:>14.4f} {old_train_metrics['brier']:>14.4f} {old_test_metrics['brier']:>14.4f}")
    print(f"{'LogLoss':>12s} {train_metrics['log_loss']:>14.4f} {test_metrics['log_loss']:>14.4f} {old_train_metrics['log_loss']:>14.4f} {old_test_metrics['log_loss']:>14.4f}")
    print(f"{'AUC-ROC':>12s} {train_metrics['auc']:>14.4f} {test_metrics['auc']:>14.4f} {old_train_metrics['auc']:>14.4f} {old_test_metrics['auc']:>14.4f}")

    improvement = old_test_metrics['brier'] - test_metrics['brier']
    print(f"\nMejora Brier (test): {improvement:+.4f}  ({'mejor' if improvement > 0 else 'peor'} que conf vieja)")

    # 7. Calibration curve (test set)
    print("\n=== CALIBRATION CURVE (test set, modelo NUEVO) ===")
    print(f"{'P-bucket':>15s} {'n':>4s} {'mean P':>8s} {'actual WR':>10s}")
    for b in calibration_curve(y_test, p_test, n_buckets=10):
        print(f"  [{b['range'][0]:.2f}-{b['range'][1]:.2f})  {b['n']:>4d} {b['mean_pred']:>8.3f} {b['actual_wr']:>10.3f}")

    # 8. Feature importance
    print("\n=== TOP 15 FEATURES por importancia (|coef|) ===")
    importance = feature_importance(model, X.columns.tolist())
    for name, coef in importance[:15]:
        direction = 'win' if coef > 0 else 'loss'
        print(f"  {name:35s} coef={coef:+.3f}  predicts {direction}")

    # 9. Persistir modelo + metadata
    # JSON solo con metadata (modelo binario va en joblib)
    metadata = {
        'version': '2.0',
        'model_type': args.model,
        'trained_at': datetime.now().isoformat(),
        'n_train': len(X_train),
        'n_test': len(X_test),
        'features': X.columns.tolist(),
        'n_features': n_features,
        'metrics': {
            'brier_train': train_metrics['brier'],
            'brier_test': test_metrics['brier'],
            'auc_train': train_metrics['auc'],
            'auc_test': test_metrics['auc'],
            'old_brier_test': old_test_metrics['brier'],
            'old_auc_test': old_test_metrics['auc'],
            'improvement_brier': improvement,
            'improvement_auc': test_metrics['auc'] - old_test_metrics['auc'],
        },
        'categorical_features': CATEGORICAL_FEATURES,
        'numeric_features': NUMERIC_FEATURES,
        'enriched_features': [c for c in ENRICHED_FEATURES if c in X.columns],
        'top_features': [
            {'name': name, 'importance': round(coef, 4)}
            for name, coef in importance[:20]
        ],
    }

    # JSON metadata
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, default=str)

    # Modelo binario en joblib (sklearn-native, mas robusto)
    joblib_path = output_path.parent / 'confidence_model.joblib'
    joblib.dump({
        'model': model,
        'scaler': scaler,  # None for tree models
        'features': X.columns.tolist(),
        'model_type': args.model,
        'trained_at': metadata['trained_at'],
    }, joblib_path)

    print(f"\nMetadata: {output_path} ({os.path.getsize(output_path)} bytes)")
    print(f"Modelo:   {joblib_path} ({os.path.getsize(joblib_path)} bytes)")

    # Veredicto
    print("\n" + "=" * 70)
    if improvement > 0.01:
        print(f"✓ MODELO NUEVO MEJORA Brier {improvement:.4f} vs heurística. Candidato para Fase A.")
    elif improvement > 0:
        print(f"~ Modelo nuevo apenas mejora ({improvement:.4f}). Sample chica, considerar más features.")
    else:
        print(f"✗ Modelo nuevo NO mejora vs heurística. Brier {test_metrics['brier']:.4f} vs {old_test_metrics['brier']:.4f}.")
    print("=" * 70)


if __name__ == '__main__':
    main()
