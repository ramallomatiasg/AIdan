"""
compare_models.py — Compara modelos no-lineales vs logistic regression
sobre los features que ya tenemos (Base + Enriched).

Razón: Fase A (logistic regression) dio AUC 0.48 (peor que random).
Hipótesis: el problema puede ser NO LINEAL. Probamos Random Forest y
Gradient Boosting (XGBoost si disponible) que capturan no-linealidades.

Si algún modelo no-lineal sube AUC a >0.55, vale la pena seguir con él
en Fase A real. Si ninguno sube, confirma que el problema NO es algoritmo
sino DATA.

Uso:
    python tools/compare_models.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'financial_news.db')

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
ENRICHED_FEATURES = [
    'velocity_5c_aligned', 'velocity_10c_aligned', 'body_atr_ratio',
    'dist_prev_high_pips', 'dist_prev_low_pips', 'mins_since_high_impact_news',
]


def load_data():
    conn = sqlite3.connect(DB_PATH)
    sql = """
        SELECT id as trade_id, direction, result, mt5_pnl, confidence,
               trigger_type, htf_bias, session, hour_utc, day_of_week,
               rsi_at_entry, avg_range_pips, market_trend, trend_strength,
               volatility, created_at
        FROM trade_archive
        WHERE result IN ('win', 'loss') AND mt5_pnl IS NOT NULL
          AND confidence IS NOT NULL AND trigger_type IS NOT NULL
        ORDER BY created_at ASC
    """
    df = pd.read_sql_query(sql, conn)
    conn.close()
    enriched_path = ROOT / 'trade_archive_enriched.csv'
    if enriched_path.exists():
        enriched = pd.read_csv(enriched_path)
        df = df.merge(enriched, on='trade_id', how='left')
    return df


def engineer_features(df):
    X = pd.DataFrame(index=df.index)
    for col, levels in CATEGORICAL_FEATURES.items():
        for level in levels:
            X[f'{col}__{level}'] = (df[col].fillna('') == level).astype(int)
    for col in NUMERIC_FEATURES:
        median = df[col].median()
        X[col] = df[col].fillna(median if pd.notna(median) else 0).astype(float)
    for col in ENRICHED_FEATURES:
        if col in df.columns:
            median = df[col].median()
            X[col] = df[col].fillna(median if pd.notna(median) else 0).astype(float)
    y = (df['result'] == 'win').astype(int).values
    return X, y


def evaluate(model, X_train, y_train, X_test, y_test, needs_scaling=False):
    if needs_scaling:
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)
    else:
        X_train_s = X_train
        X_test_s = X_test
    model.fit(X_train_s, y_train)
    p_train = model.predict_proba(X_train_s)[:, 1]
    p_test = model.predict_proba(X_test_s)[:, 1]
    return {
        'brier_train': brier_score_loss(y_train, p_train),
        'brier_test': brier_score_loss(y_test, p_test),
        'auc_train': roc_auc_score(y_train, p_train) if len(np.unique(y_train)) > 1 else 0.5,
        'auc_test': roc_auc_score(y_test, p_test) if len(np.unique(y_test)) > 1 else 0.5,
        'log_loss_test': log_loss(y_test, np.clip(p_test, 0.001, 0.999)),
    }


def main():
    print("=" * 75)
    print(f"COMPARE MODELS — {datetime.now()}")
    print("=" * 75)

    df = load_data()
    print(f"\nTrades: {len(df)}")
    X, y = engineer_features(df)
    print(f"Features: {X.shape[1]}")

    # Walk-forward split
    n = len(X)
    split = int(n * 0.80)
    X_train, y_train = X.iloc[:split], y[:split]
    X_test, y_test = X.iloc[split:], y[split:]
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")

    # Definir modelos
    models = {
        'LogisticRegression (C=0.5)': (LogisticRegression(C=0.5, max_iter=1000, random_state=42, solver='lbfgs'), True),
        'LogisticRegression (C=1.0)': (LogisticRegression(C=1.0, max_iter=1000, random_state=42, solver='lbfgs'), True),
        'LogisticRegression (C=0.1)': (LogisticRegression(C=0.1, max_iter=1000, random_state=42, solver='lbfgs'), True),
        'RandomForest (100 trees)': (RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1), False),
        'RandomForest (200 trees, depth=8)': (RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1), False),
        'RandomForest (50 trees, depth=3)': (RandomForestClassifier(n_estimators=50, max_depth=3, random_state=42, n_jobs=-1), False),
        'GradientBoosting (default)': (GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42), False),
        'GradientBoosting (slow learner)': (GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42), False),
    }

    # XGBoost si disponible
    try:
        import xgboost as xgb
        models['XGBoost (100, depth=3)'] = (xgb.XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42, eval_metric='logloss', use_label_encoder=False), False)
        models['XGBoost (200, depth=5)'] = (xgb.XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.05, random_state=42, eval_metric='logloss', use_label_encoder=False), False)
    except ImportError:
        print("(XGBoost no instalado, saltando)")

    # Train + eval
    print(f"\n{'Model':<40s} {'Brier(tr)':>10s} {'Brier(te)':>10s} {'AUC(tr)':>9s} {'AUC(te)':>9s} {'overfitting':>12s}")
    print("-" * 100)

    results = []
    for name, (model, needs_scaling) in models.items():
        try:
            m = evaluate(model, X_train, y_train, X_test, y_test, needs_scaling)
            overfit = m['auc_train'] - m['auc_test']
            results.append({'name': name, **m, 'overfit': overfit})
            print(f"  {name:<38s} {m['brier_train']:>10.4f} {m['brier_test']:>10.4f} {m['auc_train']:>9.4f} {m['auc_test']:>9.4f} {overfit:>+11.3f}")
        except Exception as e:
            print(f"  {name:<38s} FAILED: {e}")

    # Best by AUC test
    print("\n" + "=" * 75)
    results.sort(key=lambda r: -r['auc_test'])
    best = results[0]
    print(f"BEST AUC TEST: {best['name']}")
    print(f"  AUC test: {best['auc_test']:.4f}")
    print(f"  Brier test: {best['brier_test']:.4f}")
    print(f"  Overfitting (train-test gap): {best['overfit']:+.4f}")

    print("\n--- Top 3 by AUC test ---")
    for r in results[:3]:
        print(f"  {r['name']:<40s} AUC={r['auc_test']:.4f}  Brier={r['brier_test']:.4f}  overfit={r['overfit']:+.3f}")

    # Veredicto
    print("\n" + "=" * 75)
    if best['auc_test'] > 0.60:
        print(f"✓✓ ALGUN MODELO LLEGA A AUC > 0.60. Vale la pena continuar con {best['name']}.")
    elif best['auc_test'] > 0.55:
        print(f"~ Best AUC = {best['auc_test']:.3f}. Mejora modesta, considerar combinación con más features.")
    elif best['auc_test'] > 0.50:
        print(f"~ Best AUC = {best['auc_test']:.3f}. Apenas mejor que random. Necesita más features o features distintos.")
    else:
        print(f"✗ Best AUC = {best['auc_test']:.3f} < 0.50. Modelos NO discriminan. Features actuales insuficientes.")
    print("=" * 75)


if __name__ == '__main__':
    main()
