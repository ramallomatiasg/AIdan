"""
confidence_calibration.py — v3.59.0: P(win) calibrada (Platt) en FASE REGISTRO.

Por que existe: la confianza cruda NO es una probabilidad (Brier 0.36-0.43 vs
0.23 de predecir una constante — medido en calibrate_confidence.py, 5-ago y
20-ago). El 20-ago, con 309 trades limpios, la calibracion de Platt PASO por
primera vez su gate pre-declarado en UN track:

    m15_structure: Brier held-out 0.2214 < gate 0.230 y < constante 0.2342

Que hace este modulo: aplica esa calibracion con los parametros CONGELADOS del
fit que paso el gate (entrenado sobre trades hasta 2026-07-28) y devuelve la
P(win) para que add_auto_strategy la REGISTRE en entry_context.calibrated_p.

Que NO hace: no toca ninguna decision. No filtra, no ajusta confianza, no toca
el lote. Es la fase registro acordada el 20-ago: 2-3 semanas guardando la
prediccion clasificada EN EL MOMENTO, y despues se lee con
tools/score_calibrated_p_forward.py contra el gate pre-declarado.

Por que los parametros van CONGELADOS y no re-fiteados: si el fit se moviera
con cada trade nuevo, el forward dejaria de ser un held-out honesto (la
prediccion de hoy estaria entrenada con la data de ayer del mismo periodo que
se va a evaluar). Congelar = lo que se mide es EXACTAMENTE lo que paso el gate.

Limite declarado: el test que paso el gate son ~29 filas y el modelo quedo
sobre-confiado en todos los buckets (predicha > real). Por eso registro y no
activacion. Si el forward no sostiene, este modulo se borra y listo.
"""
import math

# Parametros del fit que PASO el gate (calibrate_confidence.py, 20-ago-2026).
# fit_platt() estandariza conf con (mu, sd) del train y aplica sigmoid(a*z + b).
# train: trades limpios m15_structure desde CLEAN_FROM=2026-06-20 hasta
# 2026-07-28 (n=65, WR 46.15%). Held-out: n=29, Brier 0.2214.
FROZEN_PARAMS = {
    'm15_structure': {
        'a': 0.341758,
        'b': -0.160627,
        'mu': 79.923077,
        'sd': 10.148600,
        'train_wr': 0.461538,   # la constante a batir en el forward
        'fitted_at': '2026-08-20',
        'train_until': '2026-07-28',
        # desde cuando el hook esta VIVO en el exe (para el tripwire del scorer:
        # senal creada despues de esto sin calibrated_p = hook muerto)
        'deployed_at': '2026-08-21',
    },
}


def calibrated_p(trigger_type, confidence):
    """P(win) calibrada para la confianza FINAL (post-ajustes meta/retro).

    Devuelve float en (0,1) solo para tracks con parametros congelados que
    pasaron el gate; None para todo lo demas (None = "no hay calibracion",
    nunca 0.5 — un default plausible enmascararia el track sin calibrar).
    """
    params = FROZEN_PARAMS.get(trigger_type)
    if params is None or confidence is None:
        return None
    try:
        z = (float(confidence) - params['mu']) / (params['sd'] or 1.0)
        return round(1.0 / (1.0 + math.exp(-(params['a'] * z + params['b']))), 4)
    except (TypeError, ValueError, OverflowError):
        return None
