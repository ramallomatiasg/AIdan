"""
sim_engine.py — Motor de simulacion de SL/TP/expiry para shadow mode y backtest.

Refactor de tools/backtest_h1_m15.py:simulate_signal_outcome() para reuso desde:
- tools/backtest_h1_m15.py (backtest historico)
- src/optimizer/shadow_runner.py (shadow mode en vivo)
- src/optimizer/auto_tuner.py (futuro: walk-forward validation)

Conservative: si una vela toca SL y TP en mismo bar, asumimos SL primero.
"""
from typing import List, Dict, Optional


def simulate_signal_outcome(
    entry_idx: int,
    candles: List[Dict],
    direction: str,
    sl_pips: float,
    tp_pips: float,
    expiry_minutes: int,
    tf_minutes: int,
    pip_value: float = 0.0001,
) -> Dict:
    """
    Walk forward desde entry_idx+1 detectando SL/TP/expiry hit.

    Args:
        entry_idx: indice de la vela de entry en `candles`
        candles: lista de dicts con keys open/high/low/close (datetime opcional)
        direction: 'CALL' (long) o 'PUT' (short)
        sl_pips: distancia del SL en pips
        tp_pips: distancia del TP en pips
        expiry_minutes: maximo tiempo a esperar (min)
        tf_minutes: minutos por vela (5 para M5, 15 para M15, 60 para H1)
        pip_value: tamaño de 1 pip en precio (default EUR/USD = 0.0001)

    Returns:
        dict {
            result: 'tp' | 'sl' | 'expiry' | 'skip',
            exit_idx: int (indice de vela de salida),
            exit_price: float,
            pips: float (positivo si gana, negativo si pierde),
            exit_reason: str (alias de result para clarity)
        }
    """
    if entry_idx < 0 or entry_idx >= len(candles):
        return {'result': 'skip', 'exit_idx': entry_idx, 'exit_price': 0,
                'pips': 0, 'exit_reason': 'invalid_entry'}

    entry = candles[entry_idx]
    entry_price = entry['close']

    if direction == 'CALL':
        sl_price = entry_price - sl_pips * pip_value
        tp_price = entry_price + tp_pips * pip_value
    elif direction == 'PUT':
        sl_price = entry_price + sl_pips * pip_value
        tp_price = entry_price - tp_pips * pip_value
    else:
        return {'result': 'skip', 'exit_idx': entry_idx, 'exit_price': entry_price,
                'pips': 0, 'exit_reason': 'invalid_direction'}

    expiry_candles = max(1, int(expiry_minutes / max(1, tf_minutes)))
    end_idx = min(entry_idx + 1 + expiry_candles, len(candles))

    for j in range(entry_idx + 1, end_idx):
        c = candles[j]
        if direction == 'CALL':
            sl_hit = c['low'] <= sl_price
            tp_hit = c['high'] >= tp_price
        else:  # PUT
            sl_hit = c['high'] >= sl_price
            tp_hit = c['low'] <= tp_price

        # Conservative: si ambos hit en mismo bar, SL primero
        if sl_hit and tp_hit:
            return {'result': 'sl', 'exit_idx': j, 'exit_price': sl_price,
                    'pips': -float(sl_pips), 'exit_reason': 'sl'}
        if tp_hit:
            return {'result': 'tp', 'exit_idx': j, 'exit_price': tp_price,
                    'pips': float(tp_pips), 'exit_reason': 'tp'}
        if sl_hit:
            return {'result': 'sl', 'exit_idx': j, 'exit_price': sl_price,
                    'pips': -float(sl_pips), 'exit_reason': 'sl'}

    # Expiry: cerramos al close de la ultima vela
    if end_idx <= entry_idx + 1:
        # Caso edge: no hay velas futuras
        return {'result': 'expiry', 'exit_idx': entry_idx, 'exit_price': entry_price,
                'pips': 0, 'exit_reason': 'expiry_no_data'}

    last = candles[end_idx - 1]
    if direction == 'CALL':
        pips = (last['close'] - entry_price) / pip_value
    else:
        pips = (entry_price - last['close']) / pip_value
    return {'result': 'expiry', 'exit_idx': end_idx - 1, 'exit_price': last['close'],
            'pips': round(float(pips), 1), 'exit_reason': 'expiry'}


def simulate_pnl_dollars(pips: float, lot: float = 0.01, pip_value_usd: float = 1.0) -> float:
    """Convertir pips a USD asumiendo lot size.
    EUR/USD: 1 pip × 0.01 lot ≈ $0.10. 1 pip × 0.1 lot ≈ $1.0. 1 pip × 1.0 lot ≈ $10.
    Aproximacion lineal: pnl_usd = pips * lot * 10 (con default pip_value_usd=1.0 y lot=0.01 → factor 0.1).

    Args:
        pips: pips ganados (negativo si perdida)
        lot: lot size (e.g., 0.01, 0.06, etc.)
        pip_value_usd: valor de 1 pip en USD para 1 lot estandar (default 10 para EUR/USD)
    """
    return round(pips * lot * 10 * pip_value_usd, 2)


def fetch_candles_for_simulation(interval: str, count: int = 200, logger=None) -> Optional[List[Dict]]:
    """Wrapper sobre price_feed.fetch_candles para simulacion shadow mode.

    Returns ultimas `count` candles del interval (M5/M15/H1). Mismo formato
    que devuelve fetch_candles: list de {open, high, low, close, datetime}.
    """
    try:
        from src.common.price_feed import fetch_candles
        candles = fetch_candles(interval=interval, count=count, logger=logger)
        return candles
    except Exception as e:
        if logger:
            logger.warning(f"sim_engine fetch_candles failed: {e}")
        return None
