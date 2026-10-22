# P4 — lead-lag de la cesta USD ("catch-up") — criterio declarado ANTES de medir

**Fecha:** 22-oct-2026 (pedido del user: "seguí con P4"). **Tool:** `tools/backtest_p4_lead_lag.py` (read-only,
sin MT5, no toca la DB). Lee `.cache_fase2/M5_500000`.

## Pregunta

Cuando el dólar se mueve, las monedas contra el USD suelen moverse juntas. **Si tres de ellas ya se movieron en
la misma dirección en los últimos 30 min y la cuarta todavía no, ¿la cuarta "alcanza" lo suficiente para pagar el
costo?** Nunca medido acá.

## Universo

- **In-sample (decide):** los 4 mayores XXX/USD con 6,7 años de M5: EURUSD, GBPUSD, AUDUSD, NZDUSD. Cada uno es
  "objetivo" con los otros tres como cesta (misma orientación: suben todos si cae el USD).
- **Fuera de muestra (solo si pasa):** la cesta JPY con la misma regla: objetivos **CHFJPY y NZDJPY** (reservados,
  nunca mirados), cesta = los otros XXX/JPY con 6,7 años (EURJPY, GBPJPY, USDJPY) más el otro objetivo.

## Señal (congelada)

En el cierre de la vela M5 `i`, con las velas alineadas por timestamp entre los 4 instrumentos:
- `r_k = (close[i] − close[i−6]) / ATR20_k[i]` para cada instrumento (movimiento de 30 min en unidades de su
  ATR de 20 velas M5; ATR = media simple del true range).
- **Largo el objetivo** si los tres de la cesta tienen `r ≥ +1,0` y el objetivo `−0,25 ≤ r ≤ +0,25`.
  **Corto** con los signos invertidos.
- Entrada al close de `i`.

## Ejecución (congelada)

- **Salida por tiempo a H6** (6 velas = 30 min), sin SL ni TP. H3 y H12 se reportan como secundarios.
- Una posición por objetivo a la vez.
- Sin entradas en [23:00, 01:00) server, ni si la salida cae en otro día server, ni si hay un hueco en las velas
  del objetivo entre `i` y `i+6` (⇒ sin swap).

## Costos

Comisión Raw del spec (0,7p en los XXX/USD) + spread de la vela de entrada (mínimo de la barra ⇒ cota
optimista, piso 0,1p como TCA). En pips.

## Criterio de PASA (los 5, pool de los 4 objetivos, a H6)

1. n ≥ 1.000 trades.
2. Media neta > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control: 200 réplicas con entradas al azar entre las velas elegibles (mismo n por
   objetivo, mismo ratio largo/corto, misma salida y costos).
5. ≥ 3 de 4 objetivos con media neta > 0.

**Si pasa:** correr la cesta JPY una sola vez; pasa fuera de muestra si el pool de los 2 objetivos tiene media
neta > 0 y > p95 del control. Solo con las dos cosas se propone shadow en EURUSD.
**Si no pasa:** el lead-lag de la cesta queda cerrado sobre esta data; no se barren ventana, umbrales ni horizonte,
y los reservados no se miran.

## Límites

Sin slippage. Velas M5 cerradas: un catch-up que pasa dentro de los 5 minutos no se ve (la señal llega tarde por
construcción, igual que en vivo). Cinco de los 20 pares de la línea no entran (USDCAD etc. arrancan en 2025).
