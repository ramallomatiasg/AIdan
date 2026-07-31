"""
train_dedicated_models.py — Entrena modelos DEDICADOS por trigger_type
y los persiste para uso en producción.

Hallazgo del Domingo: news + m15_structure tienen edge predictivo
aislado (AUC 0.75 + 0.625) que el modelo general no captura.

Output:
- config/confidence_model_news.joblib
- config/confidence_model_m15.joblib
- config/confidence_predictor_meta.json (qué features espera cada modelo)

Cada modelo guarda:
- model object
- features list (orden esperado)
- training medians (para fill missing en runtime)
- model_type (LR o RF)
- metrics
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'financial_news.db')

CATEGORICAL_FEATURES = {
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
    'volume_zscore', 'multi_tf_score', 'dist_round_pips',
    'dist_5d_high_pips', 'dist_5d_low_pips', 'spread_entry_pips',
]


def load_data(trigger_filter):
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    df = pd.read_sql_query(f"""
        SELECT id as trade_id, direction, result, mt5_pnl, confidence, trigger_type,
               htf_bias, session, hour_utc, day_of_week, rsi_at_entry, avg_range_pips,
               market_trend, trend_strength, volatility, created_at
        FROM trade_archive WHERE result IN ('win','loss') AND mt5_pnl IS NOT NULL
          AND confidence IS NOT NULL AND trigger_type = '{trigger_filter}'
        ORDER BY created_at ASC
    """, conn)
    conn.close()
    enriched = pd.read_csv(ROOT / 'trade_archive_enriched.csv')
    return df.merge(enriched, on='trade_id', how='left')


def engineer_features(df):
    X = pd.DataFrame(index=df.index)
    medians = {}
    for col, levels in CATEGORICAL_FEATURES.items():
        for level in levels:
            X[f'{col}__{level}'] = (df[col].fillna('') == level).astype(int)
    for col in NUMERIC_FEATURES:
        median = df[col].median()
        medians[col] = float(median) if pd.notna(median) else 0.0
        X[col] = df[col].fillna(medians[col]).astype(float)
    for col in ENRICHED_FEATURES:
        if col in df.columns:
            median = df[col].median()
            medians[col] = float(median) if pd.notna(median) else 0.0
            X[col] = df[col].fillna(medians[col]).astype(float)
    y = (df['result'] == 'win').astype(int).values
    return X, y, medians


def train_best(X_train, y_train, X_test, y_test):
    """Try RF and LR, return best by AUC test."""
    candidates = []

    # LR
    try:
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_train)
        X_te_s = scaler.transform(X_test)
        lr = LogisticRegression(C=0.5, max_iter=1000, random_state=42, solver='lbfgs')
        lr.fit(X_tr_s, y_train)
        p = lr.predict_proba(X_te_s)[:, 1]
        auc = roc_auc_score(y_test, p)
        brier = brier_score_loss(y_test, p)
        candidates.append({'model': lr, 'scaler': scaler, 'type': 'lr', 'auc': auc, 'brier': brier})
    except Exception as e:
        print(f"  LR failed: {e}")

    # RF
    try:
        rf = RandomForestClassifier(n_estimators=50, max_depth=3, min_samples_leaf=5,
                                     random_state=42, n_jobs=-1, class_weight='balanced')
        rf.fit(X_train, y_train)
        p = rf.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, p)
        brier = brier_score_loss(y_test, p)
        candidates.append({'model': rf, 'scaler': None, 'type': 'rf', 'auc': auc, 'brier': brier})
    except Exception as e:
        print(f"  RF failed: {e}")

    if not candidates:
        return None
    # Best by AUC
    best = max(candidates, key=lambda c: c['auc'])
    return best


def main():
    print("=" * 75)
    print(f"TRAIN DEDICATED MODELS — {datetime.now()}")
    print("=" * 75)

    triggers_to_train = ['news', 'm15_structure']
    output_dir = ROOT / 'config'
    output_dir.mkdir(exist_ok=True)

    meta = {
        'version': '1.0',
        'trained_at': datetime.now().isoformat(),
        'models': {},
        'features_order': None,
        'categorical_features': CATEGORICAL_FEATURES,
        'numeric_features': NUMERIC_FEATURES,
        'enriched_features': ENRICHED_FEATURES,
    }

    for trigger in triggers_to_train:
        print(f"\n=== {trigger.upper()} ===")
        df = load_data(trigger)
        print(f"Trades: {len(df)}")
        if len(df) < 30:
            print(f"  Too few trades, skipping {trigger}")
            continue

        X, y, medians = engineer_features(df)
        print(f"Features: {X.shape[1]}")
        wr = y.mean() * 100
        print(f"WR: {wr:.1f}%")

        split = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y[:split], y[split:]
        print(f"Train: {len(X_train)} / Test: {len(X_test)}")

        # Train both LR and RF, pick best
        best = train_best(X_train, y_train, X_test, y_test)
        if best is None:
            print(f"  Training failed for {trigger}")
            continue

        print(f"Best model: {best['type'].upper()}  AUC={best['auc']:.3f}  Brier={best['brier']:.4f}")

        # Persist
        out_path = output_dir / f'confidence_model_{trigger}.joblib'
        joblib.dump({
            'model': best['model'],
            'scaler': best['scaler'],
            'features': X.columns.tolist(),
            'medians': medians,
            'model_type': best['type'],
            'trigger': trigger,
            'trained_at': datetime.now().isoformat(),
            'n_train': len(X_train),
            'metrics': {
                'auc_test': best['auc'],
                'brier_test': best['brier'],
            },
        }, out_path)
        print(f"  Saved: {out_path} ({os.path.getsize(out_path)} bytes)")

        meta['models'][trigger] = {
            'path': out_path.name,
            'type': best['type'],
            'auc': best['auc'],
            'brier': best['brier'],
            'n_train': len(X_train),
        }
        if meta['features_order'] is None:
            meta['features_order'] = X.columns.tolist()

    # Save meta
    meta_path = output_dir / 'confidence_predictor_meta.json'
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"\nMeta: {meta_path}")

    print("\n" + "=" * 75)
    print("DEDICATED MODELS LISTOS PARA PRODUCCION")
    for trigger, info in meta['models'].items():
        verdict = '✓✓' if info['auc'] > 0.65 else ('✓' if info['auc'] > 0.55 else '~')
        print(f"  {trigger:<20s} {info['type']} AUC={info['auc']:.3f} Brier={info['brier']:.4f}  {verdict}")
    print("=" * 75)


if __name__ == '__main__':
    main()
