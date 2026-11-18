# P53 — Anuncios de deslistado de Binance (venta forzada): criterio declarado ANTES de medir (18-nov-2026)

**Hipótesis:** cuando Binance anuncia que deslista una moneda del spot, los tenedores TIENEN que vender o sacarla
antes de la fecha y los market makers se retiran ⇒ el precio sigue cayendo entre el anuncio y el deslistado, más
allá del golpe de los primeros minutos (que no se puede agarrar). Tipo **B** (flujo forzado). Prior medio.

## Datos (verificado antes de declarar: solo el archivo de anuncios, **ningún precio**)
- Anuncios: catálogo público "Delisting" de Binance (`bapi/composite/v1/public/cms/article/list/query`,
  catalogId 161), 447 artículos desde feb-2022, cache `.cache_p53/articles.json`. Se toman los títulos
  "Binance Will Delist A, B, C on YYYY-MM-DD" (y el de "Vote to Delist Results ... Will Delist ... on YYYY-MM-DD");
  hora del anuncio = `releaseDate`. ~45 anuncios 2022 → oct-2026.
- Se excluyen stablecoins, fiat y envueltos: SUSD, USDP, IDRT, VAI, RENBTC, TUSD, BUSD, USDC, PAX.
- Precios: velas de 1 h y funding del perpetuo USDⓈ-M `<SYM>USDT` (o `1000<SYM>USDT`) de Binance (`fapi`, público;
  sigue respondiendo para perpetuos ya cerrados), cache `.cache_p53/px/`.

## Regla
- **Entrada (corto):** open de la primera vela de 1 h que arranca **después de anuncio + 5 min** (entre 5 y 65 min
  después: el golpe de los primeros minutos no se cuenta). Hace falta que esa vela tenga volumen > 0; si no, el evento
  se descarta y se cuenta.
- **Salida:** open de la vela de 00:00 UTC del día del deslistado; si el perpetuo deja de operar antes (última vela con
  volumen > 0), el open de esa última vela con volumen.
- Resultado = −(P_salida / P_entrada − 1) + funding cobrado por el corto en el tramo − costo.
- **Costo:** taker 0,05% × 2 + deslizamiento 0,25% × 2 = **0,60%** ida y vuelta (alts ilíquidas en caída). Pesimista: **1,20%**.

## Control (placebo)
Misma moneda, ventanas de la MISMA duración (en horas) que arrancan en una hora al azar de los 365 días que terminan
30 días antes del anuncio; 2000 repeticiones de la media de n ventanas (una por evento) ⇒ percentil 95. Saca la deriva
bajista propia de las monedas que terminan deslistadas.

## Muestra
- **Descubrimiento:** anuncios 2022-2024. **Reserva:** 2025 → oct-2026, solo si pasa el descubrimiento.
- Las monedas de un mismo anuncio comparten mercado ⇒ el CI se agrupa **por anuncio**.

## Criterios (descubrimiento; PASA = los 6)
1. n ≥ 25 monedas-evento con perpetuo.
2. Media neta > 0 y extremo inferior del CI95 > 0 (bootstrap agrupado por anuncio, 5000).
3. Las dos mitades cronológicas (por anuncio) con media neta > 0.
4. Media neta > percentil 95 del control.
5. Media neta > 0 con el costo pesimista.
6. Mediana neta > 0.

**Reserva:** media neta > 0, CI agrupado inferior > 0 y > control p95.

## Descriptivo (no decide)
Bruto, funding aparte, golpe de la primera hora (anuncio → entrada, NO operable), horas en posición, peor evento
(squeeze), cuántos perpetuos cerraron antes del deslistado del spot.

## Límites
- Muchas monedas deslistadas no tenían perpetuo ⇒ la muestra es la de las más grandes.
- Binance suele cerrar el perpetuo antes que el spot: la salida anticipada usa el último open con volumen, no el
  precio de liquidación.
- Funding muy negativo en el corto (todos cortos) es parte del costo real y se cuenta.

## Si PASA
No se activa. Reserva; después papel en vivo (lote mínimo, peor caso en USD = el peor squeeze medido).
## Si NO PASA
Cerrar deslistados de Binance. No probar otras horas de entrada, otros exchanges ni el largo.
