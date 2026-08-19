"""
measure_tca.py — TCA read-only: costo esperado vs realizado (v3.58.0).

Lee slippage_log (poblada por log_fill desde v3.58.0) y reporta:
  - slippage por fill: mediana, p90, max, % de fills con slippage > 0
  - spread al momento de la orden: mediana, p90
  - breakdown por hora AR y por direccion

Umbral PRE-DECLARADO (19-ago, de la referencia MQL5 Blueprint Part 14):
  mediana de slippage > 0.7 pips en un mayor con liquidez normal = la ejecucion
  es un problema MATERIAL, no ruido. Debajo de eso, el costo dominante sigue
  siendo la comision y no hay nada que arreglar del lado de la ejecucion.

No toca nada: SELECT only. No necesita MT5.
"""
import os
import sqlite3
import statistics
import sys

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
THRESHOLD_PIPS = 0.7  # pre-declarado — NO ajustar despues de ver los datos


def main():
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    rows = conn.execute(
        "SELECT strategy_id, slippage_pips, spread_pips, direction, timestamp "
        "FROM slippage_log ORDER BY id").fetchall()
    conn.close()

    print(f"TCA — slippage_log: {len(rows)} fills")
    if not rows:
        print("Sin datos todavia. La tabla se puebla con cada fill desde v3.58.0.")
        print("(0 filas + trades nuevos ejecutados = el hook esta muerto -> revisar "
              "WARNING 'log_fill FAILED' en aidan.log)")
        return 0

    slips = [r[1] for r in rows if r[1] is not None]
    spreads = [r[2] for r in rows if r[2] is not None]

    def pct(v, p):
        s = sorted(v)
        return s[min(len(s) - 1, int(len(s) * p))]

    med = statistics.median(slips)
    print(f"\nSlippage (+ = peor que lo pedido):")
    print(f"  mediana {med:+.2f}p | p90 {pct(slips, 0.9):+.2f}p | "
          f"max {max(slips):+.2f}p | >0: {sum(1 for s in slips if s > 0)}/{len(slips)}")
    if spreads:
        print(f"Spread al ordenar: mediana {statistics.median(spreads):.2f}p | "
              f"p90 {pct(spreads, 0.9):.2f}p")

    # por hora AR (timestamp es CURRENT_TIMESTAMP = UTC en SQLite; AR = UTC-3)
    by_hour = {}
    for r in rows:
        if r[1] is None or not r[4]:
            continue
        try:
            h = (int(r[4][11:13]) - 3) % 24
        except (ValueError, IndexError):
            continue
        by_hour.setdefault(h, []).append(r[1])
    if by_hour:
        print("\nPor hora AR (n>=3):")
        for h in sorted(by_hour):
            v = by_hour[h]
            if len(v) >= 3:
                print(f"  {h:02d}h  n={len(v):3d}  mediana {statistics.median(v):+.2f}p")

    print(f"\nVeredicto (umbral pre-declarado {THRESHOLD_PIPS}p):")
    if len(slips) < 30:
        print(f"  n={len(slips)} < 30 -> sin veredicto todavia (no concluir).")
    elif med > THRESHOLD_PIPS:
        print(f"  mediana {med:.2f}p > {THRESHOLD_PIPS}p -> la ejecucion es un "
              f"problema material. Mirar el breakdown por hora antes de actuar.")
    else:
        print(f"  mediana {med:.2f}p <= {THRESHOLD_PIPS}p -> ejecucion sana; el "
              f"costo dominante sigue siendo la comision.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
