# P27 — juez LLM con contexto completo sobre las señales de AIdan — criterio declarado ANTES de medir

**Fecha:** 4-nov-2026. **Pedido del user:** que la IA de AIdan decida *"no solo basado en cálculos sino en el
razonamiento como juez"*, viendo velas de todas las temporalidades, sobre las estrategias que hoy se disparan solas.
**Tool:** `tools/backtest_p27_llm_judge.py` (read-only respecto de AIdan: DB `mode=ro`, sin MT5; velas del cache M1
de P23 resampleadas; base propia `state/llm_judge_retro.db`).

## Por qué la 1ra prueba (shadow trader, v3.60.0) no fue justa

Revisado el 4-nov sobre `shadow_trader_log` (125 decisiones direccionales, ago-sep): el modelo veía ~10 datos de M5
(precio, RSI, ATR y las ETIQUETAS de AIdan: "trend bearish", "momentum down"), sin velas ni otras temporalidades,
con razonamiento en `low`, y elegía dirección desde cero cada 15 min. El **100%** de sus razones arranca con la
tendencia ⇒ copió el sesgo de AIdan (entrar a favor del movimiento ya hecho): acierto bruto 37% antes de costos,
y peor cuanto más confiado (conf 60-70: −8,8p; <60: −0,3p). Mide "LLM ciego repitiendo etiquetas", no "LLM juez".

## Qué se prueba ahora

- **Universo:** los **300 trades reales más recientes** de AIdan con `mt5_pnl` hasta el 9-oct-2026 (26-jun → 9-oct;
  el cache M1 termina el 9-oct), todos los tracks. Resultado = `mt5_pnl` del broker.
- **Lo que ve el juez:** la señal (dirección, track, SL y TP en pips), hora UTC y día de semana, velas CERRADAS antes de
  la entrada en D1 (20), H4 (30), H1 (36), M15 (32) y M5 (36) en pips relativos al último precio, ATR14 por
  temporalidad, máx/mín de ayer y de hoy, distancia al redondo de 50 pips. **Sin fechas ni precios absolutos** (para que
  no reconozca el día), **sin la confianza ni las etiquetas de AIdan** (anti-loro), sin noticias (los títulos traen
  fechas). Desfase AR → server verificado: +6 h (entrada vs cierre M1, mediana 0,4 pips).
- **Pregunta:** TAKE o VETO, con confianza y razón.
- **Modelo:** `gpt-oss:20b` **local** (Ollama, RTX 5080 16 GB), razonamiento `medium`, temperatura 0,2.
  Por qué no Groq: el límite gratis de `gpt-oss-120b` es 8.000 tokens/min y **200.000 tokens/día por organización**
  (las keys extra no suman). Medido el 4-nov: un juicio son ~3.000 tokens de entrada + 2.000-6.000 de razonamiento
  ⇒ 600 juicios (main + placebo) ≈ 3-5 M tokens ⇒ **15-25 días** de cuota, compitiendo con lo que AIdan ya usa.
  Con `high` la llamada de prueba agotó 6.000 tokens pensando y no contestó.
- **Placebo:** la misma señal con las velas de OTRO trade al azar (derangement, semilla 20261104).

## Criterio (las 5; NO mover)

1. n juzgados (main) ≥ 250.
2. Tasa de veto entre 15% y 85% (si aprueba o veta casi todo, no está juzgando).
3. PnL medio de los TAKE − PnL medio de los VETO > 0, con CI95 bootstrap inferior > 0.
4. Esa diferencia > 0 en las dos mitades cronológicas.
5. El placebo separa menos: diferencia del placebo < la del main, y su CI inferior ≤ 0.

**Pasa ⇒** juez en papel en vivo sobre cada señal nueva (~4 semanas, criterio propio) y recién después, con OK del
user, poder de veto real. **No pasa ⇒** se registra; no se barren modelo, prompt ni temporalidades sobre estos 300
trades (cualquier re-intento va sobre trades NUEVOS, posteriores al 9-oct).

## Descriptivos (no deciden)

PnL total de lo aprobado vs todo; por track; confianza del juez vs resultado; ejemplos de razones.

## Límites

- 300 trades: alcanza para ver separación grande, no chica.
- Un modelo puede "reconocer" un período por la forma del gráfico aunque no tenga fechas; el placebo lo acota.
- Las velas M1 de MT5 guardan el spread mínimo; no afecta: el resultado es el `mt5_pnl` real.

## P27b — misma prueba + calendario económico (declarada el 4-nov, ANTES de ver cualquier resultado de P27)

**Pedido del user:** que el juez sepa si se viene una noticia que pueda dar vuelta la operación.

- **Qué cambia:** solo una línea más en el prompt, sacada de `event_window_log`, que AIdan registró EN EL MOMENTO
  de cada ejecución (no reconstruida): próximo evento del calendario (nombre, impacto, minutos que faltan) y el
  anterior (nombre, impacto, minutos desde). Sin fechas: el nombre del evento ("Non-Farm Employment Change") no
  identifica el día. Mismo modelo, mismo razonamiento, mismas velas.
- **Universo:** los trades de los 300 que tienen fila en `event_window_log` (283). Los 17 sin fila se excluyen (no
  tener fila no es lo mismo que no tener evento).
- **Criterio P27b (las 5; NO mover):**
  1. n juzgados ≥ 250.
  2. Tasa de veto entre 15% y 85%.
  3. TAKE − VETO > 0 con CI95 bootstrap inferior > 0.
  4. Esa diferencia > 0 en las dos mitades.
  5. **Aporta sobre P27:** sobre los MISMOS trades, (separación con calendario − separación sin calendario) > 0 con
     CI95 de bootstrap pareado (remuestreando trades) inferior > 0.
- **Descriptivo:** subconjunto con evento de impacto alto a ≤ 60 min (antes) o ≤ 30 min (después): tasa de veto y
  separación con y sin calendario.
- **Orden:** corre después de P27; los dos se reportan juntos.

## P27c — juez + calendario + MEMORIA de casos pasados (declarada el 4-nov, ANTES de ver resultados de P27/P27b)

**Pedido del user:** que el juez entre en un loop de aprendizaje.

- **Qué cambia respecto de P27b:** se agrega un bloque con los **5 casos pasados más parecidos** y cómo terminaron.
  Cada caso: dirección, track, resumen del contexto (cambio de H4 en las últimas 6 velas, de H1 en las últimas 12,
  ATR de M15, si había evento alto cerca), **lo que decidió el juez en ese caso** (si ya lo juzgó en esta variante)
  y el resultado real (ganó/perdió, pips).
- **Sin mirar el futuro:** solo entran trades **ya cerrados** antes de la entrada que se juzga (`archived_at` <
  `created_at`, cota conservadora del cierre). Los trades se juzgan en orden cronológico, así la decisión del juez
  en un caso viejo ya existe cuando aparece como memoria. Es exactamente lo que pasaría en vivo.
- **Parecido:** misma dirección y mismo track primero; dentro de eso, distancia en (cambio H4, cambio H1, ATR M15,
  evento alto cerca) normalizados. Fijo, no se ajusta.
- **Universo:** los mismos 283 de P27b. Se evalúa sobre los que tienen ≥ 20 trades cerrados previos (la memoria
  necesita material).
- **Criterio P27c (las 5; NO mover):**
  1. n evaluados ≥ 200.
  2. Tasa de veto entre 15% y 85%.
  3. TAKE − VETO > 0 con CI95 bootstrap inferior > 0.
  4. Esa diferencia > 0 en las dos mitades.
  5. **Aporta sobre P27b:** sobre los MISMOS trades, (separación con memoria − separación de P27b) > 0 con CI95 de
     bootstrap pareado inferior > 0.
- **Descriptivo:** ¿el aporte de la memoria crece con el tiempo? (último tercio vs primer tercio).
- **Si pasa:** es el diseño del loop en vivo (cada trade que cierra se suma a la memoria). **Si no pasa:** no se
  barren K, la medida de parecido ni el formato sobre estos trades.
