# -*- coding: utf-8 -*-
"""
score_exit_reason.py — READ-ONLY. Por que cierran los trades de AIdan (v3.64.0).

LA PREGUNTA QUE CONTESTA
------------------------
Medido el 17-sep sobre 86 trades con MFE/MAE reales: `structure` planea TP 8p / SL 4p
(R:R 1:2) y REALIZA 1:0,93 — el ganador medio saca +2,6p y el perdedor se come -2,8p.
Con ese R:R hace falta 76% de WR para empatar y saca 48%. O sea: la entrada acierta
razonable y la plata se pierde en la SALIDA. 29 de 33 ganadores cerraron antes del TP
y no habia UN dato de por que, porque `tp_hit` se derivaba de result=='win'
(coincidia con win/loss en 88/88 filas).

Este scorer separa, con la palabra del BROKER:
  - los que llegaron al TP,
  - los que corto el trailing/BE  (`trail_be`)  <- el bucket sospechoso
  - los que mato el expiry        (`expiry`)    <- problema #2 del diagnostico
  - los que pegaron el SL de verdad.
Y para cada bucket, cuantos pips quedaron sobre la mesa (MFE alcanzado vs cierre).

COMO LEERLO — Y QUE **NO** CONCLUIR
-----------------------------------
`trail_be` alto NO prueba por si solo que el trailing este de mas: el trailing tambien
RESCATA trades que iban a perder (medido el 10-ago: los cortados por el BE terminan en
+$2,41 en promedio => el BE no cuesta plata). Lo que este scorer agrega es la otra
mitad de la balanza: cuanto recorrido dejaron los cortados DESPUES del corte, que el
`measure_be_cost` no podia ver.

**El numero que decide es `dejado_en_la_mesa` de los cortados vs lo que se ahorro en
los rescatados.** Un bucket `trail_be` grande con `dejado` chico = el trailing esta
haciendo bien su trabajo. Grande con `dejado` grande = ahi vive la plata.

GATE PRE-DECLARADO (no mover)
-----------------------------
n>=25 cierres con `exit_reason` poblado por track. Recien ahi se puede proponer algo.
Antes de eso es descriptivo y se dice que es descriptivo. Y aunque pase: una celda que
separa es permiso para probar en SHADOW, nunca para cambiar produccion — el proyecto
ya freno 3 sobreajustes asi (ML, gates, bounce).

TRIPWIRE DE HOOK MUERTO
-----------------------
Si hay trades archivados DESPUES del deploy de v3.64.0 con `exit_reason` NULL o
'unknown' en su mayoria, el hook murio en silencio: buscar en aidan.log la linea
`MT5 instant eval: ... exit=`. Es la clase de bug que ya mato a M15, SMC y al reversal.

Uso:  python tools/score_exit_reason.py [--days N]
READ-ONLY (mode=ro, solo SELECT). No necesita MT5 => se puede correr con AIdan vivo.
"""
import argparse
import os
import sqlite3
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')

#: Fecha del deploy de v3.64.0 — antes de esto la columna no existia y NULL es lo esperado.
DEPLOY_DATE = '2026-09-17'

#: Gate pre-declarado.
MIN_N = 25

_ORDEN = ('tp', 'trail_be', 'expiry', 'sl', 'manager', 'kill', 'aidan',
          'stopout', 'manual', 'unknown')


def _conn():
    if not os.path.exists(DB_PATH):
        print(f'ERROR: no existe {DB_PATH}')
        sys.exit(2)
    c = sqlite3.connect('file:' + DB_PATH.replace(os.sep, '/') + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    return c


def _fmt(x, spec='+6.1f'):
    """Formatea o devuelve espacios del mismo ancho si el dato no esta."""
    ancho = int(''.join(ch for ch in spec if ch.isdigit()).split('.')[0] or 6)
    return format(x, spec) if x is not None else ' ' * ancho


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=0,
                    help='limitar a los ultimos N dias (0 = todo desde el deploy)')
    args = ap.parse_args()

    conn = _conn()
    cols = [r[1] for r in conn.execute('PRAGMA table_info(trade_archive)')]
    if 'exit_reason' not in cols:
        print('La columna exit_reason no existe todavia.')
        print('=> AIdan no se rebuildeo con v3.64.0, o nunca arranco desde entonces.')
        return 1

    where = "WHERE created_at >= ? AND mt5_pnl IS NOT NULL"
    params = [DEPLOY_DATE]
    if args.days:
        where += " AND created_at >= date('now', ?)"
        params.append(f'-{args.days} days')

    rows = conn.execute(f"""
        SELECT trigger_type, exit_reason, exit_reason_raw, pips, mt5_pnl,
               mfe_pips, mae_pips, tp_pips, sl_pips, created_at
        FROM trade_archive {where} ORDER BY created_at
    """, params).fetchall()
    total_post = len(rows)

    print('=' * 72)
    print(f'MOTIVO DE CIERRE — trades archivados desde {DEPLOY_DATE}'
          + (f' (ultimos {args.days}d)' if args.days else ''))
    print('=' * 72)

    if not total_post:
        print('\nSin trades cerrados desde el deploy todavia. Nada que leer — es lo')
        print('esperado el primer dia. AIdan hace ~7 trades/dia => n=25 por track')
        print('son varias semanas.')
        conn.close()
        return 0

    # ---------------- tripwire de hook muerto ----------------
    sin_motivo = sum(1 for r in rows if not r['exit_reason'] or r['exit_reason'] == 'unknown')
    pct = 100 * sin_motivo / total_post
    print(f'\n[TRIPWIRE] {sin_motivo}/{total_post} ({pct:.0f}%) sin motivo determinado.')
    if pct >= 50:
        print('  !! MAS DE LA MITAD SIN MOTIVO — el hook puede estar muerto.')
        print('     Buscar en aidan.log: `MT5 instant eval: ... exit=`')
        print('     Si la linea no aparece, sync_closed_positions no esta clasificando.')
    else:
        print('  OK — el hook escribe.')

    # ---------------- distribucion por track ----------------
    por_track = defaultdict(list)
    for r in rows:
        por_track[r['trigger_type'] or '?'].append(r)

    for track in sorted(por_track, key=lambda k: -len(por_track[k])):
        rs = por_track[track]
        cnt = Counter(r['exit_reason'] or 'unknown' for r in rs)
        pnl = sum(r['mt5_pnl'] for r in rs)
        print(f'\n--- {track}: n={len(rs)}  PnL=${pnl:+.2f}'
              + ('' if len(rs) >= MIN_N else f'  [DESCRIPTIVO: n<{MIN_N}, no concluye]'))
        print('    motivo     |  n | % de los  | pips med | MFE med | dejado en la mesa')
        print('               |    | ganadores |          |         | (MFE - cierre)')
        for k in _ORDEN:
            s = [r for r in rs if (r['exit_reason'] or 'unknown') == k]
            if not s:
                continue
            wins = [r for r in rs if r['mt5_pnl'] > 0]
            pct_w = (100 * sum(1 for r in s if r['mt5_pnl'] > 0) / len(wins)) if wins else 0
            pips = [r['pips'] for r in s if r['pips'] is not None]
            mfes = [r['mfe_pips'] for r in s if r['mfe_pips'] is not None]
            dejado = [r['mfe_pips'] - r['pips'] for r in s
                      if r['mfe_pips'] is not None and r['pips'] is not None]
            _p = _fmt(st.median(pips) if pips else None)
            _m = _fmt(st.median(mfes) if mfes else None, '6.1f')
            _d = _fmt(st.median(dejado) if dejado else None, '6.1f')
            print(f'    {k:10s} | {len(s):2d} | {pct_w:8.0f}% | {_p}p | {_m}p | {_d}p')

        # la lectura que importa: ganadores que NO llegaron al TP
        wins = [r for r in rs if r['mt5_pnl'] > 0]
        cortados = [r for r in wins if (r['exit_reason'] or '') in ('trail_be', 'expiry')]
        if wins:
            print(f'    => ganadores: {len(wins)} | cortados antes del TP: {len(cortados)}'
                  f' ({100*len(cortados)/len(wins):.0f}%)')
            dj = [r['mfe_pips'] - r['pips'] for r in cortados
                  if r['mfe_pips'] is not None and r['pips'] is not None]
            if dj:
                print(f'       dejaron sobre la mesa: mediana {st.median(dj):.1f}p'
                      f' | total {sum(dj):.1f}p')

    # ---------------- control: el crudo del broker ----------------
    raws = Counter(r['exit_reason_raw'] for r in rows if r['exit_reason_raw'] is not None)
    if raws:
        print(f'\n[CRUDO DEL BROKER] {dict(raws)}   (4=SL 5=TP 3=EXPERT 0/1/2=manual 6=stopout)')
        print('  Se guarda aparte a proposito: si la clasificacion resulta estar mal,')
        print('  con esto se re-deriva. El error de tp_hit fue no tener este dato.')

    print(f'\nGate: n>={MIN_N} por track. Una celda que separa habilita SHADOW, no un cambio.')
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
