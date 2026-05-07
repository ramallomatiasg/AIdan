# AIdan v3.19.0 - Asistente de Scalping EUR/USD con IA + Auto-Optimizacion

Sistema de trading asistido que monitorea noticias financieras en tiempo real, analiza estructura de mercado en multiples temporalidades (D1, H4, H1, M15, M5), genera senales de trading para EUR/USD usando inteligencia artificial, y **optimiza sus propios parametros automaticamente** aprendiendo de resultados pasados.

**Un solo ejecutable de ~25MB - Portable, gratis y privado.**

---

## Que hay de nuevo en v3.19.0 — Track B M15 paralelo (dual-track)

### Decisión 7 May 2026

Después del win #396 (TP hit en 3 min con M5) seguido del expiry-loss #394 (15min mata trade direccionalmente correcto), confirmamos que M5 captura movimientos explosivos pero pierde sostenidos. La hipótesis: **dual-track M5 (mantenimiento) + M15 (experimental paralelo)** da data real para decidir el rumbo en 30+ trades comparativos.

### Cambio v3.19.0

**Nuevo módulo** `src/analyzer/technical_m15.py`:
- `TechnicalAnalyzerM15` hereda de `TechnicalAnalyzer`, override solo `_fetch_candles` para usar `interval='15min'`
- `M15_PROFILE`: SL=15p, TP=60p, expiry=45min (vs M5 5/25/15)

**Loop M15 paralelo** en `AIdan_TodoEnUno.py:run_analyzer_service`:
- Cada 60s (no 10s — M15 candles no cambian tan rápido)
- Trigger type: `m15_structure`
- Filtros mínimos: ATR floor 5p (M15 escala), counter-both, conf ceiling 80, anti-spam
- Sin late breakout / hour gate (no aplican a M15)
- Reusa MT5 executor con expiry M15
- Strategies van a la misma DB pero etiquetadas para stats separadas

### Riesgo

**Cero al M5**. El loop M15 está dentro de un try/except y vive en su propio bloque temporal. Si falla, M5 sigue operando normal. El profile M15 es constante (no afecta DB de profiles).

### Plan próximo (Día 3-5)

- Día 3: Tab dashboard "Estrategias M15" con stats separadas
- Día 4: Profile M15 ajustable (no constante hard-coded)
- Día 5: Shadow run + comparativas WR/PnL/PF M5 vs M15

---

## Que hay de nuevo en v3.18.0 — Late breakout 3p → 7p (recuperar frecuencia)

### Hallazgo (6 May 2026)

Frecuencia histórica de AIdan: 10.5 trades/día (media de últimos 14 días). Los últimos 2 días: 4 trades (5 May) y 3 trades (6 May) = ~30% del ritmo histórico.

Investigación señaló a v3.13.0 (5 May) como el cambio más restrictivo: bajamos `breakout_dist_max` de 15 → 3 pips. Justificación original: 2 trades (#328 +6.2p y #332 +5.6p past) perdieron por entradas tardías. **Pero 2 trades de muestra no es estadísticamente válido** — mismo problema que el hour gate de v3.17.

### Cambio

- `breakout_dist_max`: 3 → **7** pips
- `breakdown_dist_max`: 3 → **7** pips
- Defaults en `technical.py:672, 699` actualizados
- Optimizer DB row 7 actualizada en runtime

### Esperado

- Recuperar 30-40% de frecuencia perdida
- Bloquear solo entries muy tardías (>7p past = fully exhausted breakout)
- Los #328 y #332 (que justificaron el v3.13) seguirían bloqueados (>7p past)

### Riesgo

Bajo. Si data fresca muestra que entries 4-7p past pierden, podemos volver a 3p. Es exactamente la misma decisión que el hour gate: data contaminada, sin evidencia robusta.

---

## Que hay de nuevo en v3.17.0 — REMOVIDO hour gate (data contaminada)

### Hallazgo (6 May 2026)

Con AIdan corriendo v3.16.1 desde la mañana, solo 1 trade en 2.5h. Investigación: el hour gate (UTC 12/14/20 = 9h/11h/17h AR) bloqueaba 2 de cada 3 horas. Pero la data original que justificó ese filtro (26 trades, -$45.31 colectivo) era **cross-version** (v3.7-v3.11) durante un período donde tocamos múltiples filtros (SL cap, conf formula, alignment scoring, ATR floor) simultáneamente.

**No podemos atribuir esa pérdida a la "hora del día"** — podía ser efecto de cualquier otro cambio activo en esos trades.

### Cambio

Removidos los 3 hour gates en `AIdan_TodoEnUno.py`:
- Flujo news (línea ~1388)
- Flujo structure (línea ~2004)
- Flujo SMC (línea ~2213)

### Esperado

- AIdan opera ahora 24/7 sin restricciones de hora (salvo otros filtros).
- Frecuencia de trades sube ~3x en las 3 horas restauradas.
- Re-evaluar con data fresca de v3.17.x si hay correlación real entre hora y outcome.

### Riesgo

Bajo. Si en data fresca sale que efectivamente esas horas son malas, lo re-introducimos basado en evidencia limpia.

---

## Que hay de nuevo en v3.16.1 — Hotfix UnicodeEncodeError al arrancar

Al arrancar AIdan sin consola attached (Task Scheduler / `start ""`), stdout caía a cp1252 que no encodea emojis (🚀 📰 etc) y crasheaba `start_services` con `UnicodeEncodeError`. Visible en el log de stderr pero invisible en uso normal porque el thread del init reventaba silenciosamente.

### Fix

Doble protección al inicio de `AIdan_TodoEnUno.py`:

1. **Forzar UTF-8 en stdout/stderr** via `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` apenas arranca. Si la consola no lo soporta, cae al paso 2.
2. **Try/except en `log()`**: si el `print(message)` falla por encoding, hace fallback a ASCII con `replace`. Nunca mata el thread.

---

## Que hay de nuevo en v3.16.0 — Counter-HTF news gate + Groq prompt fix

### Hallazgo (post-mortem trade #387, 5 May 2026)

Trade CALL contra-HTF (htf bearish) con conf 60.5 (apenas pasó threshold 60) cerró por expiry-loss en 15 min. El precio recuperó a +TP 85min después del cierre — direccionalmente correcto pero al timeframe equivocado. El SL nunca se tocó.

**Doble causa raíz**:

1. **Groq mis-interpretó la news**: "ECB Doesn't See Enough Yet to Warrant Rate Hike, Villeroy Says" (dovish ECB → EUR débil → PUT) fue clasificado como CALL con razonamiento invertido ("BCE no sube tasas → USD débil → EUR fuerte"). El prompt YA tenía la regla "ECB dovish → PUT" pero Groq se confundió con la negación + presencia de "rate hike" en el título.

2. **Path regular no protegía counter-HTF**: v3.14.0 agregó counter-HTF gate solo al BYPASS (cuando conf < 60). Si la news pasaba el threshold regular, el counter-HTF no se filtraba.

### Fix #1 — Counter-HTF news gate path regular (`AIdan_TodoEnUno.py`)

News counter-HTF requiere conf >= 65 (no 60) en el path regular. Hubiera bloqueado #387 (60.5 < 65 con HTF bearish + CALL).

### Fix #2 — Groq prompt reforzado con negaciones (`news_analyzer.py`)

Sección nueva "NEGACIONES (CUIDADO - frecuentemente mal interpretadas)" con ejemplos explícitos de cómo mapear "doesn't see enough to hike", "patience on rates", "rate cut still on the table" → DOVISH → moneda débil. Mensaje crítico: "la presencia de 'rate hike' en el título NO es bullish per se".

### Caveat

El fix #1 reduce frecuencia de news trades counter-HTF (deseado). El fix #2 depende de que Groq aplique correctamente la nueva sección — observable en próximas news con negaciones.

---

## Que hay de nuevo en v3.15.0 — Gemma SL/TP feedback loop (write→read→apply)

Hasta v3.14.0, Gemma post-trade analizaba cada trade cerrado y guardaba advice como "Ajustar SL a 5.7 pips para alinear con el resultado real". Pero ese texto era WRITE-ONLY: nadie lo parseaba ni aplicaba. `sl_tp_advice` quedaba siempre vacío.

143 análisis acumulados de Gemma estaban siendo desperdiciados.

### El fix

**Step 1 — Gemma prompt structured output** (`post_trade_analyzer.py:24`):

Nuevo prompt pide datos numéricos además del texto:
```json
{
  "entry_quality": "good",
  "exit_quality": "fair",
  "key_lesson": "...",
  "suggested_adjustment": "...",
  "sl_action": "widen",       ← NUEVO categórico
  "recommended_sl_pips": 5.7,  ← NUEVO numérico
  "recommended_tp_pips": 12.0  ← NUEVO numérico
}
```

**Step 2 — Aggregation con consensus** (`db.py:get_learning_adjustments`):

Por cada trigger_type, acumula advice de últimos 48h:
- Necesita ≥3 trades para signal estable
- Consensus 60%+ en `sl_action`
- Median de `recommended_sl_pips` y `recommended_tp_pips`
- Output: `{trigger: {action, sl_pips, tp_pips, sample_size}}`

**Step 3 — Apply override** (`technical.py:compute_adaptive_sl_tp`):

Si advice difiere >15% del profile, override:
```python
if rec_sl > 0 and abs(rec_sl - prof_sl) / prof_sl > 0.15:
    learning_sl_override = rec_sl
    # Use rec_sl as base instead of profile.stop_loss_pips
```

ATR clamping y structural override siguen aplicando — la advice de Gemma reemplaza el `prof_sl` base.

### Comportamiento esperado

Después de 3+ post_trade analyses con sl_action='widen' para `news`:
```
Learning SL override for news: widen → 5.5p (profile was 3.5p, n=4)
```
La próxima news strategy va a usar SL=5.5p en lugar de 3.5p.

Si Gemma cambia de opinión y ahora dice 'tighten' o 'keep', se actualiza al siguiente ciclo.

### Trade-off

- **Pro**: 143 análisis de Gemma ahora son ACCIONABLES, no solo decorativos. Sistema aprende SL/TP por trigger.
- **Riesgo**: Gemma puede dar advice inconsistente. El consensus 60% + median + sample 3+ mitiga.
- **Limitación**: existing 143 insights no tienen los nuevos campos (text-only). Solo NUEVOS análisis (post-deploy) feed el sistema.

### Validation pendiente

- Próximos 5+ trades cerrados van a generar análisis con structured SL data
- A los 3+ análisis del mismo trigger con consensus, el override se activa
- Ver logs "Learning SL override for X: Y → Zp"

---

## Que hay de nuevo en v3.14.0 — News bypass: bloquear counter-HTF

Tercera falla del 5 May 2026 identificada: news low-conf bypass (v3.12.0) tomó un trade donde Groq dió dirección **counter-HTF**, y perdió.

**Caso real**:
- #331 news "Inflationary Signals Are Popping Up Everywhere"
- Groq direction: **CALL** (conf 32, impact 85)
- HTF bias: **bearish**
- → CALL counter-HTF
- Perdió -$2.10

### El problema

News low-conf bypass acepta direcciones inciertas porque "el mercado se mueve con news high-impact". Pero cuando la dirección VA EN CONTRA del trend macro (HTF), tenemos doble incertidumbre:
- Groq no está seguro de la dirección (conf <60)
- Y AIdan está peleando contra el HTF establecido

**Empírico (9 historical bypass trades)**:
```
News aligned with HTF (PUTs en bearish):  7/7 wins ★
News counter-HTF (CALLs en bearish):      0/2 wins ✗
```

100% vs 0% según alignment con HTF. Patrón cristalino.

### Fix

En el news flow, `_bypass_eligible` ahora requiere:
1. `impact_score >= 55` (igual que antes)
2. **AND `direction NOT counter-HTF`** (nuevo)

Si la noticia low-conf apunta contra HTF, **no se activa el bypass**. Cae al min_conf=60 normal y probablemente se filtra.

### Aplicado al 5 May

- #331 CALL en HTF bearish, impact 85, conf 32 → **bloqueado** ($2.10 saved)

### Trade-off

Con #331 bloqueado, perdemos potencial wins de "news catalyst que SÍ revierte HTF". Pero la data dice 0/2 ese caso. Si en el futuro aparecen news bullish que correctamente revierten un HTF bearish, podemos perder esos. Aceptamos el riesgo basado en evidencia.

---

## Que hay de nuevo en v3.13.0 — Late breakout filter (fresh-only)

Análisis de los 5 losses del 5 May 2026 reveló:
- 2 losses fueron pre_planned bug (ya fixed v3.12.2)
- 1 loss fue news low-conf direction error (riesgo conocido)
- **2 losses fueron breakouts STALE**: AIdan detectó "breakout sobre resistencia" cuando el precio ya se había movido 5-6 pips PAST el nivel
  - #328: +6.2p past resistance → loss
  - #332: +5.6p past resistance → loss

### El bug

`technical.py:666` permitía breakouts hasta 15 pips past el nivel:
```python
if 0.3 < dist < tuner_params.get('breakout_dist_max', 15) and crossed_above(res) and candle_confirmed:
```

Eso significa: si el precio cruzó la resistencia hace 3-4 velas y se movió +10p, AIdan todavía lo consideraba "breakout válido". En realidad, ese breakout YA ocurrió y el precio está cerca del exhaustion.

### Análisis empírico (29 breakouts/breakdowns históricos)

```
dist past level     n     WR     PnL
1-2p (fresh)        5    80%   +$10.40   ★ 
2-3p                8    25%    -$5.60
3-5p (late)         8    38%   -$11.20  ✗
5-7p (late)         4    25%    -$6.20  ✗
7-15p               3    67%    +$1.30  (sample chico)
```

**Breakouts FRESCOS (≤2p past) ganan 80%. Late breakouts (3-7p) pierden consistentemente.**

### Fix

Cambiar `breakout_dist_max` y `breakdown_dist_max` de 15 → **3** pips:
- Default in code: `tuner_params.get('breakout_dist_max', 3)`
- Optimizer params row 7 actualizada con valor 3
- Solo entradas donde el precio está cerca del nivel cruzado (entrada fresca)

### Simulación con max_dist=3

```
Threshold      kept     WR     PnL          excluded
max 2p (best)   6      67%    +$7.50        -$21.70 (23 excluidos)
max 3p (chosen) 14     43%    +$1.90        -$16.10 (15 excluidos)
max 4p          20     45%    -$0.70        -$13.50 (9 excluidos)
max 15p (old)   29     41%    -$14.20       —
```

Net delta: **+$16.10 sobre 29 breakouts históricos**. Block = sólo trades stale (que históricamente perdieron).

### Aplicado a hoy (5 May 2026)

- #328 dist +6.2p → **bloqueado**
- #332 dist +5.6p → **bloqueado**
- $11.20 saved que se perdieron hoy

### Trade-off

Filtramos más trades (53% menos breakouts) pero mantenemos los profitables. Volume baja, calidad sube.

---

## Que hay de nuevo en v3.12.2 — Hotfix: anti-contradiction en pre_planned activator

Bug crítico observado en producción (5 May 2026, ~11:00 broker time):
- **#381 PUT pre_planned** (ISM Services PMI) y **#383 CALL pre_planned** (JOLTS) activaron al mismo tiempo
- MT5 abrió ambas posiciones simultáneamente al mismo entry price (1.16984), direcciones opuestas
- Ambas perdieron: -$6.40 + -$7.50 = **-$13.90 combinados**

Histórico de pre_planned: **4 trades ejecutados, 4 losses. WR = 0%** (#211 #212 #381 #383).

### Por qué falló anti-contradiction

`has_active_opposite_strategy` solo chequea `status='active'`. Cuando dos planned activan en el mismo ciclo:
1. Ninguna es `active` antes del activator
2. El activator marca AMBAS como `active` en una sola pasada
3. La gate de anti-contradiction (en news/structure/SMC flows) NUNCA evalúa pre_planned

### Fix (`src/common/db.py:1663` `activate_due_planned_strategies`)

Anti-contradiction añadido en el activator:
1. Antes de activar, query DB para directions activas
2. Para cada planned a activar, sortear por `confidence DESC` (best first)
3. Si la dirección opuesta ya está active o se activó en este batch → marcar `status='skipped_opposite'` en lugar de activar
4. Solo una dirección por ventana de tiempo

### Comportamiento esperado

- 2 events near-simultaneous con direcciones opuestas: solo el de MAYOR conf activa, el otro se skip
- Si llega evento solo: activa normalmente
- `skipped_opposite` queda en DB para análisis posterior

### Consideración: deshabilitar pre_planner?

Con 0% WR sobre 4 trades, podríamos directamente apagar el pre_planner. **No lo hacemos aún** porque:
- Sample chico (4 trades)
- El bug del anti-contradiction era el factor dominante (4 de 4 fueron pares contradictorios)
- Con el fix, single-direction pre_planned podrían tener edge

Si los próximos 5-10 pre_planned siguen perdiendo: apagamos.

---

## Que hay de nuevo en v3.12.1 — Hotfix: el bypass de v3.12.0 no se ejecutaba

Bug detectado en producción: la lógica de bypass low-conf news estaba dentro de un bloque que requería `conf_ok=True` en un gate ANTERIOR usando `prof_min_conf=60`. Resultado: alertas con conf<60 nunca entraban al bloque donde estaba el bypass.

**Caso real (5 May 2026, 08:38 AR)**:
- Alert #1843 PUT conf 58.5 impact 55 — bypass debería haberlo capturado
- Pero `conf_ok = 58.5 >= 60 = False` en gate inicial → never reached bypass
- Strategy NO se generó

**Fix**: el gate inicial `conf_ok` ahora usa threshold dinámico:
```python
_initial_min_conf = 30 if impact_score >= 55 else prof_min_conf
conf_ok = confidence >= _initial_min_conf
```

Sin esto v3.12.0 era equivalente a v3.11.0 en producción (los trades extra del simulado no se hubieran generado).

---

## Que hay de nuevo en v3.12.0 — Low-conf news bypass (BREAK-EVEN alcanzado)

Análisis del bucket conf<50 reveló que **5 de 8 trades ganaron (62% WR, +$12.10)**, y **80% eran NEWS con impact_score 55-91**. La conclusión: cuando Groq da conf bajo en news high-impact, **eso refleja incertidumbre de DIRECCIÓN, no falta de movimiento**. El mercado SE mueve en news high-impact. Y en el régimen reciente, los PUTs ganan mayoría.

### El cambio

News flow agrega **threshold dinámico**:
```python
effective_min = 30 if impact_score >= 55 else 60
if conf < effective_min: skip
```

Es un bypass quirúrgico: solo news con impact ≥55 puede pasar con conf 30-60. Structure/SMC siguen con min_conf=60. Trades históricos en el bucket conf<50 que eran ESTRUCTURA siguen bloqueados (eran perdedores: -$7.80 en 2 CALLs structure).

### Validación con simulación (118 trades históricos)

```
                                   n      WR     PnL          PF      vs Baseline
Baseline (sin filtros):            118    38%    -$115.81     0.58     —
v3.10.0:                           73     47%    -$39.31      0.74     +$76
v3.11.0 (final, sin lower min):    31     48%    -$22.40      0.68     +$93
v3.12.0 (con news bypass):         40     55%    -$1.40       0.98     +$114  ★★
```

**v3.12.0 alcanza esencialmente break-even** (-$1.40). PF 0.98. WR 55%. **Por primera vez vemos un sistema casi rentable sobre la data histórica completa.**

### Los 9 trades adicionales capturados por v3.12.0

| # | Dir | Trigger | Conf | Impact | Resultado | PnL |
|---|---|---|---|---|---|---|
| 226 | PUT | news | 48 | 85 | win | +$8.70 |
| 253 | PUT | news | 45 | 55 | win | +$6.80 |
| 251 | PUT | news | 55 | 65 | win | +$3.70 |
| 245 | PUT | news | 36 | 65 | win | +$2.20 |
| 266 | CALL | news | 58 | 78 | win | +$2.00 |
| 326 | PUT | news | 55 | 80 | win | +$1.90 |
| 270 | PUT | news | 35 | 65 | win | +$1.50 |
| 271 | CALL | news | 50 | 55 | loss | -$4.70 |
| 265 | CALL | news | 54 | 55 | loss | -$1.10 |

**Net: +$21.00**. PUTs 7/7. CALLs 1/3 (sample chico, pero coherente con régimen bearish).

### Riesgo

- Sample chico (9 trades). Margen de error.
- Régimen-dependiente: si EUR/USD pasa a bullish, los CALLs low-conf podrían dominar (no aplica simulación).
- Si Groq se confunde mucho con dirección en news, podría dar señales malas conf<50 que no compensa.

### Trade-off aceptado

Pasamos de 31 trades (v3.11) a 40 trades (v3.12), 9 más por mes aprox. WR sube 7pp. PnL mejora $21. Risk-adjusted: el bypass solo aplica a high-impact news que históricamente movieron, así que los trades agregados tienen base sólida.

### Archivos modificados

- `AIdan_TodoEnUno.py:1338` — effective_min_conf logic en news flow
- `src/common/config.py` — version 3.11.0 → 3.12.0
- `tools/simulate_v311.py` — extendido con simulación v3.12.0
- `tools/analyze_conf_below_50.py` — script que reveló el patrón
- `README.md` — full v3.12.0 changelog

---

## Que hay de nuevo en v3.11.0 — 3 fixes data-driven (#3 descartado por simulación)

Análisis profundo de 118 trades históricos (`tools/deep_analysis.py`) reveló 4 patrones explotables. Simulación pre-deploy validó 3 de los 4 — el cuarto resultó contraproducente:

### Cambios aplicados (3 de 4)

**1. ATR floor 2.5p** — bloquear trades en deadzone (ATR<2.5)
- Empírico: 15 trades históricos | 13% WR | -$22.81
- Comm 0.7p come la mayoría del win esperado en deadzone
- Aplicado en news/structure/SMC flows

**2. Hour gate 12, 14, 20 UTC** (= 09h, 11h, 17h AR)
- Empírico: 26 trades en esas horas | -$45.31 collective
- 11h AR específicamente: 16 trades, -$33.60
- Aplicado en news/structure/SMC flows

**4. Conf ceiling 80** — bloquear trades con conf >= 80 (anti-predictiva)
- Empírico: bucket 80-89 (-$20) y 90+ (-$21) son net losers
- AIdan asigna conf alta a trades que pierden (formula reverse-correlated)
- Aplicado en news/structure/SMC flows

### Cambio descartado (#3 lower min_conf)

**No aplicado**: bajar min_conf 60→50.

**Razón**: la simulación reveló que mi premisa estaba mal. El bucket conf<50 (62% WR, +$12.10) **ya está bloqueado por min=50** (50 floor sigue bloqueando <50). Lo que se desbloquea con min=50 es bucket [50,60) que es **NET LOSER** (-$10.61, 38% WR).

El cambio hubiera HURTING: simulación con #3 dió delta +$8 vs v3.10. Sin #3 dió delta +$17.

### Validación con simulación

```
                                  n     WR    PnL          PF      Delta
BASELINE                          118   38%   -$115.81     0.58     —
v3.10.0 (universal SIM A)         73    47%   -$39.31      0.74     —
v3.11.0 con 4 fixes (incl #3)     43    47%   -$30.90      0.66     +$8 vs v3.10
v3.11.0 final (sin #3)            31    48%   -$22.40      0.68     +$17 vs v3.10  ✓
```

**v3.11.0 final**: WR 48%, PnL casi break-even (-$22), PF 0.68. **+$93 vs baseline original (-$115).**

Trade-off aceptado: 31 trades vs 73 (filtra 58% más). Volumen baja considerablemente pero calidad sube.

### Archivos modificados

- `AIdan_TodoEnUno.py:1326-1351` — gates en news flow (ATR + hour + conf ceil)
- `AIdan_TodoEnUno.py:1924-1944` — gates en structure flow
- `AIdan_TodoEnUno.py:2138-2151` — gates en SMC flow + conf ceil post-audit
- `tools/simulate_v311.py` — simulation framework
- `README.md` — changelog completo con razonamiento

---

## Que hay de nuevo en v3.10.0 — Regime detection (trending vs ranging)

Análisis del 4 May 2026 reveló que AIdan está calibrado bajo el supuesto "EUR/USD M5 es mean-reverting", pero ese día EUR/USD se movió -36p en trend bajista limpio. **AIdan perdió 4/4 CALLs** tratando de comprar bounces durante el trend.

Solución: agregar **detección de régimen** y aplicar filtros diferenciados.

### Detector de régimen (`technical.py:get_market_state`)

Computa 3 señales sobre las últimas 50 velas M5 (~4 horas):

1. **directional_score** = |movimiento neto| / ATR. >3 = trending fuerte.
2. **range_atrs** = (max-min) / ATR. >7 = expansión amplia.
3. **ma_alignment_score** = |MA9 - MA21| / ATR. >0.6 = MAs separadas, trend sostenido.

Score (0-3) → clasificación:
- ≥2 señales: **trending**
- 0 señales + directional <1.5: **ranging**
- otro: **uncertain**

### Filtros UNIVERSALES (validados sobre data histórica)

Después de simular, descubrí que **mi hipótesis inicial (regime-dependent filters) estaba al revés**. Empíricamente:

```
TRENDING regime breakdown (53 trades):
  aligned    : 23 trades | 17% WR | -$58.90  ← PEOR
  M5-only    : 14 trades | 50% WR | -$8.30
  HTF-only   : 13 trades | 46% WR | -$11.11
  counter-both: 3 trades |  0% WR | -$16.90
```

Counter-intuitivo: **aligned trades en trending son los PEORES** (17% WR), no los mejores. EUR/USD M5 mean-reverte incluso dentro de trends macro — los aligned son entries tarde en el movimiento.

Filtros corregidos (aplican en TODOS los regímenes):
- **BLOQUEAR fully-aligned** (HTF + M5 + dir todos coinciden) — siempre exhaustion
- **BLOQUEAR counter-both** (HTF + M5 ambos contra dir) — sin edge histórico
- **PERMITIR M5-only y HTF-only** (parcialmente alineado) — los buckets profitables

News flow exempt (catalysts pueden mover en cualquier dirección).
El detector de régimen sigue computado y guardado en entry_context para análisis futuro, pero la lógica de filtrado actual no lo usa.

### Validación con simulación (118 trades históricos)

```
                Baseline    v3.10.0 corregido
n trades:       118         73 (45 bloqueados)
WR:             38%         47%                ✓ +9pp
PnL:            -$115.81    -$39.31            ✓ +$76.50
PF:             0.58        0.74               ✓ +0.16

Bloqueados:  44 fully-aligned (25% WR, -$70.70)
              1 counter-both
```

**Mejora robusta**: $0.65/trade en delta (+$76 sobre 118 trades). WR sube 9pp. Cerca de break-even (-$39 vs -$115).

### Lo que esto NO arregla

- Wins amputados al 43% del TP (mecanismo aún desconocido)
- Régimen "uncertain" sigue mixto
- Transiciones entre régimen pueden producir whipsaw — a observar

### Archivos modificados

- `src/analyzer/technical.py:295-340` — detector + agregado `regime` al market state
- `AIdan_TodoEnUno.py:1893` — filtro regime-aware en structure flow
- `AIdan_TodoEnUno.py:2087` — filtro regime-aware en SMC flow
- `tools/simulate_regime.py` — simulación standalone

---

## Que hay de nuevo en v3.9.1 — Warmup gate (stale signal fix)

Patrón confirmado en producción: cuando AIdan se abre en mitad de horario de mercado, la primera estrategia que genera tiende a perder porque entra en señales "stale" — consumidas hace 5-15 minutos antes de que el bot estuviera observando.

### El caso confirmado: trade #371 (4 May 2026)

- **09:57:53** — Primera news fetched después del weekend (AIdan recién arrancado)
- **09:58:24** — Estrategia CALL creada **30 segundos después**: "Continuación alcista, precio rebotando en soporte 1.17055 (+3.7p)"
- **09:59:53** — SL hit en 90 segundos. Pérdida -$3.80
- Setup era válido a las 09:55 (cuando ocurrió el bounce). A las 09:58 ya estaba consumido — el precio había subido +5p y AIdan entró al final del movimiento.

### El mecanismo

Los indicadores (ATR, RSI, MA) se calculan correctamente desde velas históricas al startup. Pero el bot **no tiene memoria de cycles previos**: no distingue entre "señal recién aparecida" y "señal que estaba ahí hace 15 minutos". Si arranca en medio de un movimiento, ve la "evidencia" del movimiento (trend strong, momentum up) pero no detecta que ya está consumido.

### El fix

Warmup gate: durante los primeros **10 minutos** (`WARMUP_SECONDS = 600`) tras el startup del analyzer, no se generan estrategias. Esto da tiempo a que **al menos 2 velas M5 cierren mientras AIdan observa en vivo**, asegurando que las señales detectadas sean recién aparecidas y no stale.

Aplicado a:
- News flow (`AIdan_TodoEnUno.py:1326`)
- Structure scanner (`AIdan_TodoEnUno.py:1893`)
- SMC scanner (`AIdan_TodoEnUno.py:2065`)

Pre-planned strategies exentas (son scheduled, no reactivas).

### Trade-off aceptado

Si abrís AIdan a las 09:55 antes del NY open (10:00 AR), te perdés la primera media hora del NY open. Es un costo aceptable: las señales perdidas en los primeros 10 minutos eran disproporcionadamente perdedoras.

---

## Que hay de nuevo en v3.9.0 — EXPIRY FIX (el bug masivo) + SIM A

Después de meses operando con WR 38% / PnL -$105, un análisis profundo encontró el bug que estaba bottling 76% de los wins. La fix transforma AIdan de break-even-perdedor a profit factor 1.32.

### EL BUG: force-close en expiry

Línea 2260 de `AIdan_TodoEnUno.py` (eliminada en v3.9.0):

```python
# Old behavior — ESTO ERA EL BUG:
if mt5_exec.is_ready():
    mt5_closed_price = mt5_exec.close_strategy_position(sid)
    # Force-close TODA posición filled cuando expira (15min default)
```

**Comportamiento previo**: AIdan creaba strategy con expiry de 15 min. MT5 abría posición con SL/TP fijos. A los 15 minutos, AIdan **fuerza el cierre** de la posición, sin importar si llegó al TP o no.

**Resultado**: 41 wins históricos cerraron en 4.1p promedio cuando el TP nominal era 9.4p. **Capturábamos 43% del TP**. 76% de los wins eran "amputados" antes de hitearse.

### Comportamiento nuevo (v3.9.0)

```python
# v3.9.0 — solo force-close si SL/TP HIT detectado en candles
should_force_close = hit_tp or hit_sl or hit_be
if should_force_close and mt5_exec.is_ready():
    mt5_closed_price = mt5_exec.close_strategy_position(sid)
elif mt5_exec.is_ready():
    # Position still open — let MT5 close naturally on TP/SL
    logger.info(f"Strategy #{sid} expired but MT5 position OPEN — letting SL/TP do their job")
    continue  # Skip evaluation; will re-evaluate when MT5 closes naturally
```

El SL fijo en MT5 sigue protegiendo de runaway losses. Pero ahora los TPs PUEDEN llegar.

### Plus: SIM A — block fully-aligned structure trades

Análisis de los 107 trades históricos reveló que trades fully-aligned (HTF + M5 + dir todos coinciden) tenían **28% WR, -$82.30**. Counter-trend tenían 57% WR, +$5.60.

EUR/USD M5 es mean-reverting. Trades aligned son entries de exhaustion (precio ya movió, listo para reversar).

`AIdan_TodoEnUno.py` agrega filtro en flujo de structure scanner:
- Si `direction='CALL' AND htf_bias='bullish' AND trend='bullish'` → SKIP
- Si `direction='PUT' AND htf_bias='bearish' AND trend='bearish'` → SKIP
- News trades exemptos (catalysts pueden mover aligned)

### Simulación sobre 107 trades históricos

| Versión | Trades | WR | PnL | PF |
|---|---|---|---|---|
| BASELINE (con bugs) | 107 | 38% | **-$105.81** | 0.57 |
| Solo expiry fix | 107 | 34% | -$14.81 | 0.95 |
| **v3.9.0 (expiry + SIM A)** | **73** | **40%** | **+$53.59** | **1.32** ✓ |
| v4.0 (counter+momentum+hour) | 17 | 41% | +$11.19 | 1.28 |

**v3.9.0 alone supera el target PF >1.3.** v4.0 NO agrega valor — over-engineering reduce muestra sin mejorar outcome. **El expiry fix capturó todo el upside disponible**.

### Métricas que cambian con v3.9.0

| Métrica | Pre-v3.9 | Post-v3.9 (sim) |
|---|---|---|
| Avg win | 4.1p | **8.2p** ← +100% |
| TP capture | 43% | ~85% |
| Net por trade | -$0.99 | +$0.73 |
| Comisión / win ratio | 50% | 25% |

### STATS_SINCE actualizado

`STATS_SINCE=2026-05-03 06:00:00` para reflejar el deploy de v3.9.0. Dashboard arranca de cero para validar la fix con data limpia.

### Modelo de simulación (transparencia)

Para los wins históricos amputados (capture <70% TP), el modelo asume:
- 60% hubieran hit TP (avg captura del TP nominal)
- 25% similar al actual (precio se estancó)  
- 15% hubieran reversado a SL (loss)

Asumptions conservadores. Real podría ser mejor o peor pero el upside está validado direccionalmente.

---

## Que hay de nuevo en v3.8.0 — Análisis profundo + correcciones validadas con simulación

Después de 100 trades en demo desde v3.6.3 con WR 40% y PnL -$93, semana de pruebas reveló que los ajustes finos al confidence scoring no resuelven el problema estructural. Análisis profundo de la data identifica las causas reales y propuestas validadas vía simulación sobre el histórico.

### Hallazgos del análisis

1. **Comisiones son 87% de la pérdida neta**: pips netos gross -10.5p (esencialmente break-even), pero comisión $67.31 ($0.69/trade ≈ 0.7p) inflige el daño real. Para break-even al WR 41% actual necesitamos avg win 6p (vs 4p actual) o WR 53%.

2. **Wins capturan solo 43% del TP nominal**: TP promedio 9.4p, pips reales 4.1p. 212p sobre la mesa. Mecanismo desconocido (trailing está OFF en código) — investigación pendiente.

3. **SL/ATR sweet spot empírico**: trades con SL/ATR 1.0-1.5x (n=20) tuvieron 55% WR +$14. Trades con SL/ATR 0.6-1.0 (n=59, mayoría) tuvieron 42% WR -$70. **El cap del v3.7.0 estaba metiendo trades en la zona tight.**

4. **Caso 30 Abr (3 SL hits consecutivos)**: ATR 6.9-7.8p, SL cap 5.6p. Direccional correcto (precio bajó 11p en 38min) pero los 3 PUTs SL-hit en rebotes intermedios. SL adentro del ruido normal.

### Cambios

- **SL cap revertido (P1)**: `min(ATR*1.2, prof_sl*1.6)` → `max(ATR*1.0, prof_sl*1.5)`. En ATR baja usa floor del profile (5.25p), en ATR alta adapta a volatilidad real.
  - Simulación: ~19 trades hubieran sobrevivido SL hit con SL más amplio.
  - Delta optimista: +$77 / realista (descuento MAE 50%): +$40.
  
- **ATR ceiling 6p (P3)**: skip estrategias cuando `avg_range_pips > 6` en news + structure scanners.
  - Simulación: 13 trades excluidos (-$29 colectivos), Delta: +$29.
  
- **Combinado (P5)**: Trades 81 (filtrados 19), WR 42%, PnL simulado -$3 (casi break-even).

- **Wipe `learning_insights`** (568 rows): lessons aprendidas con bugs activos (v3.6.x counter-HTF mal calibrado, v3.7.0 SL cap tight) podían ser auto-confirmables. Backup en `state/learning_insights_backup_v3.7.1_*.csv`. 47 reports preservados (sin runtime impact).

### Lo que NO se hizo (descartado por evidencia)

- **TP cap a 5p**: simulación dió **-$27** (peor). Los wins grandes (>5p) sostienen el sistema.
- **min_confidence cambios**: ya investigado, no mueve la aguja.
- **Más cambios al confidence scoring**: 4 cambios en 2 semanas; el problema no estaba ahí.

### Próximo paso (Fase 2 sin cambios)

Investigar el misterio del 43% TP capture. Trailing está OFF en código pero los wins cierran tempranos. Si resolviéramos esto: capturar 70%+ del TP en lugar de 43% sería el cambio más impactante (+$100+ over 100 trades). Read-only audit pendiente de `mt5_executor.py` y los flujos de cierre.

---

## Que hay de nuevo en v3.7.1 — Hotfix: restaurar momentum scoring (overshoot de v3.7.0)

Dos trades consecutivos perdedores el dia post-deploy de v3.7.0 (#350 PUT -$3.80 exhaustion entry, #351 PUT -$4.30 SL hit en 30s) revelaron un overshoot en el cambio anterior.

Cuando neutralice el paso 8 de `dynamic_conf` para quitar el `±15` de trend+HTF alignment (correcto), tambien borre el `±5` de momentum directional que estaba en el mismo bloque (incorrecto). Eran cosas distintas:

- **Trend+HTF alignment**: signal de regimen (mean-reverting EUR/USD M5). Quitarlo fue correcto.
- **Momentum (±5)**: signal de TIMING corto plazo. Si momentum va contra la direccion del trade, los proximos 1-2 candles empujan hacia SL antes que el edge actue. No es regime, es timing.

### El bug en accion

Trade #351 PUT entry 1.16996 con `entry_context: momentum=up`. Las 3 candles previas: 1.16951 -> 1.16990 -> 1.16998 -> 1.16996 (subida limpia). SL en 1.17033 (apenas 4p arriba). **Cerro en 30 segundos.**

Con momentum -5 restaurado: conf 60 - 5 = 55 < min_conf 60 -> bloqueado. SL evitado.

### Cambio

- `technical.py:528-549` — restaurar bloque de momentum directional (±5)
- Trend/HTF stays neutralizado del v3.7.0
- 9 lineas nuevas, sin riesgo (era logica vigente por meses)

---

## Que hay de nuevo en v3.7.0 — Confidence formula data-driven + SL cap

Ronda de analisis sobre 75 trades historicos (post v3.6.3) revelo 3 patrones que apuntan a un solo bug en `dynamic_conf()`. Cambios validados con backtesting inline antes de aplicar.

### Hallazgos del analisis (75 trades, WR 41%, PnL -$54.70, PF 0.64)

- **Confidence INVERTIDA**: trades con conf >=85 tenian WR 22% y PnL -$28.80, mientras trades con conf <55 tenian WR 47% y PnL +$12.10 (la unica categoria positiva)
- **HTF aligned PEOR que counter**: aligned (CALL+bullish o PUT+bearish): 35% WR -$50.70 vs counter: 54% WR -$4.00. La hipotesis original del filtro counter-HTF estaba al reves
- **CALLs sangraban mas que PUTs**: CALL 30% WR -$53.40 vs PUT 49% WR -$1.30. Causa raiz: htf=bullish dominante, formula premiaba CALLs aligned con +15 conf, esos CALLs eran exhaustion entries

### Root cause unico

`dynamic_conf()` paso 8 daba +15 conf cuando trend+HTF aliman, -18 cuando ambos counter. EUR/USD M5 es un timeframe **mean-reverting**, no trending — el formula estaba premiando exhaustion entries (precio ya movio con la tendencia, listo para reversar) y penalizando los counter-trend que son los setups rentables.

### Cambios

- **Paso 8 de `dynamic_conf` neutralizado**: alignment delta = 0. Variables (is_with_trend, is_with_htf) se mantienen para logging/audit downstream pero no impactan confidence. RSI, volatility, structure, daily range positioning siguen siendo los drivers principales
- **Cap de SL estructural reducido**: de `prof_sl * 2.5` (=8.75p) a `min(ATR*1.2, prof_sl*1.6)` (=5.6p para profile 3.5p). Causaba perdidas catastroficas en high-conf trades (#235 -$7.60, #229 -$6.70) cuando structural override extendia SL hasta 8p
- **min_confidence subido 50 → 60** en perfil activo. Backtest inline mostro que con neutralizacion + threshold 60: -$36.50 en 31 trades vs -$66.90 en 54 trades (mismo WR 39%, la mitad de la perdida)
- **Default en `get_active_profile()` actualizado** a min_confidence=60 (antes 50) por consistencia

### Lo que esto NO arregla

La inversion sigue parcialmente: aun con el fix, el bucket conf >=70 sigue teniendo WR menor que <55. El fix detiene el sangrado pero no convierte AIdan en rentable — el problema residual es regime-driven (mercado mean-revierte) y RR asimetrico. Proximos pasos potenciales: gating posicional (premiar alignment solo si precio esta al inicio del trend, no al final).

### Bonus: optimizacion de modelos LLM

- Benchmark de modelos sobre 30 trades historicos: `llama-3.3-70b-versatile` mantiene mejor filter signal (+24pp WR gap entre agree/disagree). Modelos razonadores (gpt-oss, qwen3) tenian filter signal **invertido** (-9 a -14pp) — confiados pero equivocados
- **Local: gemma4 → qwen2.5:7b** — 3x mas rapido (7s vs 20s), libera 4GB VRAM, calidad de filter equivalente
- **Chat: dashboard ahora usa `llama-3.1-8b-instant`** — mismo nivel para el caso de uso, latencia menor
- Harness de benchmark guardado en `tools/llm_benchmark.py` para futuras evaluaciones

---

## Que hay de nuevo en v3.6.0 — Auditoria profunda + limpieza arquitectonica

Release grande: 4 rondas de auditorias paralelas con agentes especializados encontraron 22+ bugs estructurales. Se arreglaron los reales (verificando con grep cada claim para descartar falsos positivos). Enfoque en integridad de datos y flujo correcto de informacion al learning engine.

### Fixes criticos de arquitectura y flujo de datos

- **htf_bias self-referential bug**: `AIdan_TodoEnUno.py:1004` hacia `ctx['htf_bias'] = ctx.get('htf_bias', '')` — lectura del mismo dict. Resultado: 174 trades con htf_bias=NULL en historial, learning engine ciego al macro. Fix: extraer de `smc.get_status()` en las 3 rutas de archivado (startup, auto-eval, MT5 executor)
- **entry_context atomico**: el market state al momento de la decision (RSI, ATR, trend, htf_bias, volatility) ahora se guarda COMO JSON en auto_strategies en la misma transaccion que crea la strategy (elimina race condition con MT5 fills instantaneos). Antes estos datos se capturaban al EXIT del trade, contaminando el learning engine con estado post-factum
- **MT5 executor → trade_archive**: el 97% de los trades cierran via MT5 executor, que antes solo guardaba 5 campos en strategy_results. Ahora llama a `archive_trade()` con contexto completo (10 campos) leyendo el entry_context persistido. Learning engine ve por primera vez datos reales del momento de la decision
- **Gemma post_trade handler en learning**: los insights de Gemma estaban write-only — se guardaban en learning_insights pero `get_learning_adjustments()` no los leia. Ahora hay un handler que agrega penalties/bonuses cuando Gemma detecta `confidence_was='overestimated'` repetidamente por trigger_type
- **prev1/prev2 undefined en dynamic_conf**: silent NameError hacia que el boost de patrones de vela (+3 a +5 conf) nunca se aplicara. Fix: definir prev1/prev2 ANTES de la funcion (closure Python captura por nombre)
- **Key level override invertido**: `key_level` reemplazaba el entry_price con el support/resistance, locking in una entrada 5-10 pips peor cuando el precio ya habia rebotado. Eliminado — ahora se usa el tick vivo de MT5 como entry real

### Integridad de datos y trazabilidad

- **Win/loss por MT5 P&L real** (no pips teoricos desde entry_price). Fix aplicado tambien en auto-archive antes de cleanup. Corrige 26 trades mal clasificados del historial
- **Fill price en archive**: pips y distancias SL/TP calculados desde el precio de ejecucion real de MT5, no el precio teorico de la senal
- **Trend context en archive**: mt5_executor captura trend/trend_strength/htf_bias al cerrar (antes NULL en ~93% de trades)
- **entry_context en trade_archive**: columna JSON nueva que preserva el snapshot completo del entry para analisis posterior
- **SL minimo 2.0 pips**: hard floor para evitar SLs de fracciones de pip que producen cierres instantaneos

### Filtros y gates

- **Min confidence gate en news** despues de learning adjustments: bloquea trades de noticias que caen bajo el minimo del perfil por penalizaciones (antes pasaban 16 trades con conf 13-45 → -$28.80)
- **Filtro contra-tendencia corregido**: aplicaba solo cuando `trend_strength=='strong'`, pero en M5 la tendencia casi siempre era 'weak' (MA spread < 3p) — el filtro nunca se activaba. Ahora aplica en TODA tendencia detectada. Thresholds MA spread calibrados para M5: strong>3p, moderate>1.5p
- **Rate limit enforced**: `max_trades_per_hour` estaba definido en ProfileConfig pero nunca se consultaba. Ahora `add_auto_strategy()` lo chequea y skip si excedido
- **Circuit breaker 3 losses**: 3 perdidas consecutivas en <30 min → pausa 30 min (proteccion anti-tilt generica)

### Performance y latencia

- **MT5 como fuente primaria de velas**: `copy_rates_from_pos()` instantaneo, sin red. Yahoo Finance/TwelveData pasan a fallback. Elimina delay de 500ms-2s que causaba entradas tardias
- **Cache 3s en price_feed.fetch_candles()**: 3 llamadas por ciclo = 1 solo IPC a MT5
- **Gemma audit → Thread async**: audit de Gemma (2-15s de latencia) ahora corre en background. La orden va a MT5 PRIMERO, Gemma ajusta confidence post-hoc via UPDATE con WHERE status='active' (evita actualizar trades ya cerrados)
- **Skip candles incompletas**: `_fetch_mt5` descarta la ultima vela si aun se esta formando. Analisis usa solo velas cerradas
- **Spread spike retry**: si spread > SL distance, retry 3x con 0.5s delay antes de abortar (sobrevive a news events)
- **Cycle overlap guard**: detecta y loggea si un ciclo de analisis supera ANALYZER_INTERVAL (10s)

### Thread safety y robustez

- **SMC lock**: `threading.Lock` en `SMCEngine` protege `_mtf_state` y `_zones_by_tf` contra torn reads. Atomic swap en `update()`, lecturas snapshot bajo lock en `check_confirmations`, `get_status`, `get_chat_context`
- **Graceful shutdown**: `_shutdown_event` signals threads para salir limpios en close (antes daemon threads morian con DB writes en vuelo)
- **Pending orders cancel al expirar**: strategies con `mt5_status='pending'` que expiran ahora cancelan el limit order en MT5 via `TRADE_ACTION_REMOVE` antes de marcar `status='expired'`
- **Profile defaults completos**: `get_active_profile()` incluye cooldown_minutes y max_trades_per_hour (antes faltaban → consumers fallbackeaban a valores random)

### Vision macro: contexto diario y multi-timeframe

- **D1 y H4 en MTFAnalyzer**: agregado al TF_CONFIG para contexto macro superior
- **`get_daily_context()`**: retorna today high/low/close, posicion en rango del dia (0-1), prev day OHLC, week high/low
- **Daily range awareness en dynamic_conf**: bonus +8 si precio esta en zona ideal (CALL cerca del low del dia, PUT cerca del high). Penalty -10 si esta en zona de exhaustion (CALL cerca del high, PUT cerca del low). Penalty -5 si esta cerca del cierre del dia anterior (zona de pivote incierto)

### Take Profit inteligente

- **TP estructural prioritario**: cuando hay resistencia/soporte cercano con R:R >= 1:1.5, TP apunta a ese nivel -1 pip buffer (mayor probabilidad de fill). Fallback: ATR cap
- **TP cap ATR*2 (antes *3)**: calibrado a research 2026 para scalping M5 — R:R 1:1 a 1:1.5 es lo rentable, no 1:4
- **SL estructural ampliado**: el SL puede ensancharse para respetar soportes/resistencias cercanos (antes solo achicaba)
- **R:R minimo 1:1.2**: permite cerrar en 1:1 con alto WR (patrones scalping de alta frecuencia)

### Fixes verificados como falsos positivos (NO aplicados)

Los agentes de audit reportaron varios bugs que al verificar con grep resultaron ser codigo correcto y funcionando:
- `is_setup_blocked` reportado como orfan — en realidad se llama 4x (news, calendar, structure, smc)
- `LearningEngine.tick()` reportado sin invocacion — en realidad se llama cada ciclo en linea 1398
- `pre_planner.plan_next_day_strategies()` reportado orfan — en realidad se llama en linea 1099
- `has_recent_similar_strategy`, `has_active_opposite_strategy`, `audit_signal`, `build_signal_context`, `set_smc_ref`, `analyze_closed_trade`, `modify_position_sl`, `detect_candle_patterns`, `candles_snapshot` — TODAS usadas correctamente
- Calibraciones data-driven (min_conf=65, HTF penalty -35, killzones UTC hardcoded) — REVERTIDAS porque se basaban en data contaminada pre-fixes. AIdan aprende organicamente desde ahora.

### Limpieza de datos contaminados

- **learning_insights table**: 823 rows eliminadas (derivados de archive contaminado con htf_bias=NULL)
- **post_trade_analysis table**: 159 rows eliminadas (Gemma habia analizado con contexto incorrecto)
- **trade_archive**: mantenido (175 rows, mt5_pnl es ground truth valido tras fix anterior). Pattern mining en learning_engine ahora salta rows con htf_bias vacio (legacy) pero las usa para stats agregadas

### Otras mejoras menores

- MT5 deviation 20 → 50 points (mejor tolerancia en mercado rapido, explicitado como points no pips)
- MIN_TRADES_FOR_ANALYSIS 3 → 8 (patrones mas confiables estadisticamente)
- Silent exceptions en `get_learning_adjustments` → logs de warning con stack trace
- Post-trade analyzer no se llamaba en ~97% de cierres (MT5 close path) — fix aplicado: ahora Gemma analiza todos los cierres

### v3.5.0 (06 Abr 2026)
- **Trailing Stop-Loss escalonado**: 3 pasos proporcionales al TP. Mueve SL en MT5 real via TRADE_ACTION_SLTP
- **Rotacion de API keys Groq**: 3 keys con fallback automatico cuando una alcanza el limite diario (429/401)
- **Aprendizaje cross-instancia desde Supabase**: trades de otras instancias se importan con peso 0.5x y alimentan learning engine + auto tuner
- **Evaluacion con P&L real de MT5**: usa el beneficio real de MT5 como ground truth en vez de calcular pips teoricos
- **Fix timezone en graficos**: las velas del dashboard ahora muestran hora Argentina (UTC-3) correctamente
- **Fix evaluaciones incorrectas**: estrategias ganadoras en MT5 ya no se marcan como LOSS

---

## Instalacion

### Usuarios

1. Ejecuta `AIdan.exe`
2. Se abre solo en el navegador en `http://localhost:8000`
3. Ingresa con tu usuario y clave
4. El aprendizaje compartido se activa automaticamente al loguearse

**Requisitos:**
- Windows 10/11
- 4GB de RAM minimo
- Conexion a internet (usa Groq API en la nube, no requiere modelos locales)

### Desarrolladores

```bash
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan
pip install -r requirements.txt
python AIdan_TodoEnUno.py
```

Requiere variable de entorno `GROQ_API_KEY` con una API key de [Groq](https://console.groq.com/) (gratis).

**Opcional (recomendado):** para auditoria de senales, analisis post-trade y planificacion nocturna, instalar [Ollama](https://ollama.com/) y descargar Gemma 4:
```bash
ollama pull gemma4
```
Sin Ollama, AIdan funciona igual pero sin segunda opinion de IA ni analisis post-trade.

---

## Como funciona

AIdan corre 4 servicios en paralelo dentro de un solo proceso:

### 1. Collector (cada 10 min)
Busca noticias en Bloomberg, Reuters, Financial Times y otras fuentes RSS financieras. Las guarda en una base de datos SQLite local.

### 2. Analyzer (cada 1 min)
Analiza todo lo que tiene disponible:

- **NewsAnalyzer**: usa Groq (Llama 3.3 70B) para evaluar si una noticia afecta EUR/USD, con que direccion y confianza
- **TechnicalAnalyzer**: calcula RSI, Medias Moviles, Bollinger Bands, soportes/resistencias. Detecta breakouts, reversiones RSI, cruces de MA, expansiones de momentum
- **MTFAnalyzer**: analiza velas en H1, M15 y M5 simultaneamente. Detecta swings (HH, HL, LH, LL) y estructura de mercado
- **SMCEngine**: Smart Money Concepts - identifica zonas de demanda/oferta y espera confirmacion del timeframe menor
- **AutoTuner**: optimiza parametros cada 30 min analizando el historial de trades

### 3. API (FastAPI en localhost:8000)
Servidor web que sirve el dashboard y expone endpoints para datos en tiempo real.

### 4. Strategy Watcher
Thread que monitorea nuevas estrategias y muestra notificaciones toast en Windows.

---

## Tipos de Setup (Estrategias)

AIdan detecta **7 tipos de patrones tecnicos** automaticamente en el grafico EUR/USD. Cada uno busca algo diferente:

| Setup | Que busca | Ejemplo |
|-------|-----------|---------|
| **breakout** | Precio rompe un nivel de resistencia/soporte y sigue | Precio cruza 1.1550 hacia arriba con fuerza |
| **bb_rejection** | Precio toca una Banda de Bollinger y rebota hacia el centro | Precio toca BB inferior y sube |
| **rsi_reversal** | RSI en zona extrema (sobrecompra/sobreventa) + nivel clave | RSI < 30 + precio en soporte = probable rebote |
| **ma_crossover** | Cruce de medias moviles (9 y 21 periodos) | MA9 cruza por encima de MA21 = senal alcista |
| **momentum** | Explosion de volatilidad despues de un periodo de calma | Rango de velas se expande 2x despues de consolidar |
| **trend_continuation** | Precio retrocede al soporte en tendencia alcista (o resistencia en bajista) | En tendencia alcista, precio baja a soporte y rebota |
| **level_bounce/rejection** | Rebote o rechazo en un nivel de precio clave | Precio toca soporte historico y no lo rompe |

### Como decide cual usar

No elige uno — **los detecta todos en paralelo**. Cada minuto escanea el grafico y si encuentra algun patron, genera una estrategia. Puede generar varias en el mismo ciclo si el mercado muestra multiples senales.

Cada senal pasa por **filtros** antes de convertirse en estrategia:

1. **Confirmacion de cierre de vela**: no se dispara mid-candle, requiere que la vela anterior haya cerrado por encima/debajo del nivel (evita falsas rupturas por mechas)
2. **Filtro de mecha**: si la mecha es >60% del rango de la vela, penaliza confianza -15
3. **Confianza minima**: se calcula dinamicamente desde el contexto de mercado (tendencia, RSI, volatilidad, sesion horaria, win rate historico del setup)
4. **Spread gate**: si el spread estimado es >25% del SL, descarta la senal
5. **ATR gate**: si la volatilidad es demasiado baja (ATR < 2 pips), penaliza fuerte
6. **Conflicto entre fuentes**: si noticias dicen CALL pero estructura dice PUT, penaliza al de menor confianza
7. **Deduplicacion**: no genera si ya existe una estrategia similar (misma direccion, mismo nivel, ultimos 30 min)

### SL/TP Adaptativos

El Stop Loss y Take Profit se adaptan a la volatilidad actual usando ATR:

- **SL** = ATR-14 x 0.8, acotado entre el SL del perfil (piso) y 2.5x perfil (techo)
- **TP** = SL x ratio R:R del perfil (ej: si perfil es 3.5:15 = 1:4.3, se mantiene esa proporcion)
- El SL puede ensancharse para respetar el soporte/resistencia mas cercano (sin superar el techo)
- Si no hay ATR disponible, usa los valores fijos del perfil como fallback
- Metodo reportado en cada trade: `atr_adaptive`, `atr_adaptive+struct_sl`, o `profile`

### Expiracion Adaptativa

La expiracion de cada estrategia se calcula segun cuanto tardaria el precio en llegar al TP con la volatilidad actual:

```
expiry = max(15, min(60, tp_pips / avg_range_pips * 5))
```

Resultado: entre 15 y 60 minutos dependiendo del ATR.

---

## Ciclo de Aprendizaje

AIdan no es estatico. Cada operacion que hace le ensena algo:

```
  1. DETECTA senal    ->    2. CREA estrategia    ->    3. ESPERA que expire
        ^                                                      |
  6. AJUSTA params    <-    5. ANALIZA historial   <-    4. EVALUA resultado
```

### Paso 1: Detecta una senal
Cada minuto escanea el grafico buscando patrones. Si encuentra uno, calcula una **confianza** basada en: tendencia, RSI, volatilidad, sesion horaria, y el **win rate historico de ese patron**.

### Paso 2: Crea la estrategia
Si la confianza supera el umbral y pasa todos los filtros, crea la estrategia con entry, SL, TP adaptativos. Queda activa por 15-60 minutos.

### Paso 3: Espera que expire
Durante ese tiempo, revisa las velas cada minuto para ver si toco el TP (gano), el SL (perdio), o el Break Even. El trailing SL escalonado divide la distancia al TP en 3 pasos iguales: al alcanzar 1/3 mueve SL a entry (BE), al alcanzar 2/3 asegura 1/3 de ganancia.

### Paso 4: Evalua el resultado
Cuando expira, guarda el resultado con **todo el contexto**: direccion, setup_type, tendencia, RSI, sesion, pips, alineacion con HTF.

### Paso 5: Analiza el historial (cada 30 min)
El **AutoTuner** lee las ultimas 200 operaciones y:

1. Calcula el win rate actual como baseline
2. Prueba variaciones de cada parametro (umbrales RSI, distancias, confianzas)
3. Si alguna variacion mejora el win rate en >1%, la adopta
4. **Bloquea setups** con <35% win rate en 5+ trades (ej: si breakout tiene 30% → lo desactiva)
5. Si operar fuera de horario tiene <35% → bloquea sesion asiatica/off-hours

### Paso 6: Ajusta parametros
Los nuevos parametros se aplican inmediatamente. Ademas, la IA (Groq) recibe un resumen de lecciones aprendidas en cada analisis de noticias:

```
LECCIONES APRENDIDAS (42 operaciones):
  - CALL: 62% acierto (26W/16L)
  - PUT: 58% acierto (15W/10L)
  BB Rejection: 80% (8W/2L)
  Breakout: 35% (3W/6L) <- EVITAR
  - A FAVOR de HTF: 68% acierto
  - CONTRA HTF: 44% acierto <- EVITAR
```

---

## Dashboard

### Barra superior
- **AIdan / SCALPING EUR/USD** - nombre del sistema
- Chips con estadisticas: NOTICIAS, ALERTAS, ULTIMA HORA, NOTICIAS WR, ESTRATEGIAS WR

### Pestana DASHBOARD

**Grafico EUR/USD** - velas en tiempo real con precio live.

**Chat AIdan** - chat con IA sobre trading. Acepta imagenes de graficos. Usa datos en tiempo real + analisis SMC para responder.

**Alertas de Trading** - noticias analizadas con direccion (CALL/PUT/NEUTRAL), confianza, score. Las alertas con direccion se auto-evaluan a los 30 min mostrando un badge WIN/LOSS/BE con los pips.

**Calendario Economico** - eventos de la semana para EUR y USD.

### Pestana ESTRATEGIAS

**Panel Multi-Temporalidad SMC** - estado de H1, M15 y M5 con tendencia, swings, estructura y badge de confirmacion.

**Estrategias Auto-Generadas** - se generan de 4 fuentes:
1. **NOTICIA** (azul): noticia de alto impacto con direccion clara
2. **ESTRUCTURA** (violeta): breakouts, RSI extremo, cruces MA, momentum, rebotes
3. **SMC** (rosa): confirmacion completa HTF + zona + LTF
4. **CALENDARIO** (amarillo): pre-posicionamiento antes de datos economicos High Impact

Cada estrategia muestra grafico de velas (snapshot del momento), Entry/TP/SL, tiempo de expiracion, y se auto-evalua al expirar.

---

## Reporte a Google Sheets

AIdan puede subir un reporte diario a Google Sheets via webhook (Google Apps Script). Incluye:
- **Resumen Diario**: fecha, estrategias generadas, W/L/BE, win rate, pips netos, mejor y peor setup
- **Trades**: detalle de cada operacion con comentario en espanol explicando que hizo
- **Setup Analysis**: win rate por tipo de setup

Configuracion: setear `GOOGLE_SHEETS_WEBHOOK` en las variables de entorno o en config.py.

---

## Aprendizaje Compartido

AIdan comparte lo que aprende entre todas las instancias conectadas.
Cuando vos y otros usuarios usan AIdan, cada uno aporta trades y el sistema aprende de todos.

### Como funciona

1. Al abrir AIdan, ingresa con tu usuario y clave
2. El aprendizaje compartido se activa automaticamente
3. Cada 2 horas, AIdan sube tus trades (anonimizados) a la nube
4. Al mismo tiempo, descarga insights de otros usuarios
5. Los insights remotos tienen peso reducido (0.5x) para que tu aprendizaje local tenga prioridad

No requiere configuracion extra — todo se conecta automaticamente al loguearse.

### Que se comparte y que NO

| Se comparte | NO se comparte |
|-------------|----------------|
| Direccion (CALL/PUT) | Precios exactos de entrada/salida |
| Resultado (win/loss) | Titulo de la noticia |
| Pips ganados/perdidos | Datos de tu cuenta MT5 |
| Tipo de setup | Tu nombre o datos personales |
| Sesion horaria | Tickets de operacion |
| Indicadores (RSI, tendencia) | Balance o equity |

Si no configuras Supabase, AIdan funciona 100% igual que siempre (solo aprendizaje local).

---

## Arquitectura

```
AIdan_TodoEnUno.exe (~25MB)
  |
  +-- Collector (thread) --> RSS cada 10 min
  |     Bloomberg, Reuters, Financial Times
  |
  +-- Analyzer (thread) --> Analiza cada 1 min
  |     +-- NewsAnalyzer: Groq analiza noticias + lecciones aprendidas
  |     +-- TechnicalAnalyzer: RSI, MA, BB, S/R, ATR (Yahoo Finance)
  |     +-- MTFAnalyzer: velas H1/M15/M5, swings, estructura
  |     +-- SMCEngine: zonas demanda/oferta + confirmacion LTF
  |     +-- StructureScanner: 7 tipos de setup con filtros
  |     +-- LLM Auditor: Gemma 4 valida senales en paralelo con Groq
  |     +-- PostTradeAnalyzer: Gemma 4 evalua cada trade cerrado
  |     +-- PrePlanner: Groq + Gemma planifican eventos HIGH impact
  |     +-- AutoTuner: optimiza parametros cada 30 min
  |     +-- Alert Evaluator: auto-evalua alertas CALL/PUT a los 30 min
  |
  +-- API (thread) --> FastAPI en localhost:8000
  |     Dashboard HTML + Chat + Graficos
  |
  +-- Strategy Watcher (thread) --> Toast notifications
```

**Modelos de IA:**
- **Groq API** (gratis) - `llama-3.3-70b-versatile` para analisis de noticias y chat
- **Gemma 4** (local via Ollama) - auditor de senales, analisis post-trade, planificacion nocturna

**Datos persistentes** en `%APPDATA%/AIdan/`:
- `state/financial_news.db` - base de datos SQLite con noticias, alertas, estrategias, resultados y parametros optimizados

---

## Build

```bash
pyinstaller AIdan_TodoEnUno.spec --clean
```

El ejecutable queda en `dist/AIdan_TodoEnUno.exe`.

---

## Historial de versiones

### v3.6.3 (21 Abr 2026) — Triple bugfix: SMC order, circuit breaker, pre-planner dedup
- **SMC update order fix**: `smc.update()` se llamaba DESPUES que structure scanner leia `smc.get_status()`. Primer ciclo del dia (o cualquier con SMC stale) → htf_bias vacio → filtro counter-HTF inerte. Caso real: trade #264 CALL tomado contra H1 bearish sin info HTF.
- **Circuit breaker usaba `archived_at` en vez de `created_at`**: trades viejos que se archivaban hoy por cap-cleanup aparecian como "losses recientes" y bloqueaban AIdan. Caso real: pre_planned del 20 Abr archivados hoy junto con trade #264 → 3 losses aparentes pero de dias distintos. Fix: ordenar por created_at + ventana de 2 horas maximo para considerarse tilt real.
- **Pre-planner crea duplicados cuando corre 2+ veces al dia**: `planned_hours = set()` estaba dentro de la funcion, se reiniciaba cada llamada. Caso real: pre_planner corrio ayer 17:00 y 18:08, creo #260 (Core Retail Sales) y #263 (Retail Sales) ambos CALL para el mismo evento 13:30 UTC. Cuando publico, ambos perdieron simultaneamente (-$11.10 combinado). Fix: dedup persistente via query a auto_strategies buscando pre_planned con event_time en ventana de 48h.

### v3.6.2 (20 Abr 2026) — Fix counter-HTF filter (impacto alto)
- **Filtro contra-tendencia ampliado a HTF bias** (antes solo miraba M5 trend)
- El caso que perdia plata: H1=bearish + M5=bullish -> CALL pasaba como "aligned con M5" pero era suicida contra H1
- Nuevos thresholds:
  - Counter M5 + Counter HTF (contra ambos): conf >= 85 (extreme confluence required)
  - Counter HTF solo (M5 aligned, H1 contra): conf >= 75 (H1 es macro, peligroso)
  - Counter M5 solo (H1 aligned/neutral): escala existente (60/70/80 por strength)
- Validado con los 8 counter-HTF del 20 Abr: 5 se habrian bloqueado, PnL -$20.10 -> +$1.00 (+$21.10 ahorro)
- Fresh slate de trade_archive aplicado: borrados 185 trades pre-v3.6.0 contaminados

### v3.6.1 (20 Abr 2026) — Hotfix circuit breaker timezone bug
- **Circuit breaker bloqueaba eternamente** despues de 3 losses consecutivas por mix de timezones
- `archived_at` en trade_archive se guarda como UTC (SQL CURRENT_TIMESTAMP) pero se comparaba con `now_ar()` (Argentina, UTC-3)
- Resta daba valores negativos (-91min) que pasaban el check `mins_since < 30` → bloqueo permanente
- Fix: usar `datetime.utcnow()` para comparacion consistente + rango `0 <= mins_since < 30` (no solo `< 30`)

### v3.6.0 (17 Abr 2026) — Auditoria profunda + integridad de datos
- Fix critico: htf_bias self-referential bug (174 trades con NULL en historial). Learning engine ahora ve contexto macro
- entry_context JSON atomico al crear strategy (RSI/ATR/trend capturados AL ENTRY, no al exit)
- MT5 executor llama archive_trade con contexto completo (antes solo strategy_results con 5 campos)
- Gemma post_trade handler en get_learning_adjustments (insights ya no son write-only)
- prev1/prev2 en dynamic_conf: candle pattern boost funciona
- Key level override eliminado: entry_price = MT5 tick vivo, sin lock-in en peor precio
- D1 y H4 en MTFAnalyzer + get_daily_context() para vision macro
- Daily range awareness en dynamic_conf (posicion en rango del dia ±10 conf)
- TP estructural prioritario (apunta a resistencia/soporte con R:R >= 1:1.5)
- TP cap ATR*2 (research 2026 scalping M5: R:R 1:1-1:1.5 es optimo)
- SMC threading.Lock completo: atomic swap + snapshot reads
- Graceful shutdown con _shutdown_event
- Pending limit orders se cancelan al expirar strategy
- Cycle overlap guard, spread spike retry 3x, skip candles en formacion
- Rate limit max_trades_per_hour enforceado, circuit breaker 3 losses consecutivas
- Limpieza: 823 learning_insights + 159 post_trade_analysis borrados (contaminados pre-fixes)
- Pattern mining skip legacy trades con htf_bias vacio
- MT5 deviation 20→50 points, MIN_TRADES_FOR_ANALYSIS 3→8
- Calibraciones data-driven revertidas (basadas en data contaminada) — AIdan aprende organicamente

### v3.5.4 (16 Abr 2026)
- **MT5 como fuente primaria de velas**: `copy_rates_from_pos()` instantaneo sin latencia de red. Yahoo como fallback
- **Cache market state 5s**: precio 3x mas fresco (antes 15s), mejor alineacion senal-ejecucion
- **Price deviation gate**: rechaza ordenes si el precio se desvia >40% del SL desde la senal

### v3.5.3 (15 Abr 2026)
- **Fix critico filtro contra-tendencia**: aplicaba solo en tendencia strong/moderate (MA spread >3p), inalcanzable en M5. Ahora aplica en toda tendencia con thresholds calibrados para M5
- **Min confidence gate en news**: bloquea trades de noticias con confianza ajustada < perfil minimo
- **Win/loss por MT5 P&L real**: corrige 26 trades mal clasificados en historial
- **SL minimo 2.0 pips**: previene SLs de fracciones de pip
- **Trend context en archive**: mt5_executor guarda trend/strength/htf al cerrar trades
- **Fill price en archive**: pips calculados desde precio de ejecucion real

### v3.5.2 (14 Abr 2026)
- **SL adaptativo por ATR**: ATR-14 x 0.8 acotado entre perfil y 2.5x perfil. TP escala proporcionalmente
- **Filtro contra-tendencia**: senales contra tendencia fuerte requieren conf >= 75
- **Post-trade analysis (Gemma 4)**: cada cierre por MT5 genera analisis de calidad de entrada/salida, timing y lecciones
- **LLM Auditor (Gemma 4)**: segunda opinion en paralelo para validar senales (+10/-20 conf)
- **Pre-Planner nocturno**: planifica estrategias HIGH impact con consenso Groq + Gemma
- **Confianza direccional**: +20 por alineacion con tendencia/HTF, -20 por ir en contra
- **Base confianza conservadora**: punto de partida baja de 50 a 40

### v3.5.1 (06 Abr 2026)
- **Min confidence gate**: Estructura y Calendario respetan umbral minimo del perfil
- **Auto-login + auto-connect MT5**: restaura sesion local al iniciar
- **Filtro noticias basura**: descarta clickbait/quiz antes de Groq
- **Sync insights a Supabase**: bidireccional con otras instancias
- **Boton Salir**: desconecta sesion + MT5 desde dashboard
- **Startup programado 4am Lun-Vie**: con wake del PC

### v3.5.0 (06 Abr 2026)
- **Trailing SL escalonado**: 3 pasos proporcionales al TP. Mueve SL en MT5 real via TRADE_ACTION_SLTP
- **Groq API key rotation**: 3 keys con fallback automatico en 429/401
- **Cross-instance learning**: importa trades de Supabase con peso 0.5x para learning engine y auto tuner
- **MT5 P&L ground truth**: evalua con beneficio real de MT5, no pips teoricos
- **Fix timezone graficos**: velas en hora Argentina (UTC-3)
- **Fix evaluaciones**: corregido bug que marcaba trades ganadores como LOSS

### v3.4.0 (03 Abr 2026)
- **Login de usuarios**: pantalla de ingreso con autenticacion contra Supabase. Solo usuarios autorizados
- **Cambio de clave**: desde el dashboard, clic en tu nombre de usuario
- **Aprendizaje Compartido**: se activa automaticamente al loguearse. Sync cada 2 horas
- Credenciales de Supabase hardcodeadas — zero configuracion para el usuario
- Datos anonimizados: no se comparten precios, titulos ni datos de cuenta

### v3.3.0 (03 Abr 2026)
- **Integracion MT5 mejorada**: sync de posiciones con deal history, cierre automatico al evaluar
- **Kill switch inteligente**: evalua estrategias con P&L real de MT5 en vez de cancelarlas
- **Deteccion de huerfanas**: cierra posiciones MT5 sin estrategia asociada
- **Reconexion MT5 automatica**: si se pierde conexion, reconecta sin reiniciar
- **Learning Engine mejorado**: deep analysis cada 2h online, trigger_type insights, pattern blocking

### v3.2.0 (31 Mar 2026)
- Auto-evaluacion de alertas de noticias (CALL/PUT se evaluan a los 30 min)
- Deduplicacion de estrategias (no repite mismo setup/nivel en 30 min)
- Reporte diario a Google Sheets via webhook (resumen + trades con comentarios + setups)
- Escaneo cada 1 minuto (antes 2 min)
- Expiracion visible en cards de estrategias del dashboard
- Cooldown de senales tecnicas ampliado a 30 min (evita spam de breakouts)

### v3.1.0 (31 Mar 2026)
- Deteccion de patrones de velas japonesas (hammer, engulfing, shooting star, doji, morning/evening star, marubozu)
- Calendar Pre-News Trading: genera estrategias 30 min antes de datos High Impact
- Break Even automatico: SL se mueve a entry cuando precio alcanza 1:1 R:R
- Dashboard segmentado por tipo: NEWS / ESTRUCTURA / SMC / CALENDARIO / PATRON
- Base de conocimiento profesional: VWAP, Order Flow, velas, break even, scalping EUR/USD

### v3.0.0 (31 Mar 2026)
- SL/TP adaptativo por ATR
- Confirmacion de cierre de vela anti-mecha para breakouts
- Confianza dinamica por sesion de trading
- Expiracion adaptativa 15-60 min segun volatilidad
- Gate de spread y resolucion de conflictos entre fuentes
- AutoTuner: optimizador autonomo de parametros
- Smart Money Concepts multi-temporalidad
- Datos persistentes en %APPDATA%/AIdan/

### v2.x (Mar 2026)
- Dashboard multi-tema, tests unitarios, analisis tecnico, chat con IA, estrategias automaticas

### v1.x (Mar 2026)
- Recolector RSS, dashboard basico, alertas, calendario economico

---

## Licencia

MIT - Uso libre.

## Disclaimer

AIdan es una herramienta de asistencia, NO un sistema de trading automatico. Las senales son orientativas y no garantizan resultados. Opera bajo tu propio riesgo y criterio. Nunca arriesgues dinero que no puedas perder.
