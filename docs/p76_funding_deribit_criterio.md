# P76 — Carry de funding de P15 en Deribit, reglas congeladas: criterio declarado ANTES de medir (26-nov-2026)

**Pregunta:** ¿la MISMA regla de P15 (spot comprado + perpetuo vendido), sin tocar nada, rinde más que la tasa libre
de riesgo con el funding del perpetuo de **Deribit**? Igual que P74 (Bybit): prueba fuera de muestra de la idea en
otro exchange, con otra base de clientes (institucional) y otra contraparte. Tipo **A** (premio por riesgo).
Prior bajo: P74 mostró que el carry replica clavado entre exchanges y desde 2021 queda debajo de la letra.

## Datos (solo se verificó que la API responde y desde cuándo hay funding; ningún valor mirado más allá)
- API pública de Deribit, sin cuenta: `public/get_funding_rate_history` (BTC-PERPETUAL, ETH-PERPETUAL; campo
  `interest_1h` = funding realizado de cada hora; hay datos desde el 30-abr-2019) y
  `public/get_tradingview_chart_data` (resolución 60 min; se toman los open de las 00/08/16 UTC como precio del perpetuo).
  Cache `.cache_p76/`.
- **Pata spot:** la de P15 (open de 8 h del spot de Binance, cache `.cache_p15/`), como dice la cola. El perpetuo de
  Deribit es inverso (margen en BTC/ETH): un corto de N USD paga en USD `N·(1 − f/f0)`, igual que el corto lineal que
  modela el simulador ⇒ la cobertura se mide en USD con el mismo simulador.
- **Monedas:** BTC y ETH (SOL no tiene perpetuo con historia en Deribit). Desde la primera marca con funding de 7 días
  completo hasta el 22-oct-2026 (fin del cache de spot de P15).

## Regla (la de P15, sin cambios; el simulador se IMPORTA de `tools/backtest_p15_funding.py`)
- Decisión cada 8 h; señal = funding sumado de los últimos 7 días / 21; entrar si ≥ 0,005%, salir si < 0.
- Funding cobrado = suma de los `interest_1h` horarios, ponderado por el precio del perpetuo; rebalanceo ±50%;
  capital 2 × nocional; ranura sin posición rinde 0.
- **Costo:** 0,38% del nocional por ida y vuelta (el de P15).

## Criterio de PASA (los de P15/P74, cartera de las 2 monedas con una ranura igual cada una)
1. Rendimiento neto anualizado > tasa libre de riesgo media del período (`docs/p11_policy_rates.csv`).
2. CI95 bootstrap por bloques de una semana del rendimiento medio: inferior > 0 (5000, semilla 20261126).
3. Anualizado > 0 en las dos mitades cronológicas.
4. Caída máxima de la cartera < 10%.
5. Las 2 monedas con resultado neto > 0.

## Descriptivo (no decide)
Por año, funding vs base vs costos, "siempre adentro", la misma ventana con el funding de Binance (P15) y la
correlación diaria entre los dos libros.

## Límites
- Riesgo de exchange no modelado (Deribit es de Coinbase desde 2025). Spot de otro exchange que el perpetuo ⇒ la base
  incluye la diferencia de precio entre exchanges. Sin reservas (es en sí una prueba fuera de muestra).

## Si PASA
No se activa nada. Entra a `docs/cartera_de_lo_que_pasa.md` como réplica en otro exchange; propuesta de sumarlo al
papel de P19 para el OK del user.
## Si NO PASA
Se anota; no se cambia ninguna regla para que pase.
