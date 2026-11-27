# P80 — Prestar USD en el funding de Bitfinex contra la letra: criterio declarado ANTES de medir (26-nov-2026)

**Hipótesis:** los que operan con margen en Bitfinex pagan por pedir USD prestado una prima sobre la tasa libre (el mismo
motor que el funding de P15, pero cobrado como prestamista, sin precio que cubrir). Prestar USD con auto-renovación
rinde más que la letra a 3 meses. Tipo **A** (premio por riesgo: contraparte y exchange). Sirve con $500-1.000.

## Datos (verificado antes de declarar: solo cantidad de velas y fechas, **ningún valor mirado**)
- Velas diarias públicas del libro de préstamos en USD de Bitfinex, agregado de plazos 2 a 30 días
  (`trade:1D:fUSD:a30:p2:p30`): 3.763 velas del 31-jul-2016 al 27-nov-2026 (3.772 días calendario). Cache
  `.cache_p80/fusd_a30_p2_p30.json`. La tasa viene por día (fracción). También se bajó `trade:1D:fUSD:p30` (solo
  descriptivo).
- Letra a 3 meses: FRED `DTB3` (cache de P50, `.cache_p50/dtb3.json`), último dato disponible hacia atrás.

## Cálculo
- **Tasa del día (base)** = cierre de la vela; día sin vela = tasa del último día con vela.
- Rendimiento del prestamista por día = tasa × utilización × (1 − comisión de Bitfinex).
  **Base:** utilización 100%, comisión 15%. **Pesimista:** utilización 70%, comisión 18%, días sin vela = 0.
- **Costo de entrada/salida:** 1%/año (depositar USDT y convertir a USD, o el giro; igual que P50 y P57).
- **Premio diario** = rendimiento − DTB3/365 − 1%/365.
- **Hackeo de ago-2016:** el 2-ago-2016 Bitfinex socializó una pérdida de 36,067% sobre todos los saldos y la devolvió
  con tokens BFX rescatados 1:1 hasta el 3-abr-2017. **Base y pesimista:** −36,067% el 2-ago-2016 y +la devolución
  el 3-abr-2017 (lo que realmente pasó, sin intereses por el tiempo). **Descriptivo:** el mismo cálculo sin devolución.

## Muestra
- **Descubrimiento:** 1-ago-2016 → 31-dic-2021. **Reserva:** 2022 → nov-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Premio anualizado (base) > 0.
2. CI95 por bootstrap en bloques de 30 días (5000): inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Premio anualizado pesimista > 0.
5. ≥ 60% de los meses con premio (base) > 0.

**Reserva:** criterios 1 y 2.

## Descriptivo (no decide)
Tasa anual media por año, contra la letra por año, sin devolución del hackeo, con la vela de plazo 30 días sola, cuántos
días sin vela.

## Límites
- La vela es de operaciones cerradas: no dice qué parte de una oferta chica a la tasa de mercado se presta (por eso la
  utilización de 70% en el pesimista). La tasa del cierre no es la media ponderada del día.
- El riesgo de exchange (hackeo, quiebra, congelamiento) solo aparece una vez y con devolución; la cola real es mayor.
- Depositar USD fiat en Bitfinex pide montos altos; con $500-1.000 se entra con USDT ⇒ el costo de 1%/año lo cubre.

## Si PASA
No se activa. Reserva; después papel (seguir la tasa en vivo) con monto mínimo y peor caso en USD, y medir la
correlación con lo que ya está en la cartera.
## Si NO PASA
Cerrado el préstamo de USD en Bitfinex; no se prueban otras monedas (USDt, BTC), plazos ni otra utilización.
