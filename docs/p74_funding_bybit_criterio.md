# P74 — Carry de funding de P15 en Bybit, reglas congeladas: criterio declarado ANTES de medir (25-nov-2026)

**Pregunta:** P15 (spot comprado + perpetuo vendido, Binance) es lo único que pasó en el proyecto. ¿La MISMA regla,
sin tocar nada, también rinde más que la tasa libre de riesgo con los datos de otro exchange (Bybit)? Es una prueba
fuera de muestra de la idea (otro libro de órdenes, otra base de clientes, otro funding) y, si pasa, otra contraparte
para la cartera. Tipo **A** (premio por riesgo).

## Datos (solo se verificó que la API responde; ningún funding ni precio mirado antes de declarar)
- API pública v5 de Bybit, sin cuenta: `/v5/market/funding/history` (category=linear) y `/v5/market/kline`
  (category=spot y linear, intervalo 240 min; Bybit no tiene velas de 8 h ⇒ se toman los open de las velas de las
  00/08/16 UTC, que son el open de la vela de 8 h). Cache `.cache_p74/`.
- **Monedas:** BTC, ETH, SOL (USDT). Desde la primera marca en que existen las tres series (funding, spot y
  perpetuo) de cada moneda hasta el 24-nov-2026.

## Regla (la de P15, sin cambios; el simulador se IMPORTA de `tools/backtest_p15_funding.py`)
- Decisión cada 8 h; señal = funding sumado de los últimos 7 días / 21 (por 8 h, vale aunque el intervalo de cobro
  de Bybit sea otro); entrar si ≥ 0,005%, salir si < 0.
- Spot comprado + perpetuo vendido al mismo nocional; funding real ponderado por precio; rebalanceo (cerrar y
  reabrir) si el spot se mueve ±50%; capital 2 × nocional; ranura sin posición rinde 0.
- **Costo:** 0,38% del nocional por ida y vuelta (el de P15). Descriptivo: con las comisiones taker de Bybit
  (spot 0,10%, perpetuo 0,055%) da 0,39%.

## Criterio de PASA (los 5 de P15, cartera de las 3 monedas con una ranura igual cada una)
1. Rendimiento neto anualizado > tasa libre de riesgo media del período (`docs/p11_policy_rates.csv`).
2. CI95 bootstrap por bloques de una semana del rendimiento medio: inferior > 0 (5000, semilla 20261125).
3. Anualizado > 0 en las dos mitades cronológicas.
4. Caída máxima de la cartera < 10%.
5. ≥ 2 de 3 monedas con resultado neto > 0.

## Descriptivo (no decide)
Por año, funding vs base vs costos, "siempre adentro", y la misma ventana de fechas con los datos de Binance de
P15 (`.cache_p15`) para comparar; correlación diaria del resultado Bybit vs Binance.

## Límites
- Riesgo de exchange no modelado. Velas de 4 h para aproximar las de 8 h (mismo open). El spot de Bybit arranca más
  tarde que el de Binance ⇒ período más corto y sin el 2020-21 de funding alto.
- Reservas: no hay (es en sí una prueba fuera de muestra con reglas congeladas).

## Si PASA
No se activa nada. Entra a `docs/cartera_de_lo_que_pasa.md` como "réplica en otro exchange" y se propone sumar el
libro de Bybit al papel de P19 (OK del user).
## Si NO PASA
Se anota que P15 no replica en Bybit (dato en contra de la idea, no solo del exchange); no se cambia ninguna regla
para que pase.
