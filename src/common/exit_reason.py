# -*- coding: utf-8 -*-
"""
exit_reason.py — v3.64.0. Motivo REAL por el que cerro un trade.

POR QUE EXISTE
--------------
`tp_hit` se derivaba de `result == 'win'` (db.py:3542), o sea no observaba nada:
coincidia con win/loss en 88/88 filas del archivo y de 33 trades marcados "TP hit"
solo 4 habian tocado su TP. Con eso no se puede contestar la unica pregunta que
importa hoy: de los ganadores que salen en +2,6p contra un objetivo de 8p, cuantos
los corto el trailing/BE, cuantos el expiry, y cuantos llegaron de verdad.

DISENO
------
1. La palabra del BROKER manda. MT5 marca cada deal de cierre con `reason`
   (SL / TP / EXPERT / CLIENT...). Eso es verdad observada, no inferencia, y ya
   viene en los deals que `sync_closed_positions` baja igual.
2. Se guardan DOS cosas: la clasificacion (`exit_reason`) y el codigo crudo
   (`exit_reason_raw`). El error de `tp_hit` fue exactamente guardar un derivado sin
   el dato que lo respalda: si la clasificacion resulta estar mal, con el crudo se
   re-deriva; sin el crudo no se recupera nada.
3. UNA sola ambiguedad real: el broker reporta `DEAL_REASON_SL` tanto para el SL
   original como para un stop MOVIDO por el trailing/BE — y distinguirlos es
   justamente el objetivo. Se resuelve comparando el precio de cierre contra el SL
   ORIGINAL: si cerro del lado FAVORABLE del SL original, el stop habia sido movido
   (`trail_be`); si cerro en el SL o peor (gap/slippage), es `sl`. Sin SL original no
   se adivina: se devuelve `sl`, que es lo que dijo el broker.
4. Lista CERRADA de valores. Un valor suelto lo ignoraria el scorer en silencio, que
   es la clase de bug que ya mato a M15, SMC y al reversal en este proyecto.
5. Fail-safe total: cualquier input raro devuelve 'unknown'. Este modulo corre dentro
   del path de archivado y el archivo es la verdad historica del proyecto — perder un
   trade por un TypeError seria mucho peor que no saber por que cerro.

Puro: sin I/O, sin DB, sin MetaTrader5. Testeable sin broker (por eso las constantes
estan copiadas y hay un test que las compara contra el paquete real si esta instalado).
"""

# Constantes de MT5 (ENUM_DEAL_REASON). Copiadas a proposito para no importar el
# paquete: este modulo tiene que poder correr en tests mientras AIdan.exe esta vivo.
DEAL_REASON_CLIENT = 0
DEAL_REASON_MOBILE = 1
DEAL_REASON_WEB = 2
DEAL_REASON_EXPERT = 3
DEAL_REASON_SL = 4
DEAL_REASON_TP = 5
DEAL_REASON_SO = 6

#: Lista CERRADA. Nada fuera de aca puede llegar a la DB.
EXIT_REASONS = (
    'tp',        # toco el take profit
    'sl',        # toco el stop loss ORIGINAL (o peor, por gap/slippage)
    'trail_be',  # cerro en un stop MOVIDO a favor (trailing / break-even)
    'expiry',    # se vencio el tiempo sin tocar ninguna barrera
    'manager',   # lo cerro el position manager
    'kill',      # kill switch / cierre masivo (pre-close del viernes, /kill)
    'aidan',     # orden de AIdan sin poder precisar cual de las tres de arriba
    'stopout',   # stop out del broker (margen)
    'manual',    # lo cerro una persona desde la terminal/app
    'unknown',   # no se pudo determinar — se cuenta, no se adivina
)

#: Valores con los que un caller puede refinar un cierre propio de AIdan.
_REFINAMIENTOS_AIDAN = ('expiry', 'manager', 'kill')

#: Tolerancia por defecto, en pips, para decidir si el cierre fue "en el SL".
#: Cubre spread + slippage normales de esta cuenta (comision ~1,3p de referencia).
_TOL_PIPS = 1.5
_PIP = 0.0001


def _num(x):
    """float finito o None. Rechaza bool a proposito (True se colaria como 1.0)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):  # NaN / inf
        return None
    return v


def classify_from_broker_deal(broker_reason=None, close_price=None, orig_sl=None,
                              orig_tp=None, direction=None, aidan_reason=None,
                              sl_moved=None, tol_pips=_TOL_PIPS):
    """Clasifica un cierre a partir del deal del broker.

    Devuelve `(exit_reason, exit_reason_raw)`, donde `exit_reason` esta SIEMPRE en
    EXIT_REASONS y `exit_reason_raw` es el codigo crudo de MT5 (o None).

    `aidan_reason` solo refina un cierre que el broker ya atribuyo a AIdan
    (DEAL_REASON_EXPERT). NUNCA pisa la palabra del broker: si el broker dice TP, fue
    TP, aunque el caller crea otra cosa.
    """
    try:
        raw = broker_reason if isinstance(broker_reason, int) and not isinstance(broker_reason, bool) else None

        if raw is None:
            return 'unknown', None

        if raw == DEAL_REASON_TP:
            return 'tp', raw

        if raw == DEAL_REASON_SO:
            return 'stopout', raw

        if raw in (DEAL_REASON_CLIENT, DEAL_REASON_MOBILE, DEAL_REASON_WEB):
            return 'manual', raw

        if raw == DEAL_REASON_EXPERT:
            if aidan_reason in _REFINAMIENTOS_AIDAN:
                return aidan_reason, raw
            return 'aidan', raw

        if raw == DEAL_REASON_SL:
            return _clasificar_sl(close_price, orig_sl, direction, tol_pips, sl_moved), raw

        return 'unknown', raw
    except Exception:
        # Fail-safe: el archivado no se rompe por no saber el motivo.
        return 'unknown', None


def _clasificar_sl(close_price, orig_sl, direction, tol_pips, sl_moved=None):
    """SL del broker: era el SL original, o un stop movido a favor?

    Orden de evidencia, de mejor a peor:
      1. `sl_moved` — AIdan REGISTRA si movio el stop (`mt5_trailing_step > 0` en
         auto_strategies, y `stop_loss` en la DB nunca se pisa: guarda el original).
         Es un hecho propio, no una inferencia, asi que manda.
      2. Comparar el precio de cierre contra el SL original (fallback para filas
         viejas o si el dato no llego).
      3. Sin datos: 'sl', la palabra del broker. No se adivina.
    """
    if sl_moved is True:
        return 'trail_be'
    if sl_moved is False:
        return 'sl'

    cp = _num(close_price)
    sl = _num(orig_sl)
    tol = _num(tol_pips)
    if cp is None or sl is None or tol is None or not sl:
        return 'sl'

    d = str(direction or '').upper()
    if d not in ('CALL', 'PUT'):
        return 'sl'

    delta_pips = (cp - sl) / _PIP  # >0 = cierre por ENCIMA del SL original
    if abs(delta_pips) <= tol:
        return 'sl'

    # Lado favorable del SL original => el stop habia sido movido (trailing / BE).
    # Lado adverso => atraveso el SL (gap/slippage): sigue siendo SL.
    if d == 'CALL':
        return 'trail_be' if delta_pips > 0 else 'sl'
    return 'trail_be' if delta_pips < 0 else 'sl'


def classify_from_eval_flags(hit_tp=False, hit_be=False, hit_sl=False,
                             be_triggered=False):
    """Clasifica desde el path de evaluacion por PRECIO (expiry), que no tiene deal
    del broker pero si sabe que barrera creyo tocar.

    Prioridad: TP > BE > SL > expiry. 'expiry' es el residuo — ninguna barrera tocada
    y el trade cerro igual — y es justamente la hipotesis a medir (problema #2 del
    diagnostico: el expiry mata trades direccionalmente correctos).
    """
    try:
        if hit_tp:
            return 'tp'
        if hit_be or be_triggered:
            return 'trail_be'
        if hit_sl:
            return 'sl'
        return 'expiry'
    except Exception:
        return 'unknown'
