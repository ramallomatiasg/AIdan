# P56 — Corto de los perpetuos recién listados en Binance (días 2 a 30): criterio declarado ANTES de medir (18-nov-2026)

**Hipótesis:** los tokens nuevos llegan con oferta que TIENE que venderse en las primeras semanas (airdrops,
launchpool, inventario de market makers, desbloqueos de inversores tempranos) ⇒ el precio cae del día 2 al día 30
más que en un mes "normal" de la misma moneda. Tipo **B** (flujo forzado). Prior medio (muy citado de forma anecdótica,
nunca medido acá).

## Datos (verificado antes de declarar: solo LISTAS de símbolos y fechas, **ningún precio**)
- Universo: todo perpetuo USDⓈ-M `*USDT` de Binance con alta (`onboardDate` de `fapi/v1/exchangeInfo`, que incluye los
  ya cerrados en estado SETTLING) desde el 1-ene-2023. Los perpetuos que ya NO figuran en exchangeInfo salen de la
  lista pública de `data.binance.vision` (29 símbolos); para ellos la fecha de alta = primera vela diaria de `fapi`.
  Caches `.cache_p56/exchangeInfo.json` y `.cache_p56/s3_symbols.json` (bajados el 18-nov).
- Se excluyen: `PENDING_TRADING`, índices (`BTCDOM`, `DEFI` y similares sin token), y los listados después del
  20-ago-2026 (no llegan al día 88 que pide el control).
- Precios: velas diarias y funding de `fapi` (público, responde también para perpetuos cerrados), cache `.cache_p56/px/`.

## Regla
- Día 1 = día UTC del alta (vela parcial, se saltea a propósito: es el squeeze del lanzamiento).
- **Corto:** open de la vela diaria del día 2 (alta + 1 día, 00:00 UTC) → open de la vela del día 30 (28 días).
  Si el perpetuo deja de operar antes, salida en el open de la última vela con volumen > 0.
- Resultado = −(P_salida / P_entrada − 1) + funding cobrado por el corto en el tramo − costo.
- **Costo:** taker 0,05% × 2 + deslizamiento 0,10% × 2 = **0,30%** ida y vuelta. Pesimista: **0,60%**.
- Sin stop (como está declarado; las colas se reportan).

## Control (placebo)
La MISMA moneda, corto del open del día 60 al open del día 88 (28 días, misma mecánica y costo). Saca la deriva
bajista general de las alts nuevas (si todas caen siempre, no es un efecto de la oferta del lanzamiento).

## Muestra
- **Descubrimiento:** altas 2023-2024. **Reserva:** altas 1-ene-2025 → 20-ago-2026, solo si pasa el descubrimiento.
- Las monedas listadas la misma semana comparten mercado ⇒ CI por bootstrap agrupado por **semana ISO del alta**.

## Criterios (descubrimiento; PASA = los 6)
1. n ≥ 25 monedas con perpetuo y control.
2. Media neta > 0 y extremo inferior del CI95 agrupado > 0 (5000 remuestreos).
3. Las dos mitades cronológicas con media neta > 0.
4. Diferencia (tramo − control) por moneda: media > 0 y extremo inferior del CI95 agrupado > 0.
5. Media neta > 0 con el costo pesimista.
6. Mediana neta > 0.

**Reserva:** media neta > 0, CI agrupado inferior > 0 y diferencia contra el control > 0.

## Descriptivo (no decide)
Bruto y funding aparte; golpe del día 1 (no operable); peor evento (squeeze); subconjunto "token nuevo de verdad"
(sin par spot `<base>USDT` en Binance más de 30 días antes del alta del perpetuo); cuántos perpetuos cerraron antes
del día 30.

## Límites
- Corto de alt sin stop = pérdida ilimitada en teoría; el peor caso medido se reporta en USD sobre $100.
- La mitad de las altas desde 2023 son monedas viejas que recién reciben perpetuo: el subconjunto de "token nuevo" es
  descriptivo, la regla toma todas (decidido antes para no elegir el corte después).

## Si PASA
No se activa. Reserva; después papel en vivo (lote mínimo, peor caso = el peor squeeze medido).
## Si NO PASA
Cerrar el corto de listados nuevos. No probar otros días de entrada/salida, stops ni otros exchanges.
