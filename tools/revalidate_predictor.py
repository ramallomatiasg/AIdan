"""
revalidate_predictor.py — ¿El predictor ML v3.35.0 (news 0.75, m15 0.625) es real o se engaña?

El entrenamiento original (train_dedicated_models.py) midio el AUC sobre UN SOLO
corte 80/20 (test = ultimas ~10-11 filas) y encima eligio el mejor de LR/RF en
ESE mismo corte. Eso es fragil: con n_test ~10, el AUC es casi azar de cual corte tocó.

Este script:
  1. Reproduce el AUC del corte unico (deberia dar ~0.75 / ~0.625).
  2. Lo valida en serio: 5-fold StratifiedKFold (multi-seed), TimeSeriesSplit,
     y permutation test (labels barajados).
  3. Veredicto: si el CV honesto colapsa a ~0.5, el 0.75 era espejismo.
"""
import os, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit
from tools.train_dedicated_models import load_data, engineer_features


def fit_lr(Xtr, ytr):
    sc = StandardScaler()
    Xs = sc.fit_transform(Xtr)
    lr = LogisticRegression(C=0.5, max_iter=1000, random_state=42, solver='lbfgs')
    lr.fit(Xs, ytr)
    return lr, sc


def evaluate(trigger, claimed):
    df = load_data(trigger)
    X, y, _ = engineer_features(df)
    X = X.values
    n = len(y)
    print(f"\n{'='*64}\n{trigger.upper()}  (n={n}, wins={int(y.sum())}={y.mean()*100:.0f}%, claim AUC={claimed})\n{'='*64}")

    # 1. Reproducir el corte unico 80/20 (como produccion)
    split = int(n * 0.8)
    lr, sc = fit_lr(X[:split], y[:split])
    p_test = lr.predict_proba(sc.transform(X[split:]))[:, 1]
    p_train = lr.predict_proba(sc.transform(X[:split]))[:, 1]
    try:
        auc_single = roc_auc_score(y[split:], p_test)
    except ValueError:
        auc_single = float('nan')
    auc_train = roc_auc_score(y[:split], p_train)
    print(f"1) Corte unico 80/20 (como produccion): test AUC={auc_single:.3f}  (train AUC={auc_train:.3f}, n_test={n-split})")

    # 2. StratifiedKFold multi-seed (validacion honesta)
    seed_means = []
    for seed in range(20):
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
        aucs = []
        for tr, te in skf.split(X, y):
            lr, sc = fit_lr(X[tr], y[tr])
            p = lr.predict_proba(sc.transform(X[te]))[:, 1]
            try:
                aucs.append(roc_auc_score(y[te], p))
            except ValueError:
                pass
        if aucs:
            seed_means.append(np.mean(aucs))
    cv_mean, cv_std = np.mean(seed_means), np.std(seed_means)
    print(f"2) 5-fold CV (20 seeds): AUC media={cv_mean:.3f} +/- {cv_std:.3f}  rango [{min(seed_means):.3f}, {max(seed_means):.3f}]")

    # 3. TimeSeriesSplit (respeta cronologia = escenario real)
    tss = TimeSeriesSplit(n_splits=5)
    ts_aucs = []
    for tr, te in tss.split(X):
        if len(np.unique(y[te])) < 2:
            continue
        lr, sc = fit_lr(X[tr], y[tr])
        p = lr.predict_proba(sc.transform(X[te]))[:, 1]
        ts_aucs.append(roc_auc_score(y[te], p))
    ts_mean = np.mean(ts_aucs) if ts_aucs else float('nan')
    print(f"3) TimeSeriesSplit (cronologico real): AUC media={ts_mean:.3f}  ({len(ts_aucs)} folds validos)")

    # 4. Permutation test: con labels barajados, ¿que AUC sale por azar?
    rng = np.random.RandomState(0)
    null_aucs = []
    for _ in range(200):
        yp = rng.permutation(y)
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        a = []
        for tr, te in skf.split(X, yp):
            lr, sc = fit_lr(X[tr], yp[tr])
            p = lr.predict_proba(sc.transform(X[te]))[:, 1]
            try: a.append(roc_auc_score(yp[te], p))
            except ValueError: pass
        if a: null_aucs.append(np.mean(a))
    null_p95 = np.percentile(null_aucs, 95)
    p_value = np.mean([na >= cv_mean for na in null_aucs])
    print(f"4) Permutation test (labels random): null AUC p95={null_p95:.3f}  | p-value del modelo real={p_value:.3f}")

    # Veredicto
    real = cv_mean >= 0.58 and p_value < 0.05 and ts_mean >= 0.55
    print(f"\n   VEREDICTO: {'REAL (sobrevive)' if real else 'ESPEJISMO (no sobrevive — el ' + str(claimed) + ' fue suerte del corte)'}")
    print(f"   El AUC honesto del modelo es ~{cv_mean:.2f}, no {claimed}.")
    return {'trigger': trigger, 'claimed': claimed, 'single': auc_single,
            'cv': cv_mean, 'ts': ts_mean, 'p_value': p_value, 'real': real}


if __name__ == '__main__':
    results = []
    results.append(evaluate('news', 0.75))
    results.append(evaluate('m15_structure', 0.625))
    print(f"\n{'='*64}\nRESUMEN\n{'='*64}")
    for r in results:
        print(f"  {r['trigger']:<16s} claim={r['claimed']}  corte_unico={r['single']:.2f}  CV_honesto={r['cv']:.2f}  -> {'REAL' if r['real'] else 'ESPEJISMO'}")
