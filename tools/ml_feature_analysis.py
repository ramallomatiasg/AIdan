"""
Feature analysis + ML train sobre trade_archive.

Objetivo: identificar features que predicen win/loss y entrenar modelo
para calcular probabilidad de win pre-trade.

Caveat principal: 148-160 trades es muestra chica para XGBoost serio
(necesitarías 500+). Pero podemos:
1. Identificar features con poder predictivo via correlación
2. Entrenar logistic regression regularizada (menos prone a overfit)
3. XGBoost con cross-validation estricto + early stopping
4. Reportar feature importance + thresholds preliminares
5. NO integrar a producción todavía — esperar 500+ trades para serio

Uso:
    python tools/ml_feature_analysis.py
    python tools/ml_feature_analysis.py --track m5
    python tools/ml_feature_analysis.py --use-xgb     # usar XGBoost en lugar de LogReg
"""
import argparse
import os
import sqlite3
import sys
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


def load_data(track='all'):
    """Load trade_archive into DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    where_track = ''
    if track == 'm5':
        where_track = "AND trigger_type NOT LIKE 'm15_%' AND trigger_type NOT LIKE 'h1_%'"
    elif track == 'm15':
        where_track = "AND trigger_type LIKE 'm15_%'"
    elif track == 'h1':
        where_track = "AND trigger_type LIKE 'h1_%'"

    df = pd.read_sql_query(f"""
        SELECT direction, result, sl_pips, tp_pips, confidence, impact_score,
               trigger_type, market_trend, trend_strength, rsi_at_entry, htf_bias,
               volatility, avg_range_pips, session, hour_utc, day_of_week,
               mt5_pnl, profile_name
        FROM trade_archive
        WHERE result IN ('win', 'loss')
          AND mt5_pnl IS NOT NULL
          AND avg_range_pips > 0
          {where_track}
    """, conn)
    conn.close()
    return df


def prepare_features(df):
    """Encode features para ML. Returns X, y, feature_names."""
    feat = pd.DataFrame()

    # Numeric
    feat['confidence'] = df['confidence'].fillna(50)
    feat['impact_score'] = df['impact_score'].fillna(50)
    feat['rsi_at_entry'] = df['rsi_at_entry'].fillna(50)
    feat['avg_range_pips'] = df['avg_range_pips'].fillna(3.0)
    feat['sl_pips'] = df['sl_pips'].fillna(5.0)
    feat['tp_pips'] = df['tp_pips'].fillna(10.0)
    feat['rr_ratio'] = feat['tp_pips'] / (feat['sl_pips'] + 0.001)
    feat['hour_utc'] = df['hour_utc'].fillna(12)
    feat['day_of_week'] = df['day_of_week'].fillna(2)

    # Direction (CALL=1, PUT=0)
    feat['is_call'] = (df['direction'] == 'CALL').astype(int)

    # HTF alignment
    htf = df['htf_bias'].fillna('neutral')
    feat['htf_aligned_with_dir'] = (
        ((df['direction'] == 'CALL') & (htf == 'bullish')) |
        ((df['direction'] == 'PUT') & (htf == 'bearish'))
    ).astype(int)
    feat['htf_against_dir'] = (
        ((df['direction'] == 'CALL') & (htf == 'bearish')) |
        ((df['direction'] == 'PUT') & (htf == 'bullish'))
    ).astype(int)

    # M5 trend alignment
    tr = df['market_trend'].fillna('neutral')
    feat['m5_aligned_with_dir'] = (
        ((df['direction'] == 'CALL') & (tr == 'bullish')) |
        ((df['direction'] == 'PUT') & (tr == 'bearish'))
    ).astype(int)
    feat['m5_against_dir'] = (
        ((df['direction'] == 'CALL') & (tr == 'bearish')) |
        ((df['direction'] == 'PUT') & (tr == 'bullish'))
    ).astype(int)

    # Counter-both flag
    feat['counter_both'] = ((feat['htf_against_dir'] == 1) & (feat['m5_against_dir'] == 1)).astype(int)
    # Aligned-both (SIM A flag)
    feat['aligned_both'] = ((feat['htf_aligned_with_dir'] == 1) & (feat['m5_aligned_with_dir'] == 1)).astype(int)

    # Volatility encoded
    vol_map = {'low': 0, 'normal': 1, 'high': 2}
    feat['volatility_n'] = df['volatility'].fillna('normal').map(vol_map).fillna(1).astype(int)

    # Session encoded
    sess_map = {'asia': 0, 'london': 1, 'ny': 2, 'overlap': 3}
    feat['session_n'] = df['session'].fillna('ny').map(sess_map).fillna(2).astype(int)

    # Trigger type encoded (one-hot)
    feat['trig_news'] = (df['trigger_type'].fillna('') == 'news').astype(int)
    feat['trig_structure'] = (df['trigger_type'].fillna('') == 'structure').astype(int)
    feat['trig_smc'] = (df['trigger_type'].fillna('') == 'smc').astype(int)
    feat['trig_m15_struct'] = (df['trigger_type'].fillna('').str.startswith('m15_')).astype(int)
    feat['trig_h1_struct'] = (df['trigger_type'].fillna('').str.startswith('h1_')).astype(int)

    # Target
    y = (df['result'] == 'win').astype(int)

    return feat, y


def feature_correlation(X, y):
    """Compute Pearson correlation de cada feature con target."""
    corr = pd.DataFrame({
        'feature': X.columns,
        'correlation': [X[c].corr(y) for c in X.columns],
    })
    corr['abs_corr'] = corr['correlation'].abs()
    corr = corr.sort_values('abs_corr', ascending=False)
    return corr


def train_logistic(X, y):
    """Logistic regression con regularización L2 + cross-validation."""
    model = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    accs = cross_val_score(model, X, y, cv=cv, scoring='accuracy')
    aucs = cross_val_score(model, X, y, cv=cv, scoring='roc_auc')

    # Train on full for inspection
    model.fit(X, y)
    coefs = pd.DataFrame({'feature': X.columns, 'coef': model.coef_[0]})
    coefs['abs_coef'] = coefs['coef'].abs()
    coefs = coefs.sort_values('abs_coef', ascending=False)

    return {
        'cv_accuracy_mean': accs.mean(),
        'cv_accuracy_std': accs.std(),
        'cv_auc_mean': aucs.mean(),
        'cv_auc_std': aucs.std(),
        'coefficients': coefs,
        'baseline_acc': max(y.mean(), 1 - y.mean()),  # majority class baseline
    }


def train_random_forest(X, y):
    """Random forest con cross-val (mejor para no-linealidades)."""
    model = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42, n_jobs=-1)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    accs = cross_val_score(model, X, y, cv=cv, scoring='accuracy', n_jobs=-1)
    aucs = cross_val_score(model, X, y, cv=cv, scoring='roc_auc', n_jobs=-1)

    model.fit(X, y)
    importances = pd.DataFrame({'feature': X.columns, 'importance': model.feature_importances_})
    importances = importances.sort_values('importance', ascending=False)

    return {
        'cv_accuracy_mean': accs.mean(),
        'cv_accuracy_std': accs.std(),
        'cv_auc_mean': aucs.mean(),
        'cv_auc_std': aucs.std(),
        'importances': importances,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--track', default='all', choices=['all', 'm5', 'm15', 'h1'])
    args = p.parse_args()

    print(f'=== ML Feature Analysis (track={args.track}) ===\n')
    df = load_data(args.track)
    print(f'Trades: {len(df)}')
    print(f'Wins: {(df["result"]=="win").sum()} / Losses: {(df["result"]=="loss").sum()}')
    win_rate = (df['result'] == 'win').sum() / len(df) * 100
    print(f'Win rate: {win_rate:.1f}%\n')

    if len(df) < 50:
        print(f'WARNING: muestra chica ({len(df)} trades). ML poco confiable.')
    if len(df) < 30:
        print('Muestra muy chica, abort.')
        return

    X, y = prepare_features(df)
    print(f'Features: {len(X.columns)}')
    print(f'Feature names: {list(X.columns)}\n')

    # 1. Correlation analysis
    print('=== TOP 10 features por correlation con WIN ===')
    corr = feature_correlation(X, y)
    print(corr.head(10).to_string(index=False))
    print()

    # 2. Logistic Regression (linear baseline)
    print('=== LOGISTIC REGRESSION (CV 5-fold) ===')
    lr = train_logistic(X, y)
    print(f'Baseline accuracy (majority class): {lr["baseline_acc"]*100:.1f}%')
    print(f'Model CV accuracy: {lr["cv_accuracy_mean"]*100:.1f}% ± {lr["cv_accuracy_std"]*100:.1f}%')
    print(f'Model CV AUC: {lr["cv_auc_mean"]:.3f} ± {lr["cv_auc_std"]:.3f}')
    if lr['cv_auc_mean'] < 0.55:
        print('AUC < 0.55: modelo no aprende mejor que random.')
    print('\nTop 8 features por |coef|:')
    print(lr['coefficients'].head(8).to_string(index=False))
    print()

    # 3. Random Forest (non-linear)
    print('=== RANDOM FOREST (CV 5-fold) ===')
    rf = train_random_forest(X, y)
    print(f'Model CV accuracy: {rf["cv_accuracy_mean"]*100:.1f}% ± {rf["cv_accuracy_std"]*100:.1f}%')
    print(f'Model CV AUC: {rf["cv_auc_mean"]:.3f} ± {rf["cv_auc_std"]:.3f}')
    print('\nTop 8 features por importance:')
    print(rf['importances'].head(8).to_string(index=False))
    print()

    # 4. Conclusion
    print('=== CONCLUSION ===')
    best_auc = max(lr['cv_auc_mean'], rf['cv_auc_mean'])
    if best_auc < 0.55:
        verdict = 'No predictive signal. Esperar mas data.'
    elif best_auc < 0.65:
        verdict = 'Senal debil. Util como filtro complementario, no como decision principal.'
    elif best_auc < 0.75:
        verdict = 'Senal moderada. Util como filtro real con threshold cuidadoso.'
    else:
        verdict = 'Senal fuerte. Modelo confiable para filtro automatico.'
    print(f'AUC max: {best_auc:.3f} -> {verdict}')


if __name__ == '__main__':
    main()
