"""
Deshace los outcomes que los scorers escribieron con el OFFSET ROTO (mercado cerrado).

Contexto (20-sep-2026): `score_shadow_trader.py` y `score_rejected_signals.py`
derivaban el offset server-UTC restando la hora local al ultimo tick. Con el mercado cerrado
el ultimo tick es el del cierre del viernes => offset ~-44h => cada ventana se
puntuo ~2 dias ANTES de la decision. Corridas afectadas (scored_at UTC):
    2026-09-13 20h (sabado)  y  2026-09-20 20h (domingo)
Lo que hace: pone en NULL las columnas de outcome de esas filas para que el scorer
(ya arreglado, ver tools/mt5_server_offset.py) las re-puntue con el offset correcto.
NO toca trade_archive ni ninguna tabla de produccion: solo las tablas que son de los
scorers (shadow_trader_log kind='open', rejected_signals). Los 'manage' del shadow
trader NO se tocan: se puntuan contra trade_archive, sin MT5, y estan bien.

DRY-RUN por default. `--apply` escribe (con backup previo de la DB).
Despues: `python tools/score_shadow_trader.py --server-offset-hours 3` y
         `python tools/score_rejected_signals.py --server-offset-hours 3`
(3 = verificado el 20-sep contra la vela del NFP del 4-sep: spike de 40p en
15:30 server = 12:30 UTC), o sin el flag con mercado abierto (cachea solo).
"""
import argparse
import os
import shutil
import sqlite3
from datetime import datetime

DB = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')
# corridas hechas con el mercado cerrado (prefijo de scored_at, UTC)
BAD_RUNS = ('2026-09-13 20', '2026-09-20 20')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='escribir (default: dry-run)')
    ap.add_argument('--db', default=DB)
    args = ap.parse_args()

    where = ' OR '.join(["substr(scored_at,1,13)=?"] * len(BAD_RUNS))
    if not args.apply:
        conn = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
    else:
        bak = args.db + f'.bak_reset_offset_{datetime.now():%Y%m%d_%H%M%S}'
        shutil.copy2(args.db, bak)
        print(f'backup: {bak}')
        conn = sqlite3.connect(args.db, timeout=15.0)

    n_st = conn.execute(f"SELECT count(*) FROM shadow_trader_log WHERE kind='open' AND ({where})",
                        BAD_RUNS).fetchone()[0]
    n_rs = conn.execute(f"SELECT count(*) FROM rejected_signals WHERE ({where})", BAD_RUNS).fetchone()[0]
    print(f"filas con outcome de offset roto: shadow_trader_log(open)={n_st}  rejected_signals={n_rs}")
    for run in BAD_RUNS:
        a = conn.execute("SELECT count(*), round(avg(outcome_pips),1) FROM shadow_trader_log "
                         "WHERE kind='open' AND decision IN ('CALL','PUT') AND substr(scored_at,1,13)=?",
                         (run,)).fetchone()
        print(f"  {run}: open CALL/PUT n={a[0]} media={a[1]}p")

    if not args.apply:
        print('\nDRY-RUN: no se escribio nada. Para aplicar: --apply')
        conn.close()
        return
    conn.execute(f"UPDATE shadow_trader_log SET outcome_pips=NULL, outcome_detail=NULL, scored_at=NULL "
                 f"WHERE kind='open' AND ({where})", BAD_RUNS)
    conn.execute(f"UPDATE rejected_signals SET fav_pips=NULL, adv_pips=NULL, abs_move_pips=NULL, "
                 f"net_drift_pips=NULL, scored_at=NULL WHERE ({where})", BAD_RUNS)
    conn.commit()
    conn.close()
    print(f'\nAPLICADO: {n_st} + {n_rs} filas vuelven a pendientes. Re-puntuar con --server-offset-hours 3.')


if __name__ == '__main__':
    main()
