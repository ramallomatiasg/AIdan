"""Medidor READ-ONLY: cuanto cuesta el break-even del trailing.

ORIGEN (10-ago): el user marco que un SMC ganador habia cerrado en perdida. Investigado:
lo cerro el BE del trailing 17min despues de abrir, tras llegar a +4,4p; el precio despues
alcanzo el TP. Es el segundo caso documentado (el primero fue #658, 17-jun). Este script
mide el tamano del problema en todo el sistema.

QUE MIDE (y que NO):
  SI  — cuantos trades cerraron en la zona del BE (pips de cierre ~ BE_OFFSET) y cuanto
        DEVOLVIERON desde su propio pico (hwm - pips_cierre). Eso es dato duro: el pico
        existio y el cierre existio.
  NO  — cuanto habrian dado si el BE no los cortaba. Eso exige velas POSTERIORES al cierre
        y este script no baja velas a proposito (MT5 lo tiene el exe vivo; y la regla de la
        casa es no correr MT5 pesado en paralelo). El "pico devuelto" es una COTA INFERIOR
        del costo cuando el precio siguio a favor, y es una SOBREESTIMACION cuando el precio
        se dio vuelta (ahi el BE hizo bien su trabajo).
  NO  — cuanto SALVA el BE (perdidas evitadas). Mismo motivo: es un contrafactico.
        => el resultado NO es un neto. Es la mitad visible de la balanza. No usarlo solo
           para decidir apagar el BE.

CAVEAT DE RESOLUCION: hwm_pips lo escribe el thread de trailing (1s) y lo loguea el PM
cada 15s => el pico real puede ser MAYOR que el registrado. Subestima el costo.

Correr: python tools/measure_be_cost.py
Env: BE_OFFSET_PIPS (default 1.0), BE_ZONE (default 0.5, ancho de la banda alrededor
     del offset), CLEAN_FROM (default 2026-06-20, la data post-fixes).
"""
import os
import sqlite3
import statistics as st
import sys

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
BE_OFFSET = float(os.getenv('BE_OFFSET_PIPS', '1.0'))
BE_ZONE = float(os.getenv('BE_ZONE', '0.5'))
CLEAN_FROM = os.getenv('CLEAN_FROM', '2026-06-20')

LO, HI = BE_OFFSET - BE_ZONE, BE_OFFSET + BE_ZONE


def fetch():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT t.strategy_id sid, t.trigger_type tt, t.pips, t.mt5_pnl,
               t.tp_pips, t.sl_pips, t.created_at,
               (SELECT MAX(hwm_pips) FROM position_manager_log
                 WHERE strategy_id = t.strategy_id) hwm,
               (SELECT COUNT(*) FROM position_manager_log
                 WHERE strategy_id = t.strategy_id
                   AND action LIKE 'CLOSE%' AND COALESCE(executed,0) = 1) pm_cerro
        FROM trade_archive t
        WHERE t.mt5_pnl IS NOT NULL AND t.pips IS NOT NULL
    """).fetchall()
    c.close()
    return [r for r in rows if r['hwm'] is not None]


def clasificar(r):
    """Devuelve el rol del trade respecto del BE."""
    tp = r['tp_pips'] or 0
    armo_be = tp > 0 and r['hwm'] >= 0.50 * tp     # el BE arma a 50% del TP
    en_zona = LO <= r['pips'] <= HI
    if en_zona and not r['pm_cerro']:
        return 'cortado_por_BE'      # cerro en la zona del stop de BE, y no fue el PM
    if en_zona and r['pm_cerro']:
        return 'cortado_por_PM'      # mismo rango pero lo cerro el gestor
    if armo_be:
        return 'armo_BE_y_siguio'    # el BE existia y NO lo corto
    return 'sin_BE'


def bloque(titulo, rows):
    if not rows:
        print(f"\n{titulo}: sin filas")
        return
    dev = [r['hwm'] - r['pips'] for r in rows]
    pnl = sum(r['mt5_pnl'] for r in rows)
    print(f"\n{titulo}: n={len(rows)}")
    print(f"  pico devuelto: total {sum(dev):.1f}p | mediana {st.median(dev):.1f}p "
          f"| max {max(dev):.1f}p")
    print(f"  P&L realizado: ${pnl:+.2f} | hwm mediano {st.median([r['hwm'] for r in rows]):.1f}p")


def main():
    if not os.path.exists(DB):
        print(f"no existe la DB: {DB}")
        return 1
    rows = fetch()
    print(f"universo: {len(rows)} trades con P&L real Y pico registrado por el PM")
    print(f"zona del BE: cierre entre {LO:+.1f}p y {HI:+.1f}p (offset {BE_OFFSET}p)")

    for etiqueta, sel in (('LIFETIME', lambda r: True),
                          (f'POST-FIXES (>= {CLEAN_FROM})',
                           lambda r: (r['created_at'] or '') >= CLEAN_FROM)):
        sub = [r for r in rows if sel(r)]
        print(f"\n{'='*66}\n{etiqueta} — n={len(sub)}\n{'='*66}")
        grupos = {}
        for r in sub:
            grupos.setdefault(clasificar(r), []).append(r)
        for k in ('cortado_por_BE', 'cortado_por_PM', 'armo_BE_y_siguio', 'sin_BE'):
            bloque(k, grupos.get(k, []))

        cort = grupos.get('cortado_por_BE', [])
        if cort:
            print(f"\n  --- los cortados por el BE, uno por uno ---")
            for r in sorted(cort, key=lambda x: -(x['hwm'] - x['pips'])):
                print(f"    #{r['sid']:4} {r['tt']:14} pico {r['hwm']:5.1f}p -> cerro "
                      f"{r['pips']:+5.1f}p  (devolvio {r['hwm']-r['pips']:5.1f}p)  "
                      f"TP era {r['tp_pips'] or 0:5.1f}p  ${r['mt5_pnl']:+.2f}")
            print(f"\n  por track:")
            per = {}
            for r in cort:
                per.setdefault(r['tt'], []).append(r['hwm'] - r['pips'])
            for tt, ds in sorted(per.items(), key=lambda kv: -sum(kv[1])):
                print(f"    {tt:16} n={len(ds):2}  pico devuelto {sum(ds):6.1f}p "
                      f"(mediana {st.median(ds):.1f}p)")

            # cuanto de su TP habian recorrido: dice si el BE armo temprano o tarde
            fr = [r['hwm'] / r['tp_pips'] for r in cort if r['tp_pips']]
            if fr:
                print(f"\n  al cortarse, el pico era el {100*st.median(fr):.0f}% del TP (mediana)")
                print(f"  => si es alto, el BE armo cerca del objetivo y cortar duele mas")

    print(f"\n{'='*66}")
    print("LIMITES (leer antes de decidir nada):")
    print("  * el 'pico devuelto' NO es plata perdida: solo lo es si el precio siguio a")
    print("    favor despues del cierre. Eso exige velas posteriores y no se mide aca.")
    print("  * no se mide lo que el BE SALVA (trades que iban al SL y cerraron en +1p).")
    print("    => este numero es la mitad visible de la balanza, no un neto.")
    print("  * hwm_pips se muestrea cada 15s => el pico real puede ser mayor (subestima).")
    print("  * el criterio 'cortado_por_BE' es heuristico (cierre en la banda del offset")
    print("    sin cierre ejecutado del PM). Puede incluir algun expiry/late-close casual.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
