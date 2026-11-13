# P38 — Reversión después del fixing de Tokio en EURJPY y AUDJPY: criterio declarado ANTES de medir (12-nov-2026)

**Hipótesis:** el flujo de compra de dólares de los días gotobi (fixing de Tokio, 9:55 JST = 00:55 UTC) empuja el yen
antes del fixing y la presión se deshace después. En P34 el tramo corto 00:55 → 03:00 UTC en USDJPY (declarado como
descriptivo antes de medir) dio +2,68 pips neto. Puede ser el rebote del fixing o una caída de esa hora que pasa
todos los días: el control lo separa. Tipo **B** (flujo forzado de calendario). Prior bajo.

**Por qué en estos pares:** el criterio de P34 ya declaraba EURJPY/AUDJPY como fuera de muestra del efecto Gotobi.
Están en los 20 pares de Fases 2-6 (se usaron para otras señales), pero **nunca se miró esta ventana en ellos**.
USDJPY no decide (ya se miró).

## Datos
- `.cache_fase2/M5_500000/EURJPY` y `AUDJPY` (MT5 ICMarkets), dic-2019 → ago-2026, mismo mapeo de hora que P34
  (`load_pair` de `backtest_fase4_planes.py`). Antes de declarar solo se miró la spec (comisión 1,117 pips).
- Costo: comisión de la spec + spread de la vela de entrada (mínimo de la vela ⇒ cota optimista). Pesimista: +0,3 pips.
  Sin swap (no cruza el rollover).

## Días gotobi
Misma regla de P34 (5, 10, 15, 20, 25 y último del mes; fin de semana ⇒ viernes anterior; sin feriados de Japón).

## Regla (fija)
- **Entrada:** apertura de la vela M5 de las 00:55 UTC del día gotobi, **corto** el cruce.
- **Salida:** apertura de la vela M5 de las 03:00 UTC.
- Falta una de las dos velas ⇒ evento descartado y contado. Neto en pips.

## Control (placebo)
Misma ventana corta 00:55 → 03:00 UTC en días hábiles **no gotobi** del mismo año; 2000 repeticiones de la media de n
eventos tomados al azar por año ⇒ percentil 95. Por par, y en conjunto.

## Criterios (PASA = los 6, sobre los dos pares juntos)
1. n ≥ 600 eventos en total.
2. Media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > percentil 95 del control (la ventana tiene que ser especial los días gotobi).
5. Media neta > 0 con el costo pesimista (+0,3 pips).
6. Cada par por separado con media neta > 0.

## Descriptivo (no decide)
Bruto, % ganados, por año, por par; USDJPY con el mismo control (para saber si el +2,68 de P34 era gotobi o la hora).

## Si PASA
No se activa. Siguiente paso: papel en vivo y los JPY reservados (CHFJPY, NZDJPY), declarado ahora.
## Si NO PASA
Cerrar Gotobi en todas sus ventanas en CFDs con este costo. No probar otras horas, otros cruces ni subconjuntos.
