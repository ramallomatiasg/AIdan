# P77 — Capitulación de apalancamiento en BTC/ETH: criterio declarado ANTES de medir (26-nov-2026)

**Pregunta:** cuando en un día el interés abierto (OI) del perpetuo cae muy fuerte **y** el precio cae (liquidaciones
en cascada = ventas forzadas, no información), ¿el precio rebota en los 3 días siguientes lo suficiente para pagar
costo y funding? Tipo **B** (flujo forzado). Distinto de P41 (funding extremo), P65 (sentimiento) y P70 (corte
transversal semanal del OI).

## Datos (solo se verificó que el primer archivo existe; ningún OI ni precio mirado)
- OI: `sum_open_interest` (contratos) de los `metrics` diarios de data.binance.vision (BTCUSDT, ETHUSDT), primera fila
  del día (≤ 00:15 UTC) = OI de las 00:00. Cache `.cache_p77/`.
- Precio y funding del perpetuo: cache de P15 (`.cache_p15/`, open de 8 h y funding real hasta el 22-oct-2026).

## Señal (por moneda, día UTC d)
- `dOI_d = ln(OI_{d+1} / OI_d)`, `r_d = ln(P_{d+1, 00:00} / P_{d, 00:00})` (open del perpetuo).
- **Evento:** `dOI_d` ≤ percentil 10 de `dOI` del descubrimiento de esa moneda **y** `r_d < 0`.
- **Entrada:** largo el perpetuo al open de las **08:00 UTC del día d+1** (el dato de OI de las 00:00 sale unos minutos
  después; se espera a la próxima marca de 8 h para no mirar el futuro). **Salida:** 08:00 UTC de d+4 (3 días).
- Una posición por moneda: los eventos que caen con posición abierta se ignoran.
- **Neto** = retorno del perpetuo − funding pagado en la tenencia (cobros reales de P15) − **0,10%** de costo.

## Control (no cambia la regla, es la comparación)
- Días con `r_d` ≤ percentil 10 de `r` del descubrimiento (caída de precio igual de grande) y `dOI_d` ≥ mediana
  (sin caída de OI); misma entrada, salida, funding y costo, misma regla de no superponer.
- Placebo: 2000 sorteos de la misma cantidad de días con `r_d < 0` al azar (semilla 20261126); p95 de la media neta.

## Períodos
- Descubrimiento: desde el primer día con OI (sep-2020) hasta el 31-dic-2023. Reserva: 1-ene-2024 → 21-oct-2026,
  **solo se mira si pasa el descubrimiento**.

## Criterio de PASA (descubrimiento, eventos de BTC y ETH juntos)
1. n ≥ 25 eventos.
2. Media neta > 0 con CI95 bootstrap por evento (5000, semilla 20261126) de inferior > 0.
3. Media neta > p95 del placebo **y** > media neta del control.
4. Media neta > 0 en las dos mitades cronológicas de los eventos.
5. Media neta > 0 en las dos monedas.
**Reserva:** media neta > 0 y > media del control.

## Límites
- OI en contratos (no en USD): en un día de caída fuerte el OI en USD cae más que en contratos ⇒ la señal en contratos
  es la más conservadora (mide cierre real de posiciones). Solo Binance. Costo 0,10% ida y vuelta (taker ~0,05% × 2).

## Si PASA (descubrimiento y reserva)
No se activa nada: propuesta de papel en vivo con OK del user. **Si NO PASA:** se anota y no se prueban otros
percentiles, horizontes ni monedas.
