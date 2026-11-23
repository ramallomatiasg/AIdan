# P65 — Índice de miedo y codicia de cripto como señal CONTRARIA semanal en BTC: criterio declarado ANTES de medir (23-nov-2026)

**Hipótesis:** el índice de miedo y codicia (alternative.me) resume el humor minorista. Si los minoristas venden en
pánico (miedo extremo) el que compra cobra un premio por dar liquidez, y en euforia (codicia extrema) pasa al revés.
Tipo **C** (información/sentimiento). Nunca medido (grep miedo/greed: 0).

## Datos (ningún valor del índice ni precio mirado antes de declarar; solo se probó que la API responde)
- Índice diario: `https://api.alternative.me/fng/?limit=0&format=json` (cada valor fechado a las 00:00 UTC del día).
- BTC: velas DIARIAS spot BTCUSDT de Binance (API pública), apertura de cada día. Cache `.cache_p65/`.
- Funding del perpetuo BTCUSDT de Binance: `.cache_p15/BTC.json` (desde sep-2019; antes, funding 0 para el corto).

## Regla (fija)
- Cada lunes 00:00 UTC se mira el valor del **domingo** (publicado 24 h antes: no hay mirada al futuro).
- Valor ≤ 20 ⇒ **largo** BTC la semana (lunes → lunes, apertura a apertura); valor ≥ 80 ⇒ **corto** con el perpetuo
  (cobra/paga el funding real de la semana); en el medio ⇒ afuera (0).
- **Costo** por cada cambio de posición: **0,10%** por unidad de cambio (taker + deslizamiento; pasar de largo a corto
  cuesta 0,20%). Pesimista: **0,20%** por unidad.
- Retorno de la semana = `s · r_BTC` (+ funding si corto) − costo.

## Muestra
- **Descubrimiento:** semanas desde feb-2018 hasta dic-2022. **Reserva:** ene-2023 → última semana completa
  (16-nov-2026), solo si pasa.

## Criterios (descubrimiento; PASA = los 5), sobre las semanas ACTIVAS (s ≠ 0)
1. n ≥ 30 semanas activas.
2. Media neta por semana activa > 0 y CI95 bootstrap por bloques de 4 semanas (5000, semilla fija) inferior > 0.
3. Las dos mitades cronológicas de las semanas activas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. **Placebo (controla la deriva de BTC):** la serie de posiciones corrida en el tiempo (todos los corrimientos
   circulares de 8 a N−8 semanas; mismo número de semanas largas y cortas, timing roto): la media bruta real por semana
   activa supera el percentil 95 del placebo.

**Reserva:** criterios 2 y 5 (con n reportado).

## Descriptivo (no decide)
Pata larga (miedo) y corta (codicia) por separado, media incondicional de BTC por semana, % de semanas activas,
correlación del índice con el retorno de los 30 días previos (cuánto del índice es precio pasado), por año.

## Límites
- Pocas semanas extremas; el índice se construye en parte con volatilidad y momentum del precio ⇒ el placebo es el que
  separa "sentimiento" de "deriva".
- El corto con perpetuo tiene colas (squeeze): se reporta la peor semana.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo (lectura de cada domingo) y propuesta al user con capital chico.
## Si NO PASA
Cerrado el índice de miedo y codicia como señal; no se prueban otros umbrales, horizontes ni el signo contrario.
