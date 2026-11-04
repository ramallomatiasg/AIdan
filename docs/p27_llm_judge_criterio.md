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
