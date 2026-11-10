# P30 — hora del día en índices europeos, fuera de muestra — criterio declarado ANTES de medir

**Fecha:** 9-nov-2026. **Origen:** P29 (`docs/p29_info_screen_criterio.md`): de 138 celdas de dirección pasó UNA,
DE40 · F1 hora del día · h=16 velas M15 (4 h): neto +3,47 bps, CI [+0,72, +6,40]. Con 138 celdas, una que pase puede
ser azar. Si es un flujo real de la sesión europea, tiene que aparecer en índices y fechas que P29 nunca miró.
**Tool:** `tools/backtest_p30_hora_europa.py` (read-only: sin MT5, sin DB de AIdan; caches `.cache_p1/M15` ya bajados).

## Prueba principal (decide)

- **Mapa congelado:** retorno medio a 16 velas por hora de servidor de DE40, estimado SOLO en el descubrimiento de
  P29 (primer 70% de DE40, abr-2020 → ~sep-2024), exactamente con la función de P29. Cortes de quintil del mismo
  descubrimiento. No se re-estima nada.
- **Dónde se aplica:** STOXX50 y F40 (CAC 40) en la ventana **2017-08-21 → 2020-04-17**, ANTERIOR a la primera vela de
  DE40 ⇒ fuera de muestra en instrumento Y en tiempo (P29 no vio ninguna de esas velas en ningún instrumento europeo).
- **Regla:** cada 16 velas, comprar si la hora está en el quintil superior del mapa, vender si está en el inferior,
  no operar en el resto; salir 16 velas después.
- **Costo:** spread mediano del instrumento en esa ventana (cota optimista: MT5 guarda el mínimo de la vela) en la
  entrada; + swap actual de MT5 (`meta.json`, por lote / precio mediano de la ventana) por cada cambio de fecha de
  servidor entre entrada y salida. El swap de hoy no es el de 2017-19 (tasas negativas del BCE) ⇒ también se reporta
  el neto sin swap; decide el neto CON swap.

**PASA si, en STOXX50 Y en F40 (los dos):**
1. n de operaciones ≥ 200.
2. IC de Spearman (mapa vs retorno a 16 velas) > 0 y mayor que el p95 de 200 corrimientos circulares del mapa
   (placebo, semilla 20261109).
3. Neto medio por operación > 0.
4. CI95 bootstrap inferior del neto > 0.
5. El largo/corto le gana a "siempre comprado" en la misma ventana y con las mismas entradas (exceso > 0), para que no
   sea la deriva del índice.

## Secundario (descriptivo, no decide)

- P29 F1 tal cual (70/30 propio, h = 4/16/96) en STOXX50, F40 y UK100 (UK100 recién desde abr-2020).
- Horas del quintil superior/inferior de cada mapa, para ver si coinciden con las de DE40 (05-08 y 20 servidor).

## Qué se hace con el resultado

- **PASA:** no se opera. Siguiente paso propuesto al user (Plan/Razón/Pros/Contras/Opinión): shadow en papel en DE40 y
  STOXX50 con el mapa congelado.
- **NO PASA:** se cierra la hora del día en índices europeos; el pase de DE40 en P29 queda como el azar esperable de
  138 celdas. No se buscan otras horas, horizontes ni instrumentos sobre esta data.
