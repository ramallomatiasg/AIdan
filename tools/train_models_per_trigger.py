"""
train_models_per_trigger.py — Entrena 1 modelo por trigger_type.

Hipotesis: news, structure, smc tienen patrones predictivos DISTINTOS.
Un modelo general (276 trades) no captura. 1 modelo por trigger (50-113
trades cada uno) capaz si.

Output: AUC por trigger + best model per trigger.
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

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


def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT id as trade_id, direction, result, mt5_pnl, confidence, trigger_type,
               htf_bias, session, hour_utc, day_of_week, rsi_at_entry, avg_range_pips,
               market_trend, trend_strength, volatility, created_at
        FROM trade_archive WHERE result IN ('win','loss') AND mt5_pnl IS NOT NULL
          AND confidence IS NOT NULL AND trigger_type IS NOT NULL
        ORDER BY created_at ASC
    """, conn)
    conn.close()
    enriched = pd.read_csv(ROOT / 'trade_archive_enriched.csv')
    return df.merge(enriched, on='trade_id', how='left')


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


def train_eval(X_train, y_train, X_test, y_test, name):
    """Train RF + LR, return best."""
    if len(X_train) < 20 or len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
        return None

    results = {}
    # RF
    try:
        rf = RandomForestClassifier(n_estimators=50, max_depth=3, min_samples_leaf=5,
                                     random_state=42, n_jobs=-1, class_weight='balanced')
        rf.fit(X_train, y_train)
        p_test = rf.predict_proba(X_test)[:, 1]
        results['RF'] = {
            'auc': roc_auc_score(y_test, p_test),
            'brier': brier_score_loss(y_test, p_test),
        }
    except Exception as e:
        results['RF'] = {'error': str(e)}

    # LR (regularizada)
    try:
        lr = LogisticRegression(C=0.5, max_iter=1000, random_state=42, solver='lbfgs')
        # Simple scaling
        means = X_train.mean()
        stds = X_train.std().replace(0, 1)
        X_train_s = (X_train - means) / stds
        X_test_s = (X_test - means) / stds
        lr.fit(X_train_s, y_train)
        p_test = lr.predict_proba(X_test_s)[:, 1]
        results['LR'] = {
            'auc': roc_auc_score(y_test, p_test),
            'brier': brier_score_loss(y_test, p_test),
        }
    except Exception as e:
        results['LR'] = {'error': str(e)}

    return results


def main():
    print("=" * 75)
    print(f"TRAIN MODELS PER TRIGGER_TYPE — {datetime.now()}")
    print("=" * 75)

    df = load_data()
    print(f"\nTotal trades: {len(df)}")
    triggers = df['trigger_type'].value_counts()
    print("Distribution:")
    for t, n in triggers.items():
        wr = (df[df['trigger_type'] == t]['result'] == 'win').mean() * 100
        print(f"  {t:25s} n={n:3d} WR={wr:.1f}%")

    print(f"\n{'Trigger':<20s} {'n':>4s} {'split':>10s} {'RF AUC':>8s} {'RF Brier':>10s} {'LR AUC':>8s} {'LR Brier':>10s}")
    print("-" * 85)

    overall_metrics = []

    # Train por trigger (solo los que tienen >=30 trades)
    for trigger in triggers.index:
        sub = df[df['trigger_type'] == trigger].reset_index(drop=True)
        if len(sub) < 30:
            print(f"  {trigger:<18s} {len(sub):>4d}  too few, skipped")
            continue

        X, y = engineer_features(sub)
        # Walk-forward 80/20
        split = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y[:split], y[split:]

        result = train_eval(X_train, y_train, X_test, y_test, trigger)
        if result is None:
            print(f"  {trigger:<18s} {len(sub):>4d}  failed (single class)")
            continue

        rf_auc = result.get('RF', {}).get('auc')
        rf_brier = result.get('RF', {}).get('brier')
        lr_auc = result.get('LR', {}).get('auc')
        lr_brier = result.get('LR', {}).get('brier')
        rf_str = f"{rf_auc:.3f}" if rf_auc else "err"
        rf_b_str = f"{rf_brier:.4f}" if rf_brier else "err"
        lr_str = f"{lr_auc:.3f}" if lr_auc else "err"
        lr_b_str = f"{lr_brier:.4f}" if lr_brier else "err"
        print(f"  {trigger:<18s} {len(sub):>4d}  tr/te {split}/{len(sub)-split}  {rf_str:>6s}   {rf_b_str:>8s}   {lr_str:>6s}   {lr_b_str:>8s}")

        if rf_auc:
            overall_metrics.append((trigger, 'RF', rf_auc, rf_brier))
        if lr_auc:
            overall_metrics.append((trigger, 'LR', lr_auc, lr_brier))

    # Best por trigger
    print("\n=== BEST MODEL PER TRIGGER ===")
    by_trigger = {}
    for trig, model, auc, brier in overall_metrics:
        if trig not in by_trigger or auc > by_trigger[trig][1]:
            by_trigger[trig] = (model, auc, brier)
    for trig, (m, auc, brier) in by_trigger.items():
        verdict = '✓✓' if auc > 0.65 else ('✓' if auc > 0.55 else '✗')
        print(f"  {trig:<20s} best={m} AUC={auc:.3f} Brier={brier:.4f}  {verdict}")

    # Comparativa con modelo general
    print("\n=== COMPARACION CON MODELO GENERAL ===")
    X_all, y_all = engineer_features(df)
    split_all = int(len(X_all) * 0.8)
    X_tr, X_te = X_all.iloc[:split_all], X_all.iloc[split_all:]
    y_tr, y_te = y_all[:split_all], y_all[split_all:]
    gen_result = train_eval(X_tr, y_tr, X_te, y_te, 'general')
    if gen_result and 'RF' in gen_result:
        print(f"  Modelo general (276 trades, todos triggers):")
        print(f"    RF: AUC={gen_result['RF']['auc']:.3f}  Brier={gen_result['RF']['brier']:.4f}")
        if 'LR' in gen_result:
            print(f"    LR: AUC={gen_result['LR']['auc']:.3f}  Brier={gen_result['LR']['brier']:.4f}")

    # Veredicto
    print("\n" + "=" * 75)
    if by_trigger:
        avg_auc = sum(auc for _, auc, _ in by_trigger.values()) / len(by_trigger)
        best_trig = max(by_trigger.items(), key=lambda x: x[1][1])
        print(f"Avg AUC entre triggers: {avg_auc:.3f}")
        print(f"Mejor trigger: {best_trig[0]} con AUC {best_trig[1][1]:.3f}")
        if avg_auc > 0.60:
            print("✓✓ Modelos por trigger SUPERAN al general. Vale la pena adoptar.")
        elif avg_auc > 0.55:
            print("~ Modelos por trigger marginalmente mejores. Considerar adopción parcial.")
        else:
            print("✗ Modelos por trigger NO mejoran significativamente. Mantener general.")
    print("=" * 75)


if __name__ == '__main__':
    main()
