# P1 — misma lógica, otro instrumento (criterio declarado ANTES de medir)

**Fecha:** 10-oct-2026 (rutina semanal). **Tool:** `tools/backtest_p1_instrumentos.py` (read-only, no toca la DB, MT5 solo para bajar velas con AIdan cerrado).

## Pregunta

En EURUSD M15 el detector `structure` pierde −1,04p/trade y le hace falta acertar ~55% de las
direcciones solo para pagar el costo (P0, 9-oct). En oro e índices el costo es 6-10x más chico frente
al rango de la vela (screen del 9-oct: EURUSD ~15% del rango M15, XAUUSD 1,5%, USTEC/US30 2,3%,
DE40 1,5%). **¿La MISMA lógica, con la misma geometría relativa, deja de perder ahí?**

## Cómo se hace comparable (decisión de diseño, declarada antes)

`technical.py` razona en pips de EURUSD (constantes de 7p, 12-15p, etc.). Pasarle oro en "pips" de
$0,01 sería medir otro sistema. Por eso cada instrumento se mide en **pseudo-pips**:

    pseudo_pip(sym) = mediana del rango (high−low) de las velas M15 de sym / mediana del de EURUSD (en pips)

calculado sobre todo el cache de cada uno. Con eso la vela mediana de oro "mide" lo mismo que la de
EURUSD (~5p), las constantes del detector quedan en la misma proporción, y el perfil vivo de M15
(SL 15 / TP 60 / 3 velas, `min_confidence` 60) se aplica tal cual en pseudo-pips. Lo único que cambia
entre instrumentos es **el costo expresado en pseudo-pips** — que es exactamente la hipótesis.

## Costos (en pseudo-pips del instrumento)

- **Spread:** el de cada vela de entrada (`spread` de MT5 × point). Es el MÍNIMO de la barra ⇒ cota
  OPTIMISTA, igual que en Fase 3b; pareja para todos los instrumentos. Para EURUSD, donde la vela
  trae 0, se usa piso 0,1p (TCA real, mediana 0,10p).
- **Comisión:** IC Markets Raw. FX: $7/lote round-turn. XAUUSD: $7/lote RT (100 oz). Índices: 0.
- **Swap:** NO se descuenta (hold de 45 min). Se reporta la fracción de trades que cruzan el rollover
  (21-22 UTC); si supera 5% se declara como límite.

## Universo y sesión

XAUUSD, USTEC, US30, DE40 (los del screen) + **EURUSD como ancla** (tiene que reproducir el orden de
magnitud de Fase 2, −1,0p ± 0,3, o el tool está mal y se aborta la lectura). Velas M15, todas las que
dé MT5 (piso 50.000). Sesión del detector: `london` (la de titular de Fase 2), una sola corrida.

## Criterio de PASA (los 4, sobre el pool de los 4 instrumentos nuevos, sin EURUSD)

1. Neto medio por trade > 0.
2. CI95 bootstrap con extremo inferior > 0.
3. Positivo en las dos mitades temporales.
4. Mayor que el p95 del control (entradas al azar, mismo n, mismo ratio long/short, mismos SL/TP/hold y costos).

Más: **al menos 3 de 4 instrumentos con neto > 0**.

## Qué se hace con el resultado

- **PASA:** no se toca producción. Se propone un shadow de `structure` sobre el instrumento ganador
  (Plan/Razón/Pros/Contras) y se re-mide en datos que no se miraron (otros índices: UK100, JP225, F40).
- **NO PASA pero le gana al control:** la lógica tiene información y el costo no era el único
  problema ⇒ queda registrado; no se buscan variantes (SL/TP/sesión) sobre esta data.
- **NO PASA y no le gana al control:** la lógica de `structure` no tiene edge tampoco donde el costo
  es chico ⇒ el problema es la idea, no la fricción. Se cierra P1 para `structure` y entra P2.

No afinar nada después de ver el resultado.
