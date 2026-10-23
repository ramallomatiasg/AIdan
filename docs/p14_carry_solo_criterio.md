# P14 — carry SOLO (sin filtro de tendencia), SOLO en los 6 reservados — criterio declarado ANTES de medir

**Fecha:** 23-oct-2026. **Tool:** `tools/backtest_p14_carry_solo.py` (read-only, sin MT5, no toca la DB). Reusa
todo `tools/backtest_p11_carry.py` (importado): tasas, swap reconstruido con el recargo del broker, rebalanceo
semanal, costos y control.

## De dónde sale

P11 (carry + tendencia) dio NO PASA con media semanal +0,004%. En sus descriptivos, **el carry solo dio +0,037%
por posición-semana** (~+1,9%/año) y la tendencia sola −0,051% ⇒ el filtro de tendencia le RESTA al carry
(coherente con P2: en FX 2020-26 la tendencia no funciona). Como la idea sale de mirar los 20 pares, se mide
**únicamente en los 6 reservados** (CHFJPY, NZDJPY, GBPNZD, NZDCHF, NZDCAD, GBPCAD), nunca usados para carry.

## Regla (congelada)

La de P11 sin la tendencia: largo si carry ≥ +0,5 pp, corto si carry ≤ −0,5 pp, afuera si no. Todo lo demás igual
(rebalanceo semanal, tasas del mes anterior, swap reconstruido, costos solo al cambiar de posición).

## Criterio de PASA (los 4, pool de los 6 reservados)

1. n ≥ 150 posiciones-semana.
2. Media semanal neta > 0 con CI95 bootstrap (sobre semanas) cuyo límite inferior > 0.
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control (misma exposición, dirección al azar por corrida, 1.000 réplicas).

Una sola corrida. **Si pasa:** shadow en vivo como track semanal (registrar la cartera en papel cada lunes), con
la advertencia de capital de P11. **Si no pasa:** cerrado el carry en FX sobre esta data.

## Límites

Los reservados tienen 2 pares con yen, igual que los que ganaron en los 20 (el yen se desplomó 2021-24, el
período clásico de carry) ⇒ si pasa, separar cuánto viene de los pares con JPY.
