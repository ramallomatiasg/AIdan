# P44 — Gotobi de FIN DE MES en CHFJPY y NZDJPY (reservados): criterio declarado ANTES de medir (14-nov-2026)

**Hipótesis:** en P38 el corto del cruce con yen de 00:55 a 03:00 UTC (después del fixing de Tokio) le ganó al
control, y el diagnóstico hecho DESPUÉS de mirar mostró que casi todo venía del gotobi de fin de mes (EURJPY +10,3p
n=80 contra +1,0p el resto). Como esa idea sale de mirar, se prueba **solo** en los dos pares con yen reservados de
Fase 4, que nunca se abrieron: CHFJPY y NZDJPY. Tipo **B** (flujo forzado de calendario). Prior bajo-medio.

## Datos
- `.cache_fase2/M5_500000/{CHFJPY,NZDJPY}` (MT5 ICMarkets) vía `load_pair` de `backtest_fase4_planes.py`.
- Antes de declarar solo se miró el largo del cache (500.000 velas cada uno, 2019-12-04 → 2026-08-18) y la comisión
  de la spec (1,117 pips). **Ningún precio.**
- Costo: comisión + spread de la vela de entrada (mínimo de la vela ⇒ cota optimista). Pesimista: +0,3 pips.
  Sin swap (no cruza el rollover).

## Evento
**Último día hábil del mes** (lunes a viernes; sin feriados de Japón), dic-2019 → jul-2026 (meses completos del cache).

## Regla (fija)
- **Entrada:** apertura de la vela M5 de las 00:55 UTC, **corto** el cruce.
- **Salida:** apertura de la vela M5 de las 03:00 UTC.
- Falta una de las dos velas ⇒ evento descartado y contado. Neto en pips.

## Control (placebo)
Misma ventana corta 00:55 → 03:00 UTC en los días hábiles que **no** son último día hábil del mes, del mismo año;
2000 repeticiones de la media de n eventos tomados al azar por año ⇒ percentil 95. En conjunto.

## Criterios (PASA = los 6, sobre los dos pares juntos)
1. n ≥ 120 eventos en total (esperados ~160; muestra chica por construcción, declarada).
2. Media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > percentil 95 del control (tiene que ser el día, no la hora).
5. Media neta > 0 con el costo pesimista (+0,3 pips).
6. Cada par por separado con media neta > 0.

## Descriptivo (no decide)
Bruto, % ganados, por año, por par; resto de los gotobi (5/10/15/20/25) en los mismos pares.

## Si PASA
No se activa. Siguiente paso: papel en vivo (una orden por mes por par), con el lote mínimo y el peor caso en USD.
## Si NO PASA
Cerrar Gotobi/fixing de Tokio en todas sus variantes y pares. No probar otras horas, otros cruces ni subconjuntos.
