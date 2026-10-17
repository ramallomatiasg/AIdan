# P3 — rango asiático → ruptura de Londres — criterio declarado ANTES de medir

**Fecha:** 17-oct-2026 (rutina semanal). **Tool:** `tools/backtest_p3_rango_asiatico.py` (read-only, sin MT5,
no toca la DB). Lee `.cache_fase2/M5_500000` (FX, 2019-12 → 2026-08).

## Pregunta

El research del 19-ago rankeó el "London breakout" sobre el rango asiático y nunca se midió acá. Es
confluencia + sesión, lo único que sobrevivió en el estudio de falsificación externo. Antecedentes en
contra que hay que tener presentes: toda ruptura intradía medida acá revirtió (Fases 2/2b/3, P1) y de 28,7 M
configuraciones de ORB sobrevivió el 0,51%. **¿La ruptura del rango asiático en la apertura de Londres tiene
edge neto en FX?** Una sola configuración, sin barrer parámetros.

## Reglas (congeladas)

- **Reloj:** las velas vienen en hora server = hora de Nueva York + 7h (verificado: la semana va de
  00:00 lunes a 23:55 viernes server). Se convierten a UTC con el DST de NY y a hora local de Londres con
  el DST de Londres (`zoneinfo`).
- **Día:** fecha local de Londres, lunes a viernes.
- **Rango asiático:** máximo y mínimo de las velas M5 con hora Londres en [00:00, 07:00). Se exige ≥ 70 de
  las 84 velas; si no, el día no opera. Ancho W = máx − mín. Sin filtro de ancho en el principal.
- **Órdenes:** stop de compra en el máximo y stop de venta en el mínimo, activas en [07:00, 12:00) Londres.
  Llenado: primera vela cuyo high ≥ máximo (compra) / low ≤ mínimo (venta), al precio del nivel o a la
  apertura si la vela abre más allá (gap). OCO: la primera que se llena cancela la otra; un trade por día.
- **Ambigüedad:** si la misma vela cruza los dos niveles ⇒ se cuenta **−1R − costo** (pesimista). Si en
  una vela se tocan stop y objetivo ⇒ stop primero.
- **Stop:** el otro extremo del rango (1R = W). **Objetivo (principal):** 1·W desde la entrada.
  Secundario descriptivo: 2·W.
- **Salida por tiempo:** si no tocó ni stop ni objetivo, cierre a la apertura de la primera vela ≥ 16:00
  Londres. No cruza el rollover ⇒ sin swap.

## Costos

Comisión del spec (Raw, round-turn) + spread de la vela de entrada y de la de salida (mínimo de la barra ⇒
cota OPTIMISTA, piso 0,1p, igual que P1/P2).

## Métrica

Neto por trade en **R** (1R = W) para juntar pares; también en pips.

## Criterio de PASA (los 5, sobre el principal, pool de los 20 pares de Fase 1)

1. n ≥ 300 trades.
2. Media neta > 0 con CI95 bootstrap (límite inferior > 0).
3. Positiva en las dos mitades cronológicas.
4. Mayor que el p95 del control: 200 réplicas donde en los MISMOS días operados se entra en una vela al
   azar de [07:00, 12:00) Londres, dirección al azar, con la misma geometría (stop y objetivo a W de la
   entrada), misma salida por tiempo y mismos costos.
5. ≥ 12 de 20 pares con media neta > 0.

**Si pasa:** correr los 6 reservados una sola vez con la misma regla, y recién ahí hablar de shadow.
**Si no pasa:** los reservados no se miran y se cierra "rango asiático → Londres" sobre esta data (no
barrer horarios, buffer, objetivo ni filtro de ancho). El 2·W y los terciles de ancho son descriptivos y no
rescatan al principal.
