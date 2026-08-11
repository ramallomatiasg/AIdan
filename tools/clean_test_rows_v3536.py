# -*- coding: utf-8 -*-
"""Limpieza de las filas que un TEST escribio en la DB de produccion (11-ago-2026).

QUE PASO: `tools/test_commission_double_count_v3533.py` corria `sync_closed_positions()`
de verdad con `SID = 999`, parcheando solo 2 de sus write paths. Los otros escribieron en
la DB REAL: `auto_evaluate_strategy` (strategy_results), y el thread de post-trade, que
ademas llamaba al LLM y guardaba en `post_trade_analysis` + `learning_insights`.

POR QUE SE PUEDE BORRAR (regla 5 de la casa = no borrar historico):
mismo criterio que la limpieza de fantasmas del 8-ago. Estas filas NUNCA fueron datos:
  1. `strategy_id = 999` esta POR ENCIMA del maximo id jamas asignado (887). El contador
     de auto_strategies nunca llego ahi => es imposible que sea una estrategia real.
  2. CERO menciones de `#999` en el log del bot (que loguea cada post-trade).
  3. El trade del harness es fijo (entry 1.16000, SL 1.1585 = 15 pips, TP 1.1650) => por
     eso todas las lecciones dicen "Ajustar el SL a 15 pips".
El script ABORTA si cualquiera de (1) o (2) no se cumple.

Los `learning_insights` NO guardan strategy_id => se parean con su fila de
post_trade_analysis por (key_lesson identico) + (timestamp, corrigiendo que `analyzed_at`
es UTC y `created_at` es AR). Si un insight es AMBIGUO (matchea tambien a un post-trade
REAL en la ventana) se DEJA: preferimos que sobre basura antes que borrar un dato bueno.

Uso:
    python tools/clean_test_rows_v3536.py            # dry-run (default)
    python tools/clean_test_rows_v3536.py --apply    # escribe
"""
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
LOG = os.path.join(os.environ['APPDATA'], 'AIdan', 'logs', 'aidan.log')
BACKUP_DIR = os.path.join(os.environ['APPDATA'], 'AIdan', 'backups')
UTC_TO_AR_HOURS = 3          # analyzed_at se sellaba con datetime('now') = UTC
PAIR_TOLERANCE_S = 15        # margen para parear insight <-> post_trade


def _ts(s):
    if not s:
        return None
    s = str(s).split('+')[0].strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def abortar(msg):
    print(f"\n[ABORTA] {msg}")
    sys.exit(2)


def main(apply_changes):
    conn = sqlite3.connect(DB, timeout=20.0)
    conn.row_factory = sqlite3.Row

    # ── 1. Determinar el maximo id REAL jamas asignado ────────────────────────
    maxes = [
        conn.execute("SELECT MAX(id) FROM auto_strategies").fetchone()[0],
        conn.execute("SELECT MAX(strategy_id) FROM trade_archive").fetchone()[0],
    ]
    max_real = max(m for m in maxes if m is not None)
    print(f"Max strategy_id REAL jamas asignado: {max_real}")

    pt = conn.execute(
        "SELECT id, strategy_id, result, key_lesson, analyzed_at FROM post_trade_analysis "
        "WHERE strategy_id > ? ORDER BY id", (max_real,)).fetchall()
    sr = conn.execute(
        "SELECT id, strategy_id, result, pips, recorded_at FROM strategy_results "
        "WHERE strategy_id > ? ORDER BY id", (max_real,)).fetchall()
    print(f"Candidatas (strategy_id > {max_real}): post_trade={len(pt)}  strategy_results={len(sr)}")
    if not pt and not sr:
        print("Nada que limpiar.")
        return

    ids_falsos = sorted({r['strategy_id'] for r in pt} | {r['strategy_id'] for r in sr})
    print(f"strategy_id imposibles: {ids_falsos}")

    # ── 2. Control duro: el bot NUNCA los menciono ────────────────────────────
    if not os.path.exists(LOG):
        abortar(f"no encuentro el log del bot en {LOG} — sin ese control no borro nada")
    texto = open(LOG, encoding='utf-8', errors='replace').read()
    for sid in ids_falsos:
        n = texto.count(f"#{sid}")
        print(f"  menciones de #{sid} en aidan.log: {n}")
        if n:
            abortar(f"#{sid} SI aparece en el log del bot => podria ser real. No se borra nada.")

    # ── 3. Parear los learning_insights con su post_trade ─────────────────────
    # Sin strategy_id: se usa (key_lesson identico) + (timestamp dentro de tolerancia,
    # convirtiendo analyzed_at de UTC a AR). Un insight que ADEMAS matchee un post-trade
    # REAL queda descartado por ambiguo.
    reales = conn.execute(
        "SELECT strategy_id, key_lesson, analyzed_at FROM post_trade_analysis "
        "WHERE strategy_id <= ?", (max_real,)).fetchall()
    insights = conn.execute(
        "SELECT id, created_at, insight FROM learning_insights WHERE category='post_trade'"
    ).fetchall()

    def cerca(a_utc, b_ar):
        t1, t2 = _ts(a_utc), _ts(b_ar)
        if not t1 or not t2:
            return False
        return abs(((t1 - timedelta(hours=UTC_TO_AR_HOURS)) - t2).total_seconds()) <= PAIR_TOLERANCE_S

    ins_falsos, ambiguos = [], []
    for ins in insights:
        m_falso = [p for p in pt if (p['key_lesson'] or '') == (ins['insight'] or '')
                   and cerca(p['analyzed_at'], ins['created_at'])]
        if not m_falso:
            continue
        m_real = [p for p in reales if (p['key_lesson'] or '') == (ins['insight'] or '')
                  and cerca(p['analyzed_at'], ins['created_at'])]
        if m_real:
            ambiguos.append((ins['id'], [p['strategy_id'] for p in m_real]))
            continue
        ins_falsos.append(ins)

    print(f"\nlearning_insights (category=post_trade): {len(insights)} totales")
    print(f"  pareados al test  : {len(ins_falsos)}")
    print(f"  AMBIGUOS (se dejan): {len(ambiguos)}  {ambiguos[:5]}")
    if len(ins_falsos) > len(pt):
        abortar(f"pareo mas insights ({len(ins_falsos)}) que filas de post_trade ({len(pt)}) "
                f"=> el criterio esta mal, no borro nada")

    # ── 4. Efecto sobre la ventana que lee get_learning_adjustments ───────────
    en_48h = conn.execute(
        "SELECT COUNT(*) FROM learning_insights WHERE category='post_trade' "
        "AND created_at > datetime('now','-48 hours')").fetchone()[0]
    ids_f = {i['id'] for i in ins_falsos}
    en_48h_falsos = conn.execute(
        "SELECT id FROM learning_insights WHERE category='post_trade' "
        "AND created_at > datetime('now','-48 hours')").fetchall()
    n_f48 = sum(1 for r in en_48h_falsos if r['id'] in ids_f)
    print(f"\nVentana de 48h que lee get_learning_adjustments: {en_48h} insights, "
          f"{n_f48} del test ({(100*n_f48/en_48h):.0f}%) -> quedarian {en_48h - n_f48}")

    if not apply_changes:
        print("\n=== DRY-RUN. Nada se escribio. Correr con --apply para aplicar. ===")
        print(f"Se borrarian: {len(pt)} post_trade_analysis + {len(sr)} strategy_results "
              f"+ {len(ins_falsos)} learning_insights")
        return

    # ── 5. Backup ANTES de tocar nada ─────────────────────────────────────────
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = _ts(conn.execute("SELECT datetime('now')").fetchone()[0]).strftime('%Y%m%d_%H%M%S')
    bpath = os.path.join(BACKUP_DIR, f'pre_clean_test_rows_{stamp}.db')
    dst = sqlite3.connect(bpath)
    conn.backup(dst)          # consistente con el bot escribiendo (WAL)
    dst.close()
    print(f"\nBackup: {bpath} ({os.path.getsize(bpath)/1e6:.1f} MB)")

    csv_path = os.path.join(BACKUP_DIR, f'test_rows_removed_{stamp}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['tabla', 'row_id', 'strategy_id', 'ts', 'detalle'])
        for r in pt:
            w.writerow(['post_trade_analysis', r['id'], r['strategy_id'], r['analyzed_at'],
                        f"{r['result']} | {r['key_lesson']}"])
        for r in sr:
            w.writerow(['strategy_results', r['id'], r['strategy_id'], r['recorded_at'],
                        f"{r['result']} | {r['pips']}p"])
        for r in ins_falsos:
            w.writerow(['learning_insights', r['id'], '(pareado)', r['created_at'], r['insight']])
    print(f"CSV de respaldo: {csv_path}")

    # ── 6. Borrado transaccional ──────────────────────────────────────────────
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(f"DELETE FROM post_trade_analysis WHERE strategy_id > {int(max_real)}")
        n1 = cur.rowcount
        cur.execute(f"DELETE FROM strategy_results WHERE strategy_id > {int(max_real)}")
        n2 = cur.rowcount
        n3 = 0
        for r in ins_falsos:
            cur.execute("DELETE FROM learning_insights WHERE id = ?", (r['id'],))
            n3 += cur.rowcount
        conn.commit()
        print(f"\nBORRADAS: post_trade_analysis={n1}  strategy_results={n2}  learning_insights={n3}")
    except Exception as e:
        conn.rollback()
        abortar(f"error borrando, ROLLBACK aplicado: {e}")

    ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    resto = conn.execute("SELECT COUNT(*) FROM post_trade_analysis WHERE strategy_id > ?",
                         (max_real,)).fetchone()[0]
    print(f"integrity_check={ok}  |  candidatas restantes={resto}")
    conn.close()


if __name__ == '__main__':
    main('--apply' in sys.argv)
