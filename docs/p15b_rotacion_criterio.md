# P15b — carry de funding con ROTACIÓN hacia las monedas que más pagan — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026 (pedido del user: "declará y probá la rotación hacia las monedas con más funding").
**Tool:** `tools/backtest_p15b_rotacion.py` (read-only, sin MT5, no toca la DB). Reusa la carga de datos y la
simulación de `tools/backtest_p15_funding.py` (importadas).

## De dónde sale

P15 (carry de funding, una ranura fija por moneda) pasó dentro y fuera de muestra con ~+5%/año sobre el capital.
Mirando cuánto estuvo adentro cada moneda: varias pasan mucho tiempo afuera (BNB 35%, AVAX 56%, SOL 58%), y esa
plata rinde 0. La idea: **concentrar el capital en las K monedas que más funding pagan en cada momento**, para
usar mejor la plata. Como la idea sale de mirar las 10 monedas de P15, el veredicto que importa es **fuera de
muestra en 10 monedas nuevas, nunca bajadas**.

## Universos

- **En muestra (las 10 de P15):** BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, LTC, AVAX.
- **Fuera de muestra (nuevas):** TRX, DOT, BCH, ETC, ATOM, FIL, UNI, XLM, NEAR, XTZ. Verificado el 23-oct que
  tienen funding y spot vivos desde 2019-2020 (sin mirar ningún retorno). EOS excluida: su spot dejó de cotizar en
  may-2025.

## Regla (congelada)

- Cada 8 h (00/08/16 UTC), para cada moneda, la misma señal de P15: media del funding de los últimos 7 días por 8 h.
- **K = 3 ranuras**, cada una con 1/3 del capital (nocional = capital de la ranura / 2, igual que P15).
- **Salida** de una moneda en cartera: si su señal < 0 (regla de P15) **o** si cae fuera de las 6 primeras del
  ranking (2K, para no rotar por ruido).
- **Entrada:** si hay ranura libre, entra la moneda fuera de cartera con la señal más alta, siempre que sea
  ≥ 0,005% (umbral de P15). Si no hay candidatas, la ranura queda en 0.
- Rebalanceo a ±50%, costos (0,38% por ida y vuelta), ejecución y funding: exactamente como P15 (con la
  corrección de la enmienda 1).

## Comparación

Contra **P15 tal cual** (una ranura fija por moneda) sobre las MISMAS monedas y el mismo período.

## Criterio de PASA (en muestra, las 10 de P15)

1. Rendimiento anualizado de la rotación > el de P15 sobre las mismas monedas, con CI95 de la DIFERENCIA (bootstrap
   en bloques de una semana) cuyo límite inferior > 0.
2. Rendimiento anualizado > la tasa libre de riesgo media del período.
3. Positivo en las dos mitades cronológicas.
4. Caída máxima < 10%.
5. Últimos 12 meses (hasta el 22-oct-2026) anualizado > 0 (el problema de P15 es el régimen actual).

**Si pasa:** fuera de muestra en las 10 nuevas, UNA vez: pasa si la rotación > P15 sobre esas monedas y >
la tasa libre de riesgo.
**Si no pasa:** cerrada la rotación; no se barren K, el corte de 2K ni los umbrales.

## Límites

Los de P15 (riesgo de exchange no modelado, velas de 8 h). Concentrar en 3 monedas sube el riesgo de que una
quiebra o un evento puntual de una moneda pese más.
