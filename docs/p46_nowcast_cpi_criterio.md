# P46 — nowcast de inflación de la Fed de Cleveland contra el consenso, antes del CPI — criterio declarado ANTES de medir

**Fecha:** 16-nov-2026 (investigación diaria). **Tool:** `tools/backtest_p46_nowcast_cpi.py` (read-only, sin MT5,
no toca la DB).

## Datos (verificados el 16-nov, antes de medir)

- **Nowcast por día (vintage):** `clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_month.json`
  (público). Un gráfico por mes objetivo desde 2013-07 con el nowcast del CPI m/m de cada día, tal como se
  publicó. Se usa el último valor con fecha **anterior** al día del dato (se publica ~10:30 NY, conocido antes de
  la entrada). Cache `.cache_p46/nowcast_month.json`.
- **Consenso y dato:** página pública de Investing.com del CPI m/m de EE.UU. (`/economic-calendar/cpi-69`), que
  trae embebidas las publicaciones desde jun-2018 con `forecast` (consenso), `actual` y hora. Cache
  `.cache_p46/investing_cpi69.html`.
- **Precio:** EURUSD M15 de MT5 (`.cache_fase2/M15_500000`, hasta 18-ago-2026), hora del servidor = NY + 7 h.

## Regla (congelada)

- Señal = nowcast − consenso del CPI m/m (headline). Si ≥ +0,05 pp ⇒ largo USD (**venta** de EURUSD); si ≤ −0,05 pp
  ⇒ compra de EURUSD; en el medio no se opera (0,05 = medio paso del consenso, que viene a un decimal).
- Entrada: apertura de la vela de las **01:00 servidor** del día del dato (18:00 NY del día anterior; se evita la
  vela del rollover de las 00:00 por el spread). Salida: apertura de la vela de **15 min antes** de la hora del dato
  (normalmente 15:15 servidor). No cruza rollover ⇒ sin swap.
- Costo: **1,3 pips** por operación (la fricción que usa todo el proyecto para EURUSD).

## Muestra

- **Descubrimiento:** datos de jun-2018 a dic-2023. **Reserva (solo si pasa el descubrimiento):** ene-2024 →
  18-ago-2026.

## Criterio de PASA (descubrimiento, todas)

1. ≥ 30 operaciones.
2. Media neta > 0 y límite inferior del CI95 (bootstrap) > 0.
3. Media neta > 0 en las dos mitades cronológicas.
4. Le gana al azar: la media bruta supera el p95 de 5.000 direcciones al azar en las mismas ventanas.

**Reserva:** media neta > 0. **Descriptivo (no decide):** ¿el signo de (nowcast − consenso) anticipa el signo de la
sorpresa (dato − consenso)? (acierto y binomial); la misma señal manteniendo hasta 30 min DESPUÉS del dato; placebo
= mismas señales en la misma ventana de los 5 días hábiles anteriores.

**Si no pasa:** cerrado el posicionamiento pre-CPI por nowcast; no se barren umbral, ventana ni CPI core.

## Límites

- ~8-12 operaciones por año ⇒ muestra chica; un PASA solo cuenta con la reserva.
- La hipótesis es floja de origen: el nowcast es público, y lo que paga (la sorpresa) llega DESPUÉS de la salida.
  Se prueba igual porque está en la cola y es barato; la variante que atraviesa el dato queda solo descriptiva
  (es la clase de riesgo del #969).
