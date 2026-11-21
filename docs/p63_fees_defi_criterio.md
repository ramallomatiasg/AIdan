# P63 — Comisiones de protocolos DeFi → retorno de su token (semanal, neutral al mercado): criterio declarado ANTES de medir (21-nov-2026)

**Hipótesis:** las comisiones que cobra un protocolo son el "resultado" de su negocio; el mercado de alts (minorista,
narrativo) las incorpora lento ⇒ los tokens cuyo protocolo más aumentó las comisiones rinden más la semana siguiente
que los que menos (en acciones, el crecimiento de ventas anticipa retornos). Tipo **C** (información). Nunca medido acá
(grep fees/TVL en el registro: 0).

## Datos (verificado el 21-nov que las fuentes responden; **ninguna comisión ni precio mirados**)
- **Universo:** perpetuos USDT de Binance (fapi `exchangeInfo` actual + la lista histórica de símbolos de P56, incluye
  deslistados), `underlyingType = COIN`; moneda base con la regla de P59 (`base_of`, saca prefijos 1000/1M).
- **Mapeo moneda → protocolo (regla fija, aplicada sin mirar comisiones ni precios):** en `api.llama.fi/protocols` se
  buscan los protocolos con `symbol` == moneda base; cada uno se agrupa por su padre (`parentProtocol`, sin `parent#`)
  o por su propio `slug` si no tiene padre. Si la moneda cae en exactamente **un** grupo ⇒ ese grupo; si cae en más de
  uno ⇒ afuera. La lista se guarda (`.cache_p63/mapping.json`) antes de bajar comisiones o precios.
- **Comisiones:** `api.llama.fi/summary/fees/<grupo>?dataType=dailyFees` (`totalDataChart`, USD por día). Grupo sin
  serie ⇒ afuera.
- **Precios y funding:** velas diarias de fapi (open) y funding real (mismo código que P59). Cache `.cache_p63/`.

## Regla
- Semanas que arrancan el lunes 00:00 UTC. Para la semana t: comisiones de los 28 días que terminan el domingo
  anterior (F₄) contra los 28 días previos (F₄'). Señal = log(F₄ / F₄'). Solo cuentan monedas con F₄' ≥ USD 50.000 y
  F₄ > 0, perpetuo vivo con volumen el lunes t y el lunes t+1 (o su última vela) y ≥ 30 días listado.
- Hacen falta ≥ 10 monedas elegibles; k = max(2, ⌊n/5⌋). Las k con señal MÁS ALTA ⇒ **largo**; las k con señal MÁS
  BAJA ⇒ **corto**; peso igual, del open del lunes t al open del lunes t+1, funding real (el largo paga, el corto cobra).
- Retorno semanal = media de las patas largas + media de las patas cortas ($1 por lado).
- **Costo:** 0,10% por cada entrada o salida de una moneda, sobre el cambio real de la cartera de cada lado.
  Pesimista: 0,20%.

## Muestra
- **Descubrimiento:** semanas 2020-01-06 → 2023-12-25. **Reserva:** 2024-01-01 → 2026-11-09, solo si pasa.

## Criterios (descubrimiento; PASA = los 5) — idénticos a P59
1. ≥ 100 semanas con cartera.
2. Retorno semanal neto medio > 0 y CI95 por bootstrap en bloques de 4 semanas (5000, semilla fija) con inferior > 0.
3. Las dos mitades cronológicas > 0.
4. Media > 0 con el costo pesimista.
5. **Placebo desplazado:** la media bruta real supera el percentil 95 de 200 placebos con la serie de señales de cada
   moneda desplazada circularmente (≥ 26 semanas).

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Pata larga y corta por separado, monedas elegibles por semana, por año.

## Límites
- DefiLlama reescribe historia de comisiones (adaptadores nuevos o corregidos) ⇒ la serie de hoy no es la que se veía
  en su momento: sesgo a favor de la hipótesis si las correcciones siguen al precio. Si PASA, esto se discute antes
  de cualquier shadow.
- En 2020-21 hay pocos protocolos con token y perpetuo ⇒ puede no llegar a 100 semanas (criterio 1).
- Precio del perpetuo, no spot.

## Si PASA
No se activa. Reserva; después papel semanal con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrada la señal de comisiones; no se prueban otras ventanas, umbrales, ingresos (revenue) en vez de comisiones, ni el
signo contrario.
