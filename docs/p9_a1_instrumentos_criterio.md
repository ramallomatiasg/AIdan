# P9 — A1 (reversión a 2σ) en oro e índices — criterio declarado ANTES de medir

**Fecha:** 22-oct-2026 (pedido del user: "vamos con tus propuestas"). **Tool:** `tools/backtest_p9_a1_instrumentos.py`
(read-only, sin MT5, no toca la DB). Lee `.cache_p1/M15` (EURUSD, XAUUSD, USTEC, US30, DE40; 150k velas M15,
2020 → 2026-10-09).

## Pregunta

A1 fue la única señal de toda la línea que le ganó al azar (Fase 3b: ~+0,5p bruto sobre el control en FX M5) y
murió por costo (comisión 0,85 + spread 0,63 + swap 0,18 ⇒ neto −1,01p). En P1 el costo en oro e índices dio
0,20-0,28 pseudo-pips contra 0,80 en EURUSD. **¿La misma reversión, en instrumentos 3-4x más baratos, queda neta
positiva?**

## Señal (congelada, la de `screen_generators.gen_A1`, importada)

MA(20) y desvío poblacional(20) del close; `z > +2` ⇒ corto, `z < −2` ⇒ largo; entrada al close de la vela señal.
**Diferencia declarada con Fase 3b:** el cache de oro/índices es M15 (no hay M5 sin MT5), así que la ventana de 20
velas son 5 h en vez de 100 min. Por eso se corre EURUSD M15 en el mismo tool como **ancla descriptiva** (no decide).

## Ejecución (congelada)

- **Salida por tiempo a H32** (32 velas M15 = 8 h, el mismo reloj que H96 de Fase 3b), sin SL ni TP.
  H4 (1 h) y H16 (4 h) se reportan como secundarios, no deciden.
- **Una posición por instrumento a la vez.**
- **Sin cruzar el rollover:** se descartan las entradas en [23:00, 01:00) server y las que saldrían después del
  00:00 server siguiente (el cache de oro/índices no trae swap, y el spread se abre en el rollover). Así no hay
  swap que estimar.
- **Unidad: pseudo-pips** como P1 (mediana del rango M15 del instrumento / mediana del de EURUSD en pips), para
  poder juntar instrumentos.

## Costos

Spread de la vela de entrada (`spread` × point; mínimo de la barra ⇒ cota optimista; EURUSD con piso 0,1p) +
comisión Raw round-turn (EURUSD y oro $7/lote; índices 0), igual que P1.

## Criterio de PASA (los 5, pool de los 4 nuevos: XAUUSD, USTEC, US30, DE40, a H32)

1. n ≥ 2.000 trades.
2. Media neta > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control: 200 réplicas con entradas al azar entre las velas elegibles (mismo n por
   instrumento, mismo ratio largo/corto, misma salida, mismos costos, misma exclusión del rollover).
5. ≥ 3 de 4 instrumentos con media neta > 0.

**Si pasa:** fuera de muestra en instrumentos nunca mirados (US500, JP225, XAGUSD), bajando el cache con AIdan
cerrado, una sola corrida, con la misma regla. Solo con eso se propone shadow en vivo.
**Si no pasa:** la reversión a 2σ queda cerrada también en oro/índices sobre esta data; no se barren umbral,
media, horizonte ni filtros.

## Límites

Sin slippage. Spread de la vela = cota optimista (en índices el spread real en la apertura de NY es más ancho).
Los índices tienen deriva alcista 2020-26 ⇒ se reporta largo vs corto por separado: si todo el neto sale de un
lado, es la deriva y no la señal (la trampa de P2 en oro).
