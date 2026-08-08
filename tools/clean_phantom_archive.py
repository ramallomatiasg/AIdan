"""v3.51.1 — limpieza puntual de las filas de `trade_archive` que NO fueron trades.

Contexto: hasta v3.51.1 la evaluacion por precio archivaba cualquier estrategia vencida,
aunque nunca hubiera llegado al broker (skip por cooldown, "market closing soon", spread
gate, limit sin fill). Esas filas llevan los pips TEORICOS del TP/SL nominal. El guard de
v3.51.1 corta el goteo hacia adelante; esto limpia lo que ya estaba.

REGLA: no se borra nada sin verificar contra el BROKER. Una fila solo se borra si no tiene
  (a) deal en el historial de MT5 con comentario 'AIdan #<sid>'  [decisivo]
  (b) filas en position_manager_log (el PM solo evalua posiciones ABIERTAS)
  (c) mt5_ticket / mt5_pnl en auto_strategies
Las que SI tienen evidencia son trades reales a los que se les perdio el P&L: se COMPLETAN
con la verdad del broker, no se borran. Los labels win/loss no se tocan (precedente #658);
si alguno resultara incoherente con el P&L real, el script ABORTA y lo reporta.

Uso:
    python tools/clean_phantom_archive.py            # dry-run (default, no escribe)
    python tools/clean_phantom_archive.py --apply    # aplica

Requiere MT5 abierto. Escribe un CSV con todo lo borrado antes de borrar.
"""
import os
import sys
import csv
import sqlite3
import datetime

APPLY = '--apply' in sys.argv
DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
PIP = 0.0001


def load_broker_deals():
    """{strategy_id: {'pnl':..,'open':..,'close':..,'position':..}} desde el historial real."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise SystemExit(f"MT5 no inicializo ({mt5.last_error()}). Sin broker no se borra nada.")
    frm, to = datetime.datetime(2026, 1, 1), datetime.datetime.now() + datetime.timedelta(days=1)
    deals = mt5.history_deals_get(frm, to) or []
    if not deals:
        mt5.shutdown()
        raise SystemExit("El historial de MT5 vino VACIO. Abortado (no se puede verificar).")
    times = [d.time for d in deals]
    span = (datetime.datetime.fromtimestamp(min(times)).date(),
            datetime.datetime.fromtimestamp(max(times)).date())
    out = {}
    for d in deals:
        cm = d.comment or ''
        if 'AIdan #' not in cm:
            continue
        try:
            sid = int(''.join(ch for ch in cm.split('AIdan #')[1] if ch.isdigit()))
        except Exception:
            continue
        out.setdefault(sid, set()).add(d.position_id)
    detail = {}
    for sid, pids in out.items():
        pnl, op, cl = 0.0, 0.0, 0.0
        for pid in pids:
            for d in (mt5.history_deals_get(position=pid) or []):
                pnl += d.profit + d.swap + d.commission
                if d.entry == 0:
                    op = d.price
                elif d.entry == 1:
                    cl = d.price
        detail[sid] = {'pnl': round(pnl, 2), 'open': op, 'close': cl, 'positions': sorted(pids)}
    mt5.shutdown()
    return detail, span


def main():
    conn = sqlite3.connect(DB, timeout=15.0)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""SELECT * FROM trade_archive WHERE mt5_pnl IS NULL
                           ORDER BY created_at""").fetchall()
    if not rows:
        print("No hay filas sin mt5_pnl. Nada que hacer.")
        return
    print(f"filas sin mt5_pnl: {len(rows)}")

    broker, span = load_broker_deals()
    print(f"historial MT5: {span[0]} -> {span[1]} | {len(broker)} strategies con deal\n")

    # Control de sanidad: el matcheo por comentario tiene que encontrar las filas que SI
    # tienen P&L. Si falla, el matcheo no es confiable y no se borra nada.
    ctrl = conn.execute("""SELECT strategy_id FROM trade_archive WHERE mt5_pnl IS NOT NULL
                           AND created_at >= ? ORDER BY created_at DESC LIMIT 30""",
                        (str(span[0]),)).fetchall()
    hit = sum(1 for r in ctrl if r['strategy_id'] in broker)
    print(f"CONTROL matcheo por comentario: {hit}/{len(ctrl)} filas con P&L real tienen deal")
    if len(ctrl) and hit < len(ctrl) * 0.9:
        raise SystemExit("El matcheo por comentario NO es confiable (<90%). Abortado.")

    too_old = [r for r in rows if r['created_at'][:10] < str(span[0])]
    if too_old:
        raise SystemExit(f"{len(too_old)} filas son anteriores al historial de MT5 "
                         f"({span[0]}) => no verificables. Abortado.")

    to_delete, to_fix = [], []
    for r in rows:
        sid = r['strategy_id']
        pmn = conn.execute("SELECT COUNT(*) FROM position_manager_log WHERE strategy_id=?",
                           (sid,)).fetchone()[0]
        a = conn.execute("SELECT mt5_ticket, mt5_pnl FROM auto_strategies WHERE id=?",
                         (sid,)).fetchone()
        has_row_ev = bool(a and (a['mt5_ticket'] or a['mt5_pnl'] is not None))
        if sid in broker or pmn > 0 or has_row_ev:
            to_fix.append((r, broker.get(sid), pmn))
        else:
            to_delete.append(r)

    print(f"\n=== {len(to_fix)} filas CON evidencia -> se COMPLETAN con el broker ===")
    fixes = []
    for r, b, pmn in to_fix:
        sid = r['strategy_id']
        if not b:
            print(f"  #{sid} {r['created_at'][:10]} {r['trigger_type']}: hay rastro "
                  f"(PM={pmn}) pero NO hay deal => se DEJA COMO ESTA (ni borrar ni completar)")
            continue
        real_pips = ((b['close'] - b['open']) if r['direction'] == 'CALL'
                     else (b['open'] - b['close'])) / PIP
        coherent = (b['pnl'] > 0) == (r['result'] == 'win')
        print(f"  #{sid} {r['created_at'][:10]} {r['trigger_type']:<14} {r['result']:<5} "
              f"pips {r['pips']:+7.1f} (teorico) -> {real_pips:+7.1f} (real) | "
              f"P&L ${b['pnl']:+.2f} | exit {r['exit_price']} -> {b['close']}"
              f"{'' if coherent else '   *** INCOHERENTE ***'}")
        if not coherent:
            raise SystemExit(f"#{sid}: result='{r['result']}' pero el broker dice ${b['pnl']}. "
                             f"NO se relabelea automaticamente (precedente #658). Abortado.")
        fixes.append((sid, b['pnl'], b['close'], round(real_pips, 1)))

    print(f"\n=== {len(to_delete)} filas FANTASMA -> se BORRAN ===")
    for r in to_delete:
        print(f"  #{r['strategy_id']} {r['created_at'][:10]} {r['trigger_type']:<14} "
              f"{r['result']:<5} {r['pips']:+7.1f}p (teoricos)")

    # CSV de respaldo (siempre, tambien en dry-run)
    outdir = os.path.join(os.environ['APPDATA'], 'AIdan', 'backups')
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, 'phantom_rows_removed.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        for r in to_delete:
            w.writerow(dict(r))
    print(f"\nrespaldo de las borradas -> {csv_path}")

    if not APPLY:
        print("\nDRY-RUN. Nada se escribio. Re-correr con --apply para aplicar.")
        return

    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        for sid, pnl, close_px, real_pips in fixes:
            cur.execute("""UPDATE trade_archive SET mt5_pnl=?, exit_price=?, pips=?
                           WHERE strategy_id=? AND mt5_pnl IS NULL""",
                        (pnl, close_px, real_pips, sid))
        ids = [r['strategy_id'] for r in to_delete]
        cur.executemany("DELETE FROM trade_archive WHERE strategy_id=? AND mt5_pnl IS NULL",
                        [(i,) for i in ids])
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise SystemExit(f"ROLLBACK por error: {e}")

    tot = conn.execute("SELECT COUNT(*) FROM trade_archive").fetchone()[0]
    left = conn.execute("SELECT COUNT(*) FROM trade_archive WHERE mt5_pnl IS NULL").fetchone()[0]
    print(f"\nAPLICADO. trade_archive: {tot} filas | sin mt5_pnl: {left}")
    conn.close()


if __name__ == '__main__':
    main()
