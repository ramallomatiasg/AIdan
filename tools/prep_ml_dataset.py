"""
prep_ml_dataset.py — Dataset limpio y unico para los experimentos ML (#1, #3).

Join determinista de:
  - trade_archive_enriched.csv (14 features enriquecidos, por trade_id)
  - trade_archive (features base + outcome + trigger_type + created_at)

Output: trade_archive_ml.csv ordenado cronologicamente (para walk-forward split).
target = win = (mt5_pnl > 0). Asi todos los agentes entrenan sobre EXACTAMENTE
el mismo dataset y los resultados son comparables.
"""
import csv, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common.db import DB_PATH

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENRICHED = os.path.join(ROOT, 'trade_archive_enriched.csv')
OUT = os.path.join(ROOT, 'trade_archive_ml.csv')

ENRICHED_COLS = ['velocity_5c_pips','velocity_10c_pips','velocity_5c_aligned',
                 'velocity_10c_aligned','body_atr_ratio','dist_prev_high_pips',
                 'dist_prev_low_pips','mins_since_high_impact_news','volume_zscore',
                 'multi_tf_score','dist_round_pips','dist_5d_high_pips',
                 'dist_5d_low_pips','spread_entry_pips']
BASE_NUM = ['confidence','impact_score','rsi_at_entry','avg_range_pips']
BASE_CAT = ['direction','session','market_trend','trend_strength','htf_bias','volatility']
BASE_INT = ['hour_utc','day_of_week']


def main():
    feats = {}
    with open(ENRICHED, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                tid = int(float(row['trade_id']))
            except (ValueError, TypeError, KeyError):
                continue
            feats[tid] = {k: row.get(k, '') for k in ENRICHED_COLS}

    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""SELECT id, trigger_type, mt5_pnl, created_at,
                          confidence, impact_score, rsi_at_entry, avg_range_pips,
                          direction, session, market_trend, trend_strength,
                          htf_bias, volatility, hour_utc, day_of_week
                   FROM trade_archive WHERE mt5_pnl IS NOT NULL
                   ORDER BY created_at ASC""")
    rows = cur.fetchall()
    conn.close()

    out_cols = (['trade_id','created_at','trigger_type','target']
                + ENRICHED_COLS + BASE_NUM + BASE_INT + BASE_CAT)
    n_written = 0
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=out_cols)
        w.writeheader()
        for r in rows:
            tid = r['id']
            if tid not in feats:
                continue
            rec = {'trade_id': tid, 'created_at': r['created_at'],
                   'trigger_type': r['trigger_type'] or 'unknown',
                   'target': 1 if (r['mt5_pnl'] or 0) > 0 else 0}
            rec.update(feats[tid])
            for k in BASE_NUM + BASE_INT:
                rec[k] = r[k] if r[k] is not None else ''
            for k in BASE_CAT:
                rec[k] = r[k] or ''
            w.writerow(rec)
            n_written += 1

    print(f"Wrote {OUT}: {n_written} rows, {len(out_cols)} cols")
    # resumen target
    import collections
    conn = sqlite3.connect(DB_PATH, timeout=15.0); cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN mt5_pnl>0 THEN 1 ELSE 0 END) FROM trade_archive WHERE mt5_pnl IS NOT NULL")
    n, w_ = cur.fetchone(); conn.close()
    print(f"Target balance: {w_}/{n} wins = {w_/n*100:.1f}%")
    return OUT


if __name__ == '__main__':
    main()
