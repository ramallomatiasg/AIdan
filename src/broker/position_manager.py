"""
position_manager.py — Live Position Manager (v3.36.0, Fase 1: reglas sin LLM).

Decide en vivo si una posicion abierta debe MANTENERSE o CERRARSE, reemplazando
el expiry ciego + force-close por mechas re-analizadas (bug observado en #538:
trade direccionalmente correcto cerrado plano al expiry, precio llego cerca del TP
2h despues).

Principios (no se violan nunca):
1. El SL/TP duro de MT5 es la unica salida forzada automatica del broker.
2. Nunca dejar que un ganador se vuelva perdedor (profit-lock).
3. No pagar comision por cerrar plano si todavia puede desarrollarse.
4. Caps duros (MAX_HOLD) ganan siempre.

Este modulo es PURO (sin side-effects, sin I/O): toma un PositionContext y
devuelve una ManagerDecision. El thread que lo invoca (en AIdan_TodoEnUno.py)
se encarga de loguear y, en modo 'active', ejecutar el cierre.
"""
from dataclasses import dataclass

PIP = 0.0001

# ─── Acciones ───
HOLD = 'HOLD'                 # no hacer nada, dejar correr
CLOSE_PROFIT = 'CLOSE_PROFIT'  # tomar ganancia (profit-lock por reversion)
CLOSE_PROTECT = 'CLOSE_PROTECT'  # cortar trade que se deteriora antes del SL
CLOSE_MAXHOLD = 'CLOSE_MAXHOLD'  # cierre final por tiempo maximo
CLOSE_LLM = 'CLOSE_LLM'        # cierre recomendado por el LLM (Fase 2)

CLOSE_ACTIONS = (CLOSE_PROFIT, CLOSE_PROTECT, CLOSE_MAXHOLD, CLOSE_LLM)


@dataclass
class PositionContext:
    """Snapshot de una posicion abierta para evaluar."""
    strategy_id: int
    direction: str            # 'CALL' | 'PUT'
    fill_price: float
    current_price: float
    tp_distance: float        # abs(tp - fill) en precio (>0)
    sl_distance: float        # abs(sl - fill) en precio (>0)
    progress: float           # P&L actual en precio, signado (+ = a favor)
    hwm: float                # high water mark en precio (mejor progress alcanzado, >=0)
    time_in_trade_min: float
    base_expiry_min: float
    max_hold_min: float
    momentum_aligned_pips: float  # momentum reciente en nuestra direccion, en pips (signado)
    atr_pips: float
    trigger_type: str = ''


@dataclass
class ManagerDecision:
    action: str
    reason: str
    progress_pips: float
    hwm_pips: float
    tp_pct: float             # hwm como % del TP distance (0-1+)
    llm_eligible: bool = False  # True en zona ambigua (soft-expiry HOLD): vale consultar LLM


class PositionManager:
    """Evalua posiciones segun reglas R1-R4. Stateless."""

    def __init__(self, profit_lock_arm=0.60, profit_lock_keep=0.60,
                 flat_band_pips=1.0):
        # R1: arma profit-lock cuando HWM >= arm * tp_distance
        self.profit_lock_arm = profit_lock_arm
        # R1: cierra si progress cae a <= keep * HWM (keep=0.60 => retrocedio 40% del pico)
        self.profit_lock_keep = profit_lock_keep
        # Banda de "plano" para R2 (pips alrededor de 0)
        self.flat_band = flat_band_pips * PIP

    def evaluate(self, ctx: PositionContext) -> ManagerDecision:
        progress_pips = ctx.progress / PIP
        hwm_pips = ctx.hwm / PIP
        tp_pct = (ctx.hwm / ctx.tp_distance) if ctx.tp_distance > 0 else 0.0

        def decision(action, reason, llm_eligible=False):
            return ManagerDecision(action, reason, round(progress_pips, 1),
                                   round(hwm_pips, 1), round(tp_pct, 2), llm_eligible)

        # ── R4 — Max hold backstop (prioridad maxima de seguridad) ──
        if ctx.time_in_trade_min >= ctx.max_hold_min:
            return decision(CLOSE_MAXHOLD,
                            f"max hold {ctx.max_hold_min:.0f}min alcanzado "
                            f"(en trade {ctx.time_in_trade_min:.0f}min, P&L {progress_pips:+.1f}p)")

        # ── R1 — Profit-lock on reversal (puede disparar en cualquier momento) ──
        # Llego a >=arm% del TP y retrocedio por debajo de keep% del pico.
        if ctx.tp_distance > 0 and ctx.hwm >= self.profit_lock_arm * ctx.tp_distance:
            if ctx.progress <= self.profit_lock_keep * ctx.hwm:
                return decision(CLOSE_PROFIT,
                                f"profit-lock: HWM {hwm_pips:.1f}p ({tp_pct:.0%} del TP), "
                                f"retrocedio a {progress_pips:+.1f}p")

        # ── Antes del soft-expiry: dejar trabajar ──
        if ctx.time_in_trade_min < ctx.base_expiry_min:
            return decision(HOLD,
                            f"dentro del expiry base ({ctx.time_in_trade_min:.0f}/"
                            f"{ctx.base_expiry_min:.0f}min, P&L {progress_pips:+.1f}p)")

        # ── R2 — Soft-expiry: extender / cortar / aguantar ──
        # Zona ambigua: aca es donde el LLM (Fase 2) aporta juicio -> llm_eligible=True.
        # En ganancia o venia funcionando -> extender
        if ctx.progress >= self.flat_band or ctx.hwm >= 0.5 * ctx.tp_distance:
            return decision(HOLD,
                            f"soft-expiry EXTEND: P&L {progress_pips:+.1f}p HWM {hwm_pips:.1f}p "
                            f"({tp_pct:.0%} del TP) — venia funcionando",
                            llm_eligible=True)
        # Perdiendo + momentum en contra -> cortar antes del SL (definitivo, sin LLM)
        if ctx.progress <= -self.flat_band and ctx.momentum_aligned_pips < 0:
            return decision(CLOSE_PROTECT,
                            f"soft-expiry PROTECT: perdiendo {progress_pips:.1f}p + "
                            f"momentum adverso ({ctx.momentum_aligned_pips:+.1f}p)")
        # Plano -> aguantar hasta SL/TP o MAX_HOLD (no pagar comision por cerrar plano)
        return decision(HOLD,
                        f"soft-expiry FLAT hold: {progress_pips:+.1f}p sin momentum, "
                        f"espera SL/TP o max hold",
                        llm_eligible=True)


def max_hold_for_trigger(trigger_type: str, cfg) -> float:
    """Mapea trigger_type al MAX_HOLD configurado por track."""
    t = (trigger_type or '').lower()
    if 'h1' in t:
        return float(getattr(cfg, 'MAX_HOLD_MIN_H1', 240))
    if 'm15' in t:
        return float(getattr(cfg, 'MAX_HOLD_MIN_M15', 120))
    return float(getattr(cfg, 'MAX_HOLD_MIN_M5', 90))
