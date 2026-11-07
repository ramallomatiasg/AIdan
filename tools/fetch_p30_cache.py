"""P30 — baja velas M15 de índices europeos nunca mirados (STOXX50, FR40, UK100) a .cache_p1/M15.

Solo descarga (no mide nada). Requiere MT5 => correr SOLO con AIdan.exe cerrado. Mismo formato que P1.
"""
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_fase2 as f2  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, '.cache_p1', 'M15')
WANT = ['STOXX50', 'FR40', 'UK100', 'F40', 'EU50', 'UK100.', 'STOXX50.']
COUNT, MIN_N = 150_000, 50_000


def main():
    import MetaTrader5 as mt5
    import numpy as np
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    log = logging.getLogger('p30')
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    names = {s.name for s in (mt5.symbols_get() or [])}
    log.info('candidatos en el broker: %s', sorted(n for n in names if any(k in n.upper() for k in ('STOXX', 'FR40', 'F40', 'UK100', 'EU50', 'CAC', 'FTSE'))))
    os.makedirs(CACHE, exist_ok=True)
    for sym in WANT:
        if sym not in names:
            continue
        mt5.symbol_select(sym, True)
        i = mt5.symbol_info(sym)
        r = f2.fetch_with_retry(mt5, sym, mt5.TIMEFRAME_M15, COUNT, MIN_N, log)
        n = 0 if r is None else len(r)
        if n < MIN_N:
            log.warning('%s: solo %d velas -> excluido', sym, n)
            continue
        np.save(os.path.join(CACHE, f'{sym}.npy'), r)
        meta = {'point': i.point, 'digits': i.digits, 'contract_size': i.trade_contract_size, 'n': n,
                'swap_long': i.swap_long, 'swap_short': i.swap_short, 'swap_mode': i.swap_mode,
                'desde': str(datetime.utcfromtimestamp(int(r[0]['time']))),
                'hasta': str(datetime.utcfromtimestamp(int(r[-1]['time'])))}
        with open(os.path.join(CACHE, f'{sym}.meta.json'), 'w') as f:
            json.dump(meta, f)
        log.info('%s: %d velas %s -> %s', sym, n, meta['desde'], meta['hasta'])
    mt5.shutdown()


if __name__ == '__main__':
    main()
