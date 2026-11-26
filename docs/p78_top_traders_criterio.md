# P78 — Top traders de Binance contra la masa (corte transversal semanal): criterio declarado ANTES de medir (26-nov-2026)

**Hipótesis:** las cuentas grandes ("top traders" de Binance) tienen más información o mejor ejecución que la masa
minorista. Cuando en una moneda los grandes están más largos que el resto de las cuentas, esa moneda rinde más la semana
siguiente que las monedas donde los grandes están más cortos que la masa. Tipo **C** (información que el precio no
resume). Nunca medido (grep "top trader"/"long short": 0 antes de P78).

## Datos (solo se verificó DESDE CUÁNDO vienen llenas las columnas; ningún valor ni retorno mirado)
- `metrics` diarios de data.binance.vision (`data/futures/um/daily/metrics/<SYM>/`): columnas
  `sum_toptrader_long_short_ratio` (posición largo/corto de los top traders) y `count_long_short_ratio` (largo/corto de
  todas las cuentas). **Verificado en BTCUSDT y DOGEUSDT:** las columnas de top traders vienen vacías del ~2-may al
  28-may-2022 y llenas en las 288 filas desde el **domingo 29-may-2022** ⇒ la muestra arranca ahí.
- Fila usada: la última del domingo con las dos columnas > 0 y hora ≥ 23:00 UTC (normalmente 23:55). Si no hay, la
  moneda queda afuera esa semana. Cache `.cache_p78/`.
- Precios, volumen y funding: `.cache_p67/full/` con la lógica de P67 (`load`, `eligible`, `pick`, `week_ret`,
  `turnover`, `block_ci` importados de su tool), como P70.

## Regla (fija)
- Rebalanceo cada lunes 00:00 UTC. Elegible: la de P67 (≥30 días, volumen ≥ USD 10 M/día, ≥15 cobros de funding) **y**
  dato de metrics del domingo previo.
- **Señal `s = ln(sum_toptrader_long_short_ratio) − ln(count_long_short_ratio)`.** `s` alto = los grandes más largos que
  la masa ⇒ **largo**; `s` bajo ⇒ **corto**. Quintiles con `pick` de P67 (≥10 elegibles, `floor(N/5)` por pata, mín 2).
- PnL, funding real, costo 0,15% por lado × rotación (pesimista 0,30%): idéntico a P67/P70.

## Placebo
200 placebos (semilla 20261126): a cada semana la señal de otra semana al azar, con el universo elegible real (como P70).

## Muestra
- **Descubrimiento:** lunes 30-may-2022 → 24-jun-2024 (~109 semanas). **Reserva:** 1-jul-2024 → última semana completa,
  solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥100 semanas con cartera.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000) con inferior > 0.
3. Las dos mitades cronológicas con neto > 0.
4. Neto > 0 con el costo pesimista.
5. Bruto medio real > p95 de los placebos.
**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Aporte por pata (precio/funding), por año, correlación con BTC, con P67 y con P70.

## Límites
- El ratio de "todas las cuentas" cuenta cuentas, no plata; el de top traders es de posición. Muestra corta (2 años).
- Capital chico: 2 patas × ≥2 monedas.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo y propuesta al user.
## Si NO PASA
Cerrado el posicionamiento de top traders como señal transversal; no se prueban el signo contrario, otras columnas
(`count_toptrader…`, `sum_taker…`), otras ventanas ni umbrales.
