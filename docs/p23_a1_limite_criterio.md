# P23 — A1 en EUR/USD con entrada LÍMITE (maker) — criterio declarado ANTES de medir

**Fecha:** 3-nov-2026 (rutina semanal, Parte 3). **Origen:** P21 dejó A1 en EUR/USD M15 con Fusion en
**+0,08 pips/operación, CI [−0,59, +0,74]** (H16, n=4.693): la única cosa con información que queda cerca de cero.
Lo único de ejecución sin medir es entrar con orden límite en vez de a mercado.
**Tool:** `tools/backtest_p23_a1_limite.py` (read-only, no toca la DB). Velas M1 de EURUSD bajadas de MT5 una vez
(con AIdan cerrado) a `.cache_p23/` (fuera de git); la señal M15 sale de `.cache_p1/M15/EURUSD.npy` y de
`screen_generators.gen_A1` (importada, no copiada).

## Señal y ejecución

- Señal: `gen_A1` al cierre de la vela M15 `i` (|z20| > 2, contra el desvío). Mismas ventanas que P9 (fuera de
  23:00-01:00 server, la salida el mismo día server). Una posición u orden viva a la vez.
- **Principal:** orden límite a `c_i − 0,25·sd20_i` (largo) / `c_i + 0,25·sd20_i` (corto), viva **30 minutos**
  (30 velas M1 desde el cierre de `i`). Sin llenar ⇒ se cancela, no hay trade.
- Llenado (velas bid de MT5): largo se llena si `low_bid(M1) ≤ L − spread` (el ask tocó L); corto si
  `high_bid(M1) ≥ L`. Para que el llenado sea creíble se exige **traspasar 0,1 pip** (no alcanza con tocar).
- Salida a mercado al cierre de la vela M15 `i+16` (4 h, como P21). Largo cierra al bid, corto al ask (bid + spread).
- Costo: comisión **Fusion USD 4,50** ida y vuelta (0,45 pips) + el spread que corresponda; spread = el de la vela
  (mínimo de la barra ⇒ optimista), con piso 0,1 pip (TCA real: mediana 0,10p).
- Comparador pareado: la MISMA señal entrando a mercado al cierre de `i` (ask/bid), misma salida.

## Criterio (las 5; decide la principal)

1. n llenadas ≥ 1.500.
2. neto medio > 0 y CI95 bootstrap inferior > 0 (pips por operación llenada, Fusion).
3. las dos mitades cronológicas > 0.
4. neto > p95 de un control: barras y direcciones al azar (misma proporción de largos), misma mecánica de
   límite y llenado, 200 repeticiones.
5. el límite le gana al mercado sobre el mismo set de señales (neto por SEÑAL, contando las no llenadas como 0,
   mayor que el neto por señal a mercado).

Descriptivos (no deciden): offset 0 y 0,5·sd; vida 15 y 60 min; comisión IC USD 7; tasa de llenado; neto de las
señales que NO se llenaron si hubieran entrado a mercado (mide la selección adversa directamente).

## Si no pasa

Se cierra A1 en EUR/USD por el lado de la ejecución: no se barren offset, vida ni horizonte sobre esta data.
Con eso A1 queda cerrado en todas sus variantes (instrumento, broker, binaria en backtest, entrada).
El shadow P13b (binaria en vivo) sigue aparte con su propio criterio.

## Límites

- Velas M1, no ticks: dentro de un minuto no se sabe el orden de high/low; el llenado con traspaso de 0,1 pip
  es una aproximación (sin cola de órdenes).
- Spread mínimo de la barra: optimista para el mercado y para el límite por igual.
