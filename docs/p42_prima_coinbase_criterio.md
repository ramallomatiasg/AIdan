# P42 — Prima de Coinbase → BTC del día siguiente: criterio declarado ANTES de medir (14-nov-2026)

**Hipótesis (escalera C):** la diferencia de precio de BTC entre Coinbase (BTC-USD, compradores de EE.UU. e
institucionales) y Binance (BTCUSDT, resto del mundo), corregida por el precio del USDT, mide demanda de EE.UU. que
todavía no llegó al resto del mercado; una prima alta anticipa suba al día siguiente y una prima negativa, baja.
**Riesgo declarado (como P36):** que la prima solo refleje el precio del MISMO día (Coinbase lidera los movimientos
intradía) y no anticipe el siguiente ⇒ deciden el placebo y la comparación entre las dos mitades.

## Datos
- Coinbase Exchange, API pública sin clave: velas diarias UTC de **BTC-USD** y **USDT-USD** (cierre del día d).
- Binance: precio spot y perpetuo de BTC cada 8 h y funding real, de `.cache_p15/BTC.json` (ya bajado).
- Prima del día d: `cb_close(d) / (bn_spot(d+1 00:00) × usdt_close(d)) − 1`. Días con algún dato faltante: sin señal.
  Antes de declarar solo se miró el formato de las respuestas (no niveles de prima ni retornos).

## Señal y ejecución (fijas)
- Terciles **móviles y causales**: percentiles 33,3 y 66,7 de la prima en los 365 días previos (exige ≥ 300 días).
- Prima del día d en el tercio alto ⇒ **largo** BTC perpetuo de las 00:00 UTC de d+1 a las 00:00 de d+2; tercio bajo
  ⇒ **corto**; tercio medio ⇒ afuera.
- Costo: 0,07% por lado cada vez que cambia la posición (de largo a corto cuesta dos lados). Funding real: el largo
  lo paga, el corto lo cobra.

## Muestras
- Descubrimiento: días de señal hasta 2023-12-31 (desde que hay 300 días de prima). Reserva: 2024-01-01 → último día
  completo del cache de Binance.

## Control
- **Placebo:** 1000 réplicas con la serie de prima desplazada circularmente un número al azar de días (entre 30 y
  n−30), mismas reglas ⇒ percentil 95 de la media diaria de la reserva.

## Criterios (PASA = los 5, sobre la reserva)
1. n ≥ 300 días con posición en la reserva.
2. Media neta por día con posición > 0 y extremo inferior del CI95 (bootstrap por bloques de 5 días) > 0.
3. Media neta > 0 también en el descubrimiento.
4. Media neta > percentil 95 del placebo.
5. Media neta > 0 en las dos mitades de la reserva.

## Descriptivo (no decide)
Spearman de la prima con el retorno del mismo día y del día siguiente; largos vs cortos; por año; variante con entrada
a las 08:00 UTC.

## Si PASA
No se activa. Siguiente: ETH con la misma regla (fuera de muestra) y papel en vivo; propuesta al user.
## Si NO PASA
Cerrar prima de Coinbase como señal diaria de dirección. No probar otros umbrales, horizontes ni ETH.
