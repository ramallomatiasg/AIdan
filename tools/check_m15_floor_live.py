"""
check_m15_floor_live.py — ¿el piso de ATR de m15 (v3.55.0) esta MORDIENDO de verdad?

READ-ONLY. Lee el log de AIdan (+ rotaciones) y la DB. No escribe nada, no toca MT5.

═══ QUE PREGUNTA RESPONDE ════════════════════════════════════════════════════

No alcanza con "el exe arranco y la env var vale 8". Eso ya se verifica con
tools/test_m15_atr_floor_v3550.py y mirando /version. Lo que este script busca es
la evidencia de que la perilla CAMBIA EL COMPORTAMIENTO en datos reales, y hay
una sola franja donde eso se puede ver:

    ATR entre 5.0 y 8.0  ->  el piso VIEJO dejaba escanear, el NUEVO frena.

Debajo de 5 los dos frenan (no distingue nada) y arriba de 8 los dos dejan pasar.
Por eso el veredicto se apoya en el conteo de esa banda y no en el total de skips:
un domingo a la noche con ATR 2.8p produce muchisimos skips y NO prueba nada.

═══ POR QUE IMPORTA MIRARLO TEMPRANO ═════════════════════════════════════════

El forward de la perilla se lee ~1 sep. Si por algun motivo no muerde (el exe no
encontro el .env, el bloque quedo en una rama muerta, el warmup se come el ciclo),
enterarse en 2 semanas cuesta 2 semanas. Esto se contesta el primer dia activo.

Uso:
    python tools/check_m15_floor_live.py
    python tools/check_m15_floor_live.py --desde 2026-08-17
"""
import argparse
import glob
import os
import re
import sqlite3
import sys
from collections import Counter

APPDATA = os.environ.get('APPDATA', '')
LOG_DIR = os.path.join(APPDATA, 'AIdan', 'logs')
DB = os.path.join(APPDATA, 'AIdan', 'state', 'financial_news.db')

# La linea que emite el loop (AIdan_TodoEnUno.py, bloque M15).
RE_SKIP = re.compile(
    r'^(\d{4}-\d{2}-\d{2}) [\d:]+ .*M15: ATR ([\d.]+)p < piso ([\d.]+)p')
# Contraprueba: si m15 SI escaneo, el analyzer loguea su fetch.
RE_SCAN = re.compile(r'^(\d{4}-\d{2}-\d{2}) [\d:]+ .*Technical M15: \d+ candles')

ACTIVACION = '2026-08-16'   # dia en que se puso M15_ATR_FLOOR=8.0


def leer_logs(desde):
    """Todas las rotaciones, de la mas vieja a la mas nueva."""
    files = sorted(glob.glob(os.path.join(LOG_DIR, 'aidan.log*')),
                   key=lambda p: (0 if p.endswith('.log') else -int(p.rsplit('.', 1)[-1])))
    skips, scans = [], []
    for f in files:
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    m = RE_SKIP.match(line)
                    if m and m.group(1) >= desde:
                        skips.append((m.group(1), float(m.group(2)), float(m.group(3))))
                        continue
                    m2 = RE_SCAN.match(line)
                    if m2 and m2.group(1) >= desde:
                        scans.append(m2.group(1))
        except OSError as e:
            print(f"  (no se pudo leer {os.path.basename(f)}: {e})")
    return skips, scans


def trades_m15(desde):
    if not os.path.isfile(DB):
        return None
    c = sqlite3.connect('file:' + DB + '?mode=ro', uri=True)
    q = """SELECT COUNT(*), COUNT(DISTINCT date(created_at)),
                  ROUND(MIN(avg_range_pips),1), ROUND(SUM(mt5_pnl),2)
           FROM trade_archive
           WHERE trigger_type='m15_structure' AND date(created_at) >= ?"""
    return c.execute(q, (desde,)).fetchone()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--desde', default=ACTIVACION,
                    help=f'fecha YYYY-MM-DD (default {ACTIVACION}, dia de activacion)')
    args = ap.parse_args()

    print('=' * 72)
    print(f'¿MUERDE EL PISO DE ATR DE M15?  (desde {args.desde})')
    print('=' * 72)

    skips, scans = leer_logs(args.desde)
    if not skips and not scans:
        print('\nNo hay actividad de m15 en el log desde esa fecha.')
        print('Posibles causas: AIdan no corrio, o sigue en el warmup de 30 min.')
        return 2

    pisos = Counter(s[2] for s in skips)
    banda = [s for s in skips if 5.0 <= s[1] < 8.0]      # LA evidencia
    bajo5 = [s for s in skips if s[1] < 5.0]             # no distingue nada

    print(f'\n  skips logueados  : {len(skips)}   (se loguea 1 por hora, no 1 por ciclo)')
    print(f'  scans de m15     : {len(scans)}')
    print(f'  piso reportado   : {dict(pisos) or "—"}')

    print('\n  DESGLOSE POR ATR:')
    print(f'    ATR < 5.0p        : {len(bajo5):4d} skips  <- el piso VIEJO tambien frenaba: no prueba nada')
    print(f'    ATR 5.0 - 8.0p    : {len(banda):4d} skips  <- EVIDENCIA: antes pasaba, ahora frena')

    if banda:
        vals = sorted(s[1] for s in banda)
        dias = sorted({s[0] for s in banda})
        print(f'      ATR de esos skips: {vals[:12]}{" ..." if len(vals) > 12 else ""}')
        print(f'      dias             : {", ".join(dias)}')

    t = trades_m15(args.desde)
    if t:
        n, dias, atr_min, pnl = t
        print(f'\n  TRADES de m15 desde {args.desde}: n={n} en {dias} dia(s)  PnL={pnl if pnl is not None else 0:+}')
        if atr_min is not None:
            print(f'    ATR minimo de un trade que SI entro: {atr_min}p', end='')
            if atr_min < 8.0:
                print('   <-- OJO: entro por debajo del piso, la perilla NO esta mordiendo')
            else:
                print('   (consistente con el piso 8.0)')

    print('\n' + '-' * 72)
    if pisos and 8.0 not in pisos and 5.0 in pisos:
        print('VEREDICTO: el loop esta usando piso 5.0 => el .env NO llego al exe.')
        return 1
    if banda:
        print('VEREDICTO: MUERDE. Hay skips en la franja 5-8p, que es exactamente lo que')
        print('           el piso viejo dejaba pasar. La perilla cambia el comportamiento.')
        return 0
    print('VEREDICTO: TODAVIA NO SE PUEDE DECIR. Hubo actividad pero ningun skip en la')
    print('           franja 5-8p: el mercado no paso por ahi todavia (o estuvo siempre')
    print('           debajo de 5, o siempre arriba de 8). Volver a correr tras unas')
    print('           horas de sesion activa (London/NY).')
    return 3


if __name__ == '__main__':
    sys.exit(main())
