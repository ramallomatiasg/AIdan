# -*- coding: utf-8 -*-
"""v3.62.0 — Cache en memoria del ultimo SL aceptado por ticket (thread de trailing).

Por que existe: en run_trailing_monitor el SL "actual" contra el que se compara el
candidato sale de auto_strategies.stop_loss (row[4]), que es el SL ORIGINAL — nunca se
actualiza tras un modify (y no debe: el archive lo usa como sl_pips del plan). Resultado:
mientras el BE estuviera armado, `candidate > sl + MIN_SL_MOVE` era verdadero en CADA
ciclo de 1 segundo => un modify_position_sl + un UPDATE + una linea INFO por segundo por
posicion. El no-op guard de v3.50.1 frenaba el order_send al broker, pero devolvia True,
asi que el thread lo logueaba como exito y escribia la DB igual.

Medido (logs 17-ago a 7-sep): #944 = 9.039 lineas identicas en 2,5 h; #909 = 4.337;
5% de todo el log. El log rotaba cada 2-3 dias y las lecturas retrospectivas (BE de h1)
perdian la evidencia. Cero plata en juego: el broker no recibia nada.

Funciones puras, sin estado global: el dict vive en el thread que las llama.
"""


def sl_already_sent(cache, ticket, new_sl):
    """True si `new_sl` es exactamente el ultimo SL que el broker ya acepto para ese
    ticket. Si el candidato CAMBIO (etapa TRAIL subiendo con el HWM) devuelve False."""
    if not cache or ticket is None or new_sl is None:
        return False
    last = cache.get(ticket)
    return last is not None and round(last, 5) == round(new_sl, 5)


def remember_sl(cache, ticket, new_sl):
    """Registra el SL aceptado. Llamar SOLO tras un modify exitoso: si el broker rechazo,
    el proximo ciclo tiene que volver a intentarlo."""
    cache[ticket] = round(new_sl, 5)


def prune_sl_cache(cache, live_tickets):
    """Saca los tickets que ya no estan abiertos para que el dict no crezca."""
    live = set(live_tickets or ())
    for t in [t for t in cache if t not in live]:
        del cache[t]
