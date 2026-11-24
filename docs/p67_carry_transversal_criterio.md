# P67 — Carry TRANSVERSAL de funding entre perpetuos de Binance: criterio declarado ANTES de medir (23-nov-2026)

**Hipótesis:** el funding alto marca dónde se amontonan los largos apalancados. Corto de los perpetuos con funding más
alto y largo de los de funding más bajo (semanal, neutral al mercado) cobra el diferencial de funding y, si el precio
de lo amontonado cede, también el precio (Schmeling, Schrimpf y Todorov 2023, BIS, "Crypto carry"). Tipo **A** (premio
por riesgo). Distinto de P15/P45 (spot contra perpetuo de la misma moneda) y de P41 (funding de BTC como timing).

## Datos (ningún precio ni funding mirado antes de declarar)
- Universo: todos los símbolos USDT de futuros UM que alguna vez existieron (`.cache_p56/s3_symbols.json`, sale de
  data.binance.vision, incluye los cerrados). Fuera: los que tienen `_` (vencimiento), los de `exchangeInfo` con
  `underlyingType` distinto de `COIN`, y la lista fija {BTCDOMUSDT, DEFIUSDT, BLUEBIRDUSDT, FOOTBALLUSDT, USDCUSDT,
  BUSDUSDT, TUSDUSDT, USDPUSDT, FDUSDUSDT}. Solo los que tienen primera vela antes del fin de la muestra mirada.
- Velas diarias (open, volumen) y funding de la API pública `fapi` de Binance, cache `.cache_p67/`. **El funding se pide
  con `startTime` = primera vela** (con `startTime=0` la API devuelve solo los últimos ~333 días; ver nota en el registro).

## Regla (fija)
- Rebalanceo cada lunes 00:00 UTC (open de la vela diaria del lunes). Semana = de ese open al del lunes siguiente.
- **Señal:** funding medio de los cobros con hora en los 7 días previos al lunes.
- **Elegible** esa semana: ≥30 días desde la primera vela; ≥15 cobros de funding en los 7 días previos; volumen medio
  en USD (volumen × open) de los 7 días previos ≥ USD 10 millones/día; vela con volumen > 0 el lunes.
- Se necesitan ≥10 elegibles. Quintil de funding más ALTO ⇒ corto; quintil más BAJO ⇒ largo (`floor(N/5)` por pata,
  mínimo 2), peso igual dentro de cada pata.
- PnL por moneda en la semana: largo `r − Σfunding`, corto `−r + Σfunding` (funding real con hora en la semana).
  Si la moneda deja de cotizar en la semana, se cierra en el último open con volumen (como P56).
- **Retorno de la semana** = (media de la pata larga + media de la pata corta) / 2 ⇒ por dólar de exposición bruta.
- **Costo:** 0,15% por lado operado (comisión taker 0,05% + deslizamiento 0,10%) × rotación de cada pata (suma de
  |peso nuevo − peso viejo|, la primera semana rotación completa), dividido 2 como el retorno. Pesimista: 0,30%.

## Placebo
200 placebos: a cada semana se le asigna la señal (el funding medio por moneda) de otra semana al azar de la muestra
(semilla fija 20261123), manteniendo el universo elegible de la semana real; las monedas sin señal en la semana
prestada quedan afuera. Mismo armado de quintiles. Se compara el retorno BRUTO medio.

## Muestra
- **Descubrimiento:** semanas desde el 6-ene-2020 hasta el 25-dic-2023. **Reserva:** 1-ene-2024 → última semana
  completa con datos, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥150 semanas con cartera.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000, semilla fija) con inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Retorno bruto medio real > p95 de los 200 placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado (× 52), aporte del funding vs del precio en cada pata, peor semana, caída máxima, por año, N medio de
elegibles, correlación semanal con BTC y con el carry de P15 si está a mano.

## Límites
- Volumen de las velas = base × open (aproximado). Umbral de 10 M fijo, no se prueba otro.
- Pocas monedas en 2020 (N chico al principio).
- Si pasa: el peor caso con capital chico (USD 500-1.000) choca con los mínimos de los perpetuos (~USD 5-100 por orden)
  y con 2 patas × 2+ monedas ⇒ se reporta.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo con la misma regla y propuesta al user (Plan/Razón/Pros/Contras).
## Si NO PASA
Cerrado el carry transversal de funding; no se prueban otras ventanas, umbrales, quintiles ni el signo contrario.
