# P5 — compresión → expansión en D1: ruptura del NR7 — criterio declarado ANTES de medir

**Fecha:** 22-oct-2026 (pedido del user: "seguí con P5"). **Tool:** `tools/backtest_p5_nr7.py` (read-only, sin MT5,
no toca la DB). Reusa piezas de `tools/backtest_p2_donchian.py` (carga, re-muestreo a D1, swap) sobre
`.cache_fase2/M5_500000`.

## Pregunta

Después de un día de rango anormalmente chico (Crabel: NR7, el rango más chico de los últimos 7 días), ¿la
ruptura del día siguiente sigue lo suficiente para pagar el costo? Horizonte de días ⇒ costo ~1% del movimiento.
Nunca medido acá. Distinto de P2 (canal de 20 días, sin condición de compresión).

## Reglas (congeladas)

- **Barra NR7:** día D1 `k` (día del server, re-muestreado desde M5 como P2) cuyo rango alto−bajo es el menor de
  los días `k−6..k`.
- **Órdenes (OCO)** el día `k+1`: stop de compra en el máximo de `k`, stop de venta en el mínimo de `k`, activas
  de 01:00 a 23:00 server (fuera del rollover). Si no se toca ninguna, se cancela.
- **Llenado:** la primera vela M5 que toca un nivel; si abre más allá, al open (gap). Si una misma vela M5 toca
  los dos niveles, el trade se descarta (ambiguo, se cuenta).
- **Stop:** el otro extremo de `k` (1R = rango de `k`). Si la vela del llenado también toca el stop, cuenta como
  stop (peor caso).
- **Salida:** por tiempo al cierre del día `k+3` (tres sesiones con la del llenado), ejecutada en la primera vela
  M5 posterior fuera de [23:00, 01:00) como en P2; o el stop antes.
- Una posición por par a la vez. **Principal: NR7.** Secundario descriptivo: inside bar (máx < máx anterior y
  mín > mín anterior) con las mismas reglas.

## Costos

Comisión Raw del spec + spread de la vela de entrada y de salida (piso 0,1p) + swap real del spec por noche
(miércoles ×3), igual que P2.

## Métrica

Neto por trade en R.

## Control

Mismas entradas (misma vela M5, mismo R, misma salida y costos) con **dirección al azar**, 200 réplicas. Responde
si la dirección de la ruptura aporta algo.

## Criterio de PASA (los 5, principal, pool de los 20 pares de Fase 1)

1. n ≥ 300 trades.
2. Media neta > 0 con CI95 bootstrap cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control.
5. ≥ 12 de 20 pares con media neta > 0.

**Si pasa:** correr los 6 reservados una sola vez; pasa fuera de muestra con media > 0 y > p95 del control.
**Si no pasa:** cerrado NR7/inside bar D1 en FX sobre esta data; no se barren N, salida ni stop.

## Límites

Sin slippage en el gap del llenado (se llena al open). Swap del spec = el actual. Cinco pares tienen M5 solo
desde 2025 (n chico en esos).
