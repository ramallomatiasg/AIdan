"""
trendiness_er.py — Efficiency Ratio (Kaufman) por par, solo desde PRECIO.

READ-ONLY. No mira resultados de estrategia: por construccion no puede estar
contaminado por performance. Eso es lo que lo hace usable como predictor
registrado de antemano.

═══ QUE MIDE ════════════════════════════════════════════════════════════════

    ER(W) = |close[t] - close[t-W]|  /  Σ |close[i] - close[i-1]|

Numerador = cuanto se movio NETO en la ventana. Denominador = cuanto camino
recorrio para lograrlo. ER cerca de 1 = fue derecho (tendencia). ER cerca de 0 =
dio vueltas y volvio (rango/chop).

Se promedia el ER sobre todas las ventanas rolling de W dias de las 2000 velas.

═══ POR QUE ESTA METRICA Y POR QUE W=20 ══════════════════════════════════════

El track D1 tiene hold de 10 velas. Se declara W=20 (2x el hold) porque el setup
necesita que la direccion persista MAS ALLA del horizonte de salida para que el
TP se alcance. W=10 y W=40 se reportan solo como robustez; la prediccion usa 20.

Declarado ANTES de correr el backtest sobre los pares nuevos. Ver
docs/fase1b_prediccion_registrada.md.

Uso:
    python tools/trendiness_er.py
    python tools/trendiness_er.py --symbols CHFJPY,GBPCAD
"""
import argparse
import json
import os
import statistics as st
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

CANDLES = 2000
WINDOWS = [10, 20, 40]
W_DECLARADA = 20

# Los 15 con historia completa de la corrida de Fase 1 (resultados YA vistos).
VISTOS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCHF', 'USDJPY',
          'EURGBP', 'EURJPY', 'EURCHF', 'EURAUD', 'EURCAD', 'EURNZD',
          'GBPJPY', 'GBPCHF', 'GBPAUD']
# Los que nunca se midieron y tienen 7,7 años. Conjunto OUT-OF-SAMPLE.
NUEVOS = ['CHFJPY', 'GBPCAD', 'GBPNZD', 'NZDCAD', 'NZDCHF', 'NZDJPY']


def closes(sym, count=CANDLES):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f'MT5 init failed: {mt5.last_error()}')
    mt5.symbol_select(sym, True)
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, count)
    if r is None or len(r) < 400:
        return None
    return [float(x['close']) for x in r], (r[-1]['time'] - r[0]['time']) / 86400.0


def er(cl, w):
    """ER promedio sobre todas las ventanas rolling de w dias."""
    out = []
    for i in range(w, len(cl)):
        neto = abs(cl[i] - cl[i - w])
        camino = sum(abs(cl[j] - cl[j - 1]) for j in range(i - w + 1, i + 1))
        if camino > 0:
            out.append(neto / camino)
    return st.mean(out) if out else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbols', default=','.join(VISTOS + NUEVOS))
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]

    print('=' * 74)
    print('EFFICIENCY RATIO (solo precio, ciego a resultados de estrategia)')
    print('=' * 74)
    print(f'ventana declarada para la prediccion: W={W_DECLARADA}')
    print()
    print(f"{'par':9s}{'grupo':13s}" + ''.join(f'{"ER"+str(w):>9s}' for w in WINDOWS) + f"{'años':>7s}")

    res = {}
    for s in syms:
        got = closes(s)
        if got is None:
            print(f'{s:9s} sin velas suficientes')
            continue
        cl, span = got
        vals = {w: er(cl, w) for w in WINDOWS}
        grupo = 'VISTO' if s in VISTOS else ('out-of-sample' if s in NUEVOS else '?')
        res[s] = {'er': {str(k): round(v, 4) for k, v in vals.items()},
                  'span_days': round(span), 'grupo': grupo}
        print(f'{s:9s}{grupo:13s}'
              + ''.join(f'{vals[w]:>9.4f}' for w in WINDOWS)
              + f'{span/365:>7.1f}')

    out = os.path.join(ROOT, 'trendiness_er.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(f'\nJSON: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
