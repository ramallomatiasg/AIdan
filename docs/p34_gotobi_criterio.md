# P34 — Efecto Gotobi en USD/JPY: criterio declarado ANTES de medir (11-nov-2026)

**Hipótesis (Ito & Yamada 2017; Bessho et al.):** los importadores japoneses compran dólares en el fixing de Tokio
(9:55 hora de Tokio = 00:55 UTC, Japón no tiene horario de verano) los días de pago "gotobi" (5, 10, 15, 20, 25 y
fin de mes). Esa demanda hace subir el USDJPY antes del fixing. Tipo **B** de la escalera: flujo forzado de
calendario, no mira el gráfico.

## Datos
- `.cache_fase2/M5_500000/USDJPY` (MT5 ICMarkets), dic-2019 → ago-2026. Hora del server = UTC+2/+3 según horario de
  verano de EE.UU. (mismo mapeo que `backtest_fase4_planes.py`).
- Antes de declarar solo se miró el rango de fechas y el formato del cache (no retornos).
- Costo: comisión real de la spec (1,117 pips ida y vuelta) + spread de la vela de entrada. El spread del cache es el
  **mínimo** de la vela (cota optimista, igual que Fase 3b) ⇒ descriptivo pesimista con +0,3 pips extra. Sin swap
  (no cruza el rollover).

## Días gotobi (por regla)
Días 5, 10, 15, 20, 25 y el último día del mes. Si cae sábado o domingo, el viernes anterior. Feriados de Japón
**no** se modelan (declarado: se pierde precisión, no se agrega después de mirar). Lunes a viernes solamente.

## Regla (fija, sin parámetros que buscar)
- **Entrada:** apertura de la vela M5 de las 00:00 UTC del día gotobi, largo USDJPY.
- **Salida:** apertura de la vela M5 de las 00:55 UTC (el fixing).
- Falta una de las dos velas ⇒ evento descartado y contado.
- Neto en pips por evento.

## Control (placebo)
Misma ventana 00:00 → 00:55 UTC en días hábiles **no gotobi** del mismo año. 2000 repeticiones de la media de n
eventos tomados al azar por año → percentil 95. Responde: ¿el gotobi es especial o la ventana sube siempre?

## Criterios (PASA = los 5)
1. n ≥ 300 eventos.
2. Media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > percentil 95 del control.
5. Media neta > 0 también con el costo pesimista (+0,3 pips).

## Descriptivo (no decide)
Bruto, % de eventos ganadores, por año, y el tramo posterior **00:55 → 03:00 UTC** corto (reversión después del
fixing, también citada en la literatura).

## Si PASA
No se activa. Siguiente paso a proponer: papel en vivo + el mismo efecto en otro cruce con yen nunca mirado
(EURJPY/AUDJPY como fuera de muestra, declarado ahora).
## Si NO PASA
Cerrar Gotobi en CFDs/FX con este costo. No probar otra ventana, otro horario ni subconjuntos de días.
