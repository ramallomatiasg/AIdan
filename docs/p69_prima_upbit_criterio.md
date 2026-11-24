# P69 — Prima de Upbit (Corea) por moneda → retorno en Binance la semana siguiente: criterio declarado ANTES de medir (23-nov-2026)

**Hipótesis:** la demanda minorista coreana empuja precios locales que no se arbitran fácil (controles de capital). Si
una moneda cotiza en Upbit con más prima que el resto, esa demanda local revierte o ya está "gastada" ⇒ en Binance la
moneda con más prima rinde menos la semana siguiente que la de menos prima. Tipo **C** (información que el precio de
Binance no tiene). Distinto de P42 (prima de Coinbase, solo BTC, como timing).

## Datos (ningún precio mirado antes de declarar; solo la lista de mercados de Upbit)
- Upbit, API pública: lista de mercados actual (`/v1/market/all`) y velas diarias de cada mercado `KRW-X`
  (`/v1/candles/days`, vela 00:00-24:00 UTC = 09:00 KST), cache `.cache_p69/`.
- Binance: los perpetuos de P67 (`.cache_p67/disc`, velas diarias open/volumen + funding desde la primera vela).
- **Sin tipo de cambio:** la prima de cada moneda es `P_upbit / P_binance`; el KRW→USD es el mismo para todas las monedas
  ese día, así que el ORDEN entre monedas no depende de él. Se usa la prima relativa a BTC (`prima_i / prima_BTC − 1`).
- **Mapeo fijo:** `KRW-X` ↔ perpetuo `XUSDT`; si no existe, `1000XUSDT` (precio de Binance ÷ 1000) o `1000000XUSDT`
  (÷ 1.000.000). Nada a mano.

## Regla (fija)
- Lunes 00:00 UTC. Prima diaria de la moneda `i` el día `t` = (cierre Upbit de `t`) / (open Binance de `t+1`, que es el
  cierre de `t`) relativa a la de BTC el mismo día. **Señal** = media de la prima relativa de los 7 días previos al lunes.
- **Elegible:** lo de P67 (≥30 días de perpetuo, ≥15 cobros de funding en 7 días, volumen Binance ≥ USD 10 M/día,
  vela con volumen el lunes) **y** ≥5 días con prima en los 7 previos **y** volumen medio en Upbit ≥ KRW 1.000 millones/día
  **y** filtro de identidad: la mediana de |prima relativa| en los 30 días previos ≤ 20% (si no, el ticker es otra
  moneda o el depósito está cerrado; se descarta esa semana).
- ≥10 elegibles. Quintil de prima MÁS ALTA ⇒ corto; MÁS BAJA ⇒ largo (`floor(N/5)`, mínimo 2), peso igual.
- PnL por moneda, retorno de la semana, costo (0,15% / pesimista 0,30% por lado × rotación) y cierre por deslistado:
  idénticos a P67 (se importan sus funciones).

## Placebo
200 placebos: a cada semana se le asigna la señal de otra semana al azar (semilla 20261123), con el universo elegible
de la semana real. Se compara el retorno BRUTO medio.

## Muestra
- **Descubrimiento:** lunes 6-ene-2020 → 25-dic-2023. **Reserva:** 2024 → última semana completa, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥150 semanas con cartera.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000, semilla fija) inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Retorno bruto medio real > p95 de los 200 placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado, N medio, aporte precio/funding por pata, peor semana, caída máxima, por año, correlación con P67 y P68.

## Límites
- La lista de Upbit es la ACTUAL: las monedas que Upbit deslistó no entran (sesgo de supervivencia en la señal, no en
  el resultado de Binance, que sí incluye cerrados).
- Cierre de Upbit 24:00 UTC vs open de Binance 00:00 UTC: mismo instante.
- Universo chico en 2020 (pocas monedas en los dos lados).

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo y propuesta al user.
## Si NO PASA
Cerrada la prima de Upbit por moneda; no se prueban otras ventanas, umbrales, otros exchanges coreanos ni el signo
contrario.
