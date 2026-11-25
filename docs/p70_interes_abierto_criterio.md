# P70 — Interés abierto apalancado → reversión semanal de las alts (neutral al mercado): criterio declarado ANTES de medir (24-nov-2026)

**Hipótesis:** cuando el interés abierto (OI) de un perpetuo crece junto con el movimiento del precio, entró
apalancamiento nuevo persiguiendo el movimiento; ese apalancamiento después se liquida o se cierra (desapalancamiento
forzado) y el precio revierte. Cuando el movimiento vino con el OI cayendo (cierre de posiciones), no hay ese
combustible y el movimiento sigue. Tipo **B** (flujo forzado). Distinto de P41/P67 (funding = el PRECIO del
apalancamiento): acá se mide la CANTIDAD. Nunca medido (grep "interés abierto"/"open interest": 0).

## Datos (ningún OI ni retorno mirado antes de declarar; solo se verificó que los archivos existen)
- **OI:** archivos diarios `metrics` de data.binance.vision (`data/futures/um/daily/metrics/<SYM>/`), columna
  `sum_open_interest` (en CONTRATOS, no en USD, para que el precio no entre mecánicamente), fila de las **00:00 UTC del
  lunes** (o la primera fila del lunes si está dentro de los primeros 15 min). Para las alts existen desde el
  **1-dic-2021**. Cache `.cache_p70/`. Solo se bajan los lunes que hacen falta.
- **Precios, volumen y funding:** `.cache_p67/full/` (perpetuos USDT de Binance, cerrados incluidos, funding completo),
  con la misma lógica de P67 (`load`, `eligible`, `leg`, `pick`, `turnover`, `block_ci` importados de su tool).

## Regla (fija)
- Rebalanceo cada lunes 00:00 UTC, como P67. Elegible: la de P67 (≥30 días, volumen ≥ USD 10 M/día, ≥15 cobros de
  funding) **y** OI disponible el lunes `m` y el lunes `m−7d`, con OI > 0.
- `r` = open del lunes `m` / open del lunes `m−7d` − 1. `dOI` = ln(OI_m / OI_{m−7d}).
- **Señal `y = dOI × r`.** `y` alto = el OI creció a favor del movimiento (apalancados persiguiendo) ⇒ **corto**
  (en contra de lo que se movió); `y` bajo = el movimiento vino con el OI en contra ⇒ **largo**. Un solo orden ⇒
  quintil de `y` más ALTO corto, más BAJO largo, `pick` de P67 (≥10 elegibles, `floor(N/5)` por pata, mín 2).
  (Las 4 combinaciones: OI↑ precio↑ ⇒ y>0 ⇒ corto; OI↑ precio↓ ⇒ y<0 ⇒ largo; OI↓ precio↑ ⇒ y<0 ⇒ largo, sigue;
  OI↓ precio↓ ⇒ y>0 ⇒ corto, sigue.)
- PnL, retorno de la semana (por dólar bruto), funding real, costo 0,15% por lado × rotación (pesimista 0,30%): idéntico
  a P67.

## Placebo
200 placebos (semilla 20261124): a cada semana se le asigna la señal `y` de otra semana al azar, manteniendo el universo
elegible de la semana real (como P67). Se compara el bruto medio.

## Muestra
- **Descubrimiento:** lunes 13-dic-2021 → 24-jun-2024 (~133 semanas). **Reserva:** 1-jul-2024 → última semana completa,
  solo si pasa. (El corte no es en ene-2024 porque el OI de las alts empieza recién en dic-2021.)

## Criterios (descubrimiento; PASA = los 5)
1. ≥120 semanas con cartera.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000) con inferior > 0.
3. Las dos mitades cronológicas con neto > 0.
4. Neto > 0 con el costo pesimista.
5. Bruto medio real > p95 de los placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado, aporte de precio/funding por pata, peor semana, caída máx, por año, elegibles medios, correlación con BTC,
correlación con P67 (carry transversal) y con la reversión pura (misma cartera ordenando solo por `r`, sin OI) para ver
si el OI agrega algo sobre la reversión de 1 semana.

## Límites
- Archivos `metrics` faltantes ⇒ la moneda queda afuera esa semana (se cuenta cuántas).
- Muestra de descubrimiento corta (2,5 años, incluye el bear de 2022).
- Capital chico: 2 patas × ≥2 monedas con mínimos de ~USD 5-100 por orden ⇒ se reporta si pasa.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo con la misma regla y propuesta al user.
## Si NO PASA
Cerrado el OI como señal transversal; no se prueban otras ventanas, OI en USD, umbrales ni el signo contrario.
