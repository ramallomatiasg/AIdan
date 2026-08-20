# CLAUDE.md — Contexto AIdan para asistentes IA

Este archivo es leído automáticamente por Claude Code y otras IAs. Contiene todo lo necesario para trabajar en AIdan correctamente desde el primer turno.

---

## ¿Qué es AIdan?

Bot de trading automático EUR/USD scalping M5, integrado con MetaTrader 5 (cuenta ICMarkets Raw Spread Demo). Single executable Windows portable (~50MB) que corre como GUI Tkinter + dashboard web. Usa LLMs (Groq + Ollama local) para análisis de news, post-trade y estrategias.

**Owner**: Matias Ramallo (Backend & Cloud Engineer, Yalutec, Rosario AR)
**Repo**: github.com/ramallomatiasg/AIdan
**Idioma**: Spanish con el user, inglés en código y commits.

---

## Reglas críticas del user (no negociables)

1. **NO usar `Co-Authored-By: Claude` en commits**. Los commits van directo de la cuenta del user.
2. **REBUILDEAR `AIdan.exe` después de TODA modificación de código**. El user corre desde el exe, no desde python source.
3. **Cuenta demo, NO real**. Migración a real solo bajo criterios definidos en `~/.claude/projects/F--AIdan/memory/project_real_account_goal.md`.
4. **Aprobación explícita** antes de cambios significativos. Formato preferido: `Plan / Razón / Pros / Contras / Opinión propia a proceder`.
5. **No simular soluciones con muestra <6 trades**. Histórico mostró que filtros agregados con muestra chica fueron contraproducentes (hour gate, late breakout 3p — ambos removidos).

---

## 📌 NOTAS / Hilos abiertos de la sesión (REVISAR antes de cada acción)

> **Acordado 8 Jun 2026.** El user pidió: anotar acá los hilos abiertos y **revisarlos cada vez que vayamos a hacer algo**, para no dejar cosas tiradas. Regla: hilo cerrado → marcar ✅ y bajar al historial; hilo nuevo → agregarlo.

> 📁 **Acá viven SOLO los hilos ABIERTOS.** Los cerrados (mediciones refutadas, bugs resueltos,
> checkpoints viejos) están en [`docs/historial_notas.md`](docs/historial_notas.md).
> **Consultarlo con `grep` antes de proponer algo** — ahí está lo que ya se midió y se descartó
> (fade-chop 3×, ML 4 modelos, profit-lock de h1, straddle, Platt, agrandar el SL de news…).
> Al cerrar un hilo: **moverlo** a ese archivo, no dejarlo tachado acá (este archivo se carga
> entero en cada sesión y cada KB se paga siempre).

> **Acordado 8 Jul 2026 — REGLA DE SHADOW.** Siempre que haya algo corriendo en SHADOW/prueba (fade-chop, pullback, level-quality, o lo que venga), **mostrarle proactivamente al user cómo viene cada vez que hablemos del estado de AIdan**, sin que lo pida — él no tiene forma de verlo desde el dashboard. Formato: palabras simples, comparando **lo PRODUCTIVO (lo que opera de verdad hoy) vs el SHADOW (la prueba que no opera)**. Correr los scorers (`tools/score_fade_chop_shadow.py`, `tools/score_pullback_shadow.py`) para números frescos. El user prefiere consultarme a mí antes que un dashboard → la responsabilidad de traerlo es mía.

> **Acordado 10 Ago 2026 — QUÉ SE PUEDE DEJAR EN LOOP Y QUÉ NO.** El user preguntó si AIdan se puede dejar mejorándose solo. La respuesta, con evidencia de este proyecto: **hay dos tipos de mejora y se comportan al revés.** **(A) Código y plomería** — bugs, umbrales muertos, ramas mudas, guards fail-open: se verifican LEYENDO, sin muestra. Los 5 cambios del 8-10 ago (v3.52.0 → v3.53.2) fueron todos de este tipo y ninguno necesitó significancia. **Esto SÍ se puede loopear** ⇒ implementado: `tools/audit_code_patterns.py` + tarea programada semanal `aidan-auditoria-semanal` (sábados, mide y reporta, NO aplica). **(B) Lógica y estrategia** — filtros, umbrales de confianza, calibración: requieren muestra, y AIdan hace ~7 trades/día. **Esto NO se puede loopear hoy, y ya se intentó**: el meta-optimizer (v3.31.0) lleva 5 meses, computó 1.751 shadow_strategies y 1.296 shadow_trades y aplicó **CERO cambios** (15 rejected, 1 reverted, último movimiento 1-jun). Eso no es un fallo del loop: **es el gate funcionando** — ninguna propuesta tenía evidencia. Un loop más agresivo habría sobreajustado, que es lo que la metodología ya frenó 3 veces (ML, gates, bounce). El cuello de botella es **la muestra, no la automatización** (dato: cualquier intervención en h1 dispara en 6/34 trades ⇒ n=25 tomaría ~9 meses). **Y el riesgo de sacar al humano:** la clase de bug que más daño hizo acá es "excepción tragada = subsistema muerto en silencio" (mató M15 2 semanas, SMC, el reversal, el loop de aprendizaje meses); un loop sin supervisión la amplifica — por eso mismo se rechazó el lock del path de ejecución, porque un deadlock sería INVISIBLE. *Nota honesta: el 10-ago refuté 3 hipótesis propias (profit-lock, achicar el TP de h1, el stop-de-BE-dentro-del-ruido); un loop automático sin el paso adversarial explícito habría implementado las 3.*

**⏰ LÍNEA DE TIEMPO — EJECUTAR SIN QUE EL USER LO PIDA (acordado 12 Jun: "cuando llegue el momento lo hacés directamente").** Al abrir sesión en/después de cada fecha pendiente, arrancar el item solo. Mediciones/shadows: hacer y reportar. Activaciones en vivo: llevar números + recomendación en el mismo turno (el OK sigue siendo del user).
Los items con fecha están abajo marcados con 🟢🔵🔴 — **hoy pendientes: ~22 Ago** (BE de h1, v3.52.0) ·
**~28 Ago** (veredicto news, v3.51.0) · **~1 Sep** (re-medir el castigo por nivel flojo — el del
~19 Ago se corrió el 16-ago: veredicto = no tocar la perilla, n=9) ·
**~15 Sep** (1ra lectura del track D1, v3.54.0 — baseline ya corregido el 16-ago, v3.54.1). Al cumplir uno: bajarlo a `docs/historial_notas.md`
con la razón del cierre.

**Checkpoint 19 Jun — RESULTADOS (medido, broker-truth 651 pos):**
- [ ] **🔑 EL VERDADERO PROBLEMA (sharpened): perdemos ESTANDO BIEN PARADOS.** PUT 22% WR / −$58 en 10 días estando short en una caída de 160p. Perder en una tendencia limpia a favor = el problema es CÓMO ENTRA/GESTIONA, no qué decide. Confirmado por 3 lados: (a) **entra mal no tarde** (402 fills al precio planeado, pierden al baseline); (b) **"todo alineado" = PEOR** (bias-fresh 23% WR vs baseline 36) → vende el AGOTAMIENTO de cada tramo (el piso, justo antes del rebote), no el pullback — es un sistema breakout/momentum que en tendencia entra tarde; (c) #658 (PUT correcta cortada por el BE en el retroceso). **El fix de fondo = entrar en el PULLBACK de la tendencia, no en el breakout/agotamiento (vender el rebote en downtrend).** Es lógica nueva → construir en SHADOW, medir, activar si gana. Relacionado con backlog #8 (exportar la paciencia de SMC a structure).
- [ ] **No hay tweak nuevo con evidencia para hoy.** Cooldown ya activo, bias refutado, R:R/BE ya arreglados (v3.40.18/19, miden hacia adelante, 18-19 jun aún rojo pero n=2 días + varios pre-fix). El único cambio que la data SÍ respalda es estructural: el **pullback-entry en shadow** (arriba). Hacer otro tweak a ciegas = el error que la metodología evita.
- [ ] **news = fuga confirmada (n=34, 18% WR, −$55, p=0.011, CI [8-34%] debajo del baseline; reciente 0/11).** Todos los buckets de conf pierden → subir el piso no sirve. NO se apagó (el user pidió mejorar no sacar). Candidato: medir tasa de error del LLM de news (backlog) y/o ver si el fade-chop cubre lo que news pierde en chop.
- [ ] **🟢 ~15 SEP — 1ra lectura del TRACK D1 (v3.54.0, criterio pre-declarado).** Correr `python tools/score_d1_shadow.py` (regla de shadow: traerlo **sin que el user lo pida** cada vez que hablemos del estado de AIdan). Esperado a esa altura: **~7-8 señales** (2,1-2,5/mes según el baseline corregido del 16-ago) ⇒ **n insuficiente para concluir, y eso está previsto**: a este ritmo n=25 son ~11 meses. Qué mirar igual: **(a)** ¿el `close neto` a 10 velas se parece a los **+11 a +13p** del backtest post-swap (baseline corregido — el viejo +12,8p salía de una corrida no comparable), o está claramente abajo? **(b)** ¿`adv` es mucho mayor que `fav`? Si sí, el setup te pasa por arriba antes de darte la razón — es exactamente lo que refutó fade-chop (fav ~1p vs adv ~9p) y sería señal temprana de que el backtest no se sostiene. **(c)** ¿la frecuencia real coincide con 2,7/mes? Si es mucho menor, los filtros del loop vivo están recortando más de lo que el backtest asumía. **NO activar por una lectura buena**: para pasar a `active` faltan resolver las DOS razones por las que nació en shadow — el swap (CI cruza cero) y el lote mínimo (no se puede respetar el 1% con SL de 82p en una cuenta de $639). La segunda es una decisión de CUENTA, no de código.
- [x] ✅ **CERRADO 16-ago (v3.54.1) — el baseline del D1 estaba mal y ya se corrigió.** Se tomó la opción (1): re-correr el backtest con los params vivos, read-only, sin tocar producción. Lo verificado: **(a)** los params vivos difieren del default en 4 claves, pero solo 2 afectan al D1 (`breakout_dist_max`/`breakdown_dist_max` 15→7); `block_outside_sessions` se aplica en los loops de M5/news/smc/calendar y **NO en el bloque D1**, y `min_pips_for_win` es de etiquetado del tuner. **(b)** El `conf_adj` de sesión en vivo depende de a qué hora el loop ve la vela nueva y **no se puede reconstruir honestamente** ⇒ no se inventó un "auto": se agregó `--session sweep`, que corre las 4 sesiones y reporta el rango. **Resultado — el titular del 13-ago se reproduce exacto con `--params default --session off` (242 señales, PF 1,41, +16,6p), o sea que aquella corrida fue en off-hours.** Baseline corregido (params vivos, 4 sesiones): **186-227 señales · 2,1-2,5/mes (no 2,7) · +13,7 a +15,3p neto de comisión · +10,8 a +12,7p post-swap · PF 1,25-1,30.** **Positivo en las CUATRO sesiones** ⇒ el edge no dependía de la hora del reloj, que era el riesgo real de (b); el nivel sí baja ~10-15% y la frecuencia ~20%. El número quedó escrito en el docstring de `technical_d1.py` y lo imprime `score_d1_shadow.py` al final. *(La revisión del 13-ago devolvió 28 hallazgos; los 5 accionables se arreglaron en el 2do commit de v3.54.0, este era el 6to y último accionable. El resto son menores.)*
- [ ] **🔧 PENDIENTE APARTE (no urgente, no se metió en v3.54.0 para no romper "un cambio a la vez"): las claves de intervalo de `price_feed` no coinciden entre fuentes.** MT5 mapea `'1d'`/`'4h'`; Yahoo y FXCM mapean `'1day'`. Y `_map_interval_to_yahoo` tiene **default silencioso `('5m','1d')`** (`price_feed.py:263`) ⇒ pedir `'1d'` con MT5 caído devuelve **velas de 5 minutos etiquetadas como diarias**, y el log encima miente (`from yahoo (1d)`). Verificado ejecutándolo. Efectos hoy: (a) el track D1 es **inmune** (exige MT5 y valida el espaciado real de las velas); (b) `mtf_analyzer` pide `'1day'` para su D1 ⇒ **nunca usa MT5**, siempre sale por Yahoo (funciona, pero es red innecesaria y otro instrumento); (c) `'4h'` en Yahoo devuelve velas H1 a propósito (comentado en el código) — aproximación silenciosa. Fix propuesto: aceptar ambos alias en las 3 fuentes y cambiar el default de Yahoo a `None` + warning (fail-loud). Verificado que es seguro: todos los callers vivos usan intervalos que **sí** están mapeados. **Ojo también** `mt5_executor.py:512`, que tiene el tf_map duplicado con default `TIMEFRAME_M5` — misma bomba.
- [ ] **🟢 ~1 SEP — RE-MEDIR el castigo por nivel flojo en m15 (v3.50.0). Corrido el 16-ago (3 días antes): NO se sube a 25, y la razón importa.** El gatillo pre-declarado era "si los flojos siguen pasando → `PENALTY=25`". **Pasan** (12 de 15 señales castigadas sobrevivieron = 80%, y son las de conf alta: 86→71, 88→73, 91→76 — exactamente la fuga que se había previsto). **Pero la premisa detrás del gatillo se cayó**: en el forward los flojos ya no son la mitad mala. Flojos n=5 → −$7,10 (1 win); validados (>10 toques) n=4 → −$10,63 (0 wins). Antes del castigo era al revés (flojos avg −$2,97 vs validados +$0,85, n=83). Subir a 25 hoy bloquearía la mitad **menos** mala ⇒ es el "fix que no arregla nada" del principio rector. **n=9 en total, muy por debajo de cualquier gate ⇒ no se toca la perilla, se re-mide.** Lo demás medido: **(a) frecuencia** m15 3,11 → 1,29 trades/día activo (−59%), pero **el castigo NO es la causa**: solo logueó **3 DROP** en 11 días, mientras `ATR too low` pasó de 0 a **2.115 skips** — es el mercado muerto de agosto (el resto de los tracks también bajó, 3,33 → 3,00). El costo atribuible al castigo es ~3 señales de ~12 (−25%), más que el ~12% estimado pero del mismo orden. **(b) WR del resto: no mejoró** — m15 32,1% (n=28) → 11,1% (n=9), PnL −$17,26 → −$17,73. *Contexto original de por qué 15 y no 25: contra los 10 niveles flojos reales, −15 bloquea 4/10 y evita ~$11,3 de los −$29,7, pero se le escapan los dos peores (#683 y #834, conf 90 y 83); −25 bloquearía 8/10 (~$25,2) pero a n=10 ya es casi un block de la familia.*
- [ ] **🔵 ~22 AGO — 1ra lectura del BE de h1 (v3.52.0, criterio pre-declarado).** Medir sobre los h1 creados desde el 8-ago: **(a) ¿cuántos armaron el BE?** (esperado ~32% de los trades, los que tocan ≥5p — buscar en el log `SL movido a BE` / `mt5_trailing_step`); **(b) de los que armaron, ¿cuántos cerraron en ~+1p en vez de negativo?** (el rescate esperado); **(c) ¿algún ganador se cortó en +1p que antes hubiera corrido?** — este es el contra a vigilar, la evidencia decía que no pasa (los 8 ganadores históricos nunca bajaron de +3,9p) pero es exactamente lo que un contrafáctico puede errar. Query: `position_manager_log` ⋈ `trade_archive` por `strategy_id`, comparar `MAX(hwm_pips)` contra `pips` de cierre. **Si (c) aparece seguido → `BE_TRIGGER_MAX_PIPS=8`** (arma más tarde, solo 26% de los trades); **si no rescata nada → `=0`** y queda como estaba. Ambas por env, sin rebuild. *Ojo con el volumen: h1 hace ~1-2 trades/día ⇒ puede que a las 2 semanas haya n~10 y no alcance para concluir; en ese caso extender, no forzar.*
- [ ] **🔴 ~28 AGO — VEREDICTO news v3.51.0 (criterio pre-declarado, NO mover).** Medir sobre los news creados desde el 7-ago (n≥15, ~4/semana): **(a) ¿los ganadores pasaron de recorrer 40% del TP a ≥59%?** **(b) ¿los perdedores siguen en ~53% del SL o se estiraron?** (si se estiran, la perilla 2 no está haciendo su trabajo). (c) PnL y WR del track. Query: comparar `|pips|` contra su propio `stop_loss`/`take_profit` por fila (los flags `sl_hit`/`tp_hit` son **tautológicos**, se derivan de `result`+`pips` — no usarlos). **Si no se cumple → `NEWS_MIN_EXPIRY_MIN=15`** (env, sin rebuild) y news vuelve a como estaba. *Decisión del user 7-ago: news NO se apaga, se arregla.*
- [ ] **🟢 ~1 SEP — FORWARD del piso de ATR de m15 (v3.55.0, `M15_ATR_FLOOR=8`, activo desde el 16-ago).** El hint de "m15 × expansión" creció hasta pasar el gate y se activó: **ATR ≤8p = n=90, WR 27,8%, −$75,59 · ATR >8p = n=31, WR 51,6%, +$18,80** (p=0,0042, CI95 [33,1-69,8%] sin cruzar el 27,8% del comparador, mismo período los dos buckets, ATR clasificado al entrar). El diagnóstico completo: **m15 necesita ~40,5% de WR para empatar** (ganador medio +7,8p, perdedor −5,3p) y en chop saca 28%. **Lo que la revisión adversarial del propio hallazgo encontró y hay que tener presente al leer el forward: el lado BUENO es frágil** — de los +$18,80 unos +$19,49 salen de 2 días, sin ellos queda en −$0,69; sacando los 3 mejores ganadores, −$10,88. **El lado malo sí aguanta** (pierde en las dos mitades: 28,9% y 26,7%). ⇒ **La expectativa correcta es "m15 deja de sangrar", NO "m15 pasa a rentable".** Medir: **(a)** ¿la frecuencia de m15 cayó ~74% como se estimó (3,27 → 0,84 trades/día)? **(b)** ¿el PnL de m15 se acercó a cero, o el bucket >8p también empezó a perder (= el hallazgo era el artefacto de 2 días)? **(c)** ¿cuántos skips loguea (`ATR ... < piso ... -> sin scan (chop)`, 1 por hora)? **Si el bucket que queda pierde igual → `M15_ATR_FLOOR=5.0`** (env, sin rebuild) y m15 vuelve a como estaba. *No afinar el umbral sobre esta muestra: el 8 venía pre-declarado desde el 17-jul; buscar el mejor número sería overfit.*

**🧪 FASE REGISTRO (20 Ago, v3.59.0) — P CALIBRADA DE m15 (`calibrated_p`). Leer ~10 SEP.**
El 20-ago se cruzaron los **309 trades limpios** (el umbral de ~300 que la regla del 11-may pedia) y
`calibrate_confidence.py` dio su **primer PASA**: m15_structure, Brier held-out 0.2214 < gate 0.230
y < constante 0.2342 (structure y el global siguen NO PASA; la conf cruda sigue siendo basura como
probabilidad). Se activo la fase registro acordada con el user: params de Platt **CONGELADOS** (los
del fit que paso, train hasta 28-jul, en `src/analyzer/confidence_calibration.py`) y
`add_auto_strategy` registra `calibrated_p` en `entry_context` sobre la confianza FINAL
(post meta/retro). **0 efecto en decisiones** (test de inercia: ningun path de decision la consume).
**Limite conocido: el test que paso son ~29 filas y quedo sobre-confiado en todos los buckets**
(predicha > real) ⇒ registro, no activacion. **Gate forward pre-declarado** en
`tools/score_calibrated_p_forward.py`: n>=40 cerrados con registro · Brier < constante train
(WR 46,15%) · Brier < 0.230; si a n>=60 no pasa ⇒ borrar el modulo (el PASA era artefacto).
**No mezclar con la lectura del ~1-sep del M15_ATR_FLOOR** — decidir cualquier activacion despues
de esa lectura. m15 hace ~1-3 trades/dia ⇒ n=40 son ~3-5 semanas (~10 sep siendo optimista).

**🧪 SHADOW NUEVO + TCA (19 Ago, v3.58.0/.1) — INSTRUMENTACION, 0 cambios de decision.**
Ejecucion del roadmap de [`RESEARCH_INVESTIGATION.md`](RESEARCH_INVESTIGATION.md). Lo que quedo
corriendo y hay que REPORTAR con la regla de shadow: **(a) TCA** — `log_fill()` estaba escrito y
desconectado (0 filas en meses); ahora cada fill registra pedido-vs-fill + spread. Verificado
contra el broker: la cuenta es **Market Execution** ⇒ el `deviation` del request lo IGNORA el
server (el "5 pips tolerance" del codigo era mentira; comentarios corregidos) ⇒ este log es la
UNICA visibilidad de slippage. Leer con `tools/measure_tca.py` (veredicto a n>=30). **(b) Shadow
book** (`rejected_signals`, PRFS): outcome forward de lo que los filtros BLOQUEAN — atr_floor de
m15 (sin direccion, movimiento absoluto vs 7,8p), counter_both y active_opposite (save-to-miss).
Leer con `tools/score_rejected_signals.py`; **aporta a la lectura del ~1-sep del M15_ATR_FLOOR,
no la reemplaza**. **(c)** `mfe_pips`/`mae_pips` reales en el archive (trailing 1s) — el criterio
(c) del checkpoint del BE de h1 (~22-ago) ahora es una query sobre esas columnas. **(d)**
`signal_age_at_fill_min` (edad señal→fill; #625 espero 27 min) y `efficiency_ratio` (Kaufman, en
`entry_context`): features puras, medir contra `mt5_pnl` en 6-8 semanas con el gate de siempre.
**(e) Cuenta CENT: DESCARTADA** por el gate pre-declarado de costo (+25 a +90% por trade; cent+raw
no existe) — los cuellos de Kelly/meta-labeling/D1 dependen del CAPITAL, no del tipo de cuenta
(`docs/research_cuenta_cent_2026-08-19.md`). No reabrir.

**📚 RESEARCH DE MERCADO (19 Ago) — [`docs/research_mercado_2026-08-19.md`](docs/research_mercado_2026-08-19.md).**
Pedido del user. **Consultarlo antes de proponer una idea "nueva"**: tiene una tabla de lo que se
DESCARTA con fundamento y un ranking de lo accionable. Los 4 titulares:
**(1)** un estudio de falsificacion sobre **14 familias de señales intradia / 947 dias** no encontro
NINGUNA que pase (bruto 0,07-1,50 pts contra 2 pts de friccion) ⇒ el edge bruto por debajo del costo
**es la norma, no la mala suerte de AIdan**; las 2 que sobrevivieron son de **confluencia + sesion**.
**(2)** el **pullback-entry** tambien se refuta afuera (80,7% de stop-out, −4,44 pts) ⇒ el hilo #1 del
19-jun ("el fix de fondo = entrar en el pullback") queda **refutado por dos vias independientes**; lo
que sigue en pie es el diagnostico de que AIdan entra en el agotamiento, no que el pullback lo cure.
**(3)** el piso de ATR deberia ser por **PERCENTIL** (ATR contra las ultimas ~100 barras, banda
~20-90) y no en pips fijos: es lo mismo que ya mide `M15_ATR_FLOOR` pero **autoajustado** — arreglaria
que en el agosto muerto m15 perdiera 59% de su frecuencia (2.115 skips de `ATR too low`). **Es la
mejor idea del research porque PROTEGE la frecuencia en vez de recortarla.** No superponerla a la
lectura del ~1 sep.
**(4)** de 28,7 M de configuraciones de ORB probadas sobrevivio el **0,51%** al walk-forward ⇒
valida el gate del proyecto y la regla de no afinar umbrales sobre la muestra propia.
Falta y es barato: **TCA** (costo esperado vs realizado — spread al enviar, pedido vs fill), que es
lo unico que distingue "la estrategia empeoro" de "la ejecucion empeoro". **Bloqueante para real.**
*Y lo que NO se puede hacer todavia: Kelly por track y meta-labeling para sizing chocan los dos con
el lote minimo 0,01 sobre $639 — dependen del CAPITAL, no del codigo.*

**🧪 SHADOW NUEVO (19 Ago, v3.57.0) — RETROSPECTIVA PRE-DECISION.** Pedido del user: que AIdan
pueda razonar *"esta señal era CALL y no PUT por X razones"* **antes** de la próxima decisión, sin
bajar frecuencia. Implementado como **nudge de confianza, nunca filtro**: `RETRO_MODE=shadow`
(default) calcula y registra en `pre_trade_retrospective` con delta 0.
**Lo que hace:** compara la señal contra los trades similares de la MISMA FAMILIA de setup y, si la
dirección opuesta era la que pagaba, emite `contrarian` + delta negativo. Cierra el loop con
`directional_lessons`, que el post-trade escribe (criterio derivado en CÓDIGO, no por el LLM:
perdió **y** nunca se puso a favor <20% del TP **y** pegó el SL — las tres juntas).
**Hallazgo del propio armado:** `setup_type` **codifica la dirección** (`trend_continuation_bull`
es siempre CALL) ⇒ comparando por setup exacto el lado opuesto tiene n=0 SIEMPRE y la pregunta era
inrespondible. De ahí las familias dirección-neutras (`SETUP_FAMILIES`). Se descubrió ejecutándolo
contra la DB real, no leyéndolo.
**Honestidad sobre el alcance:** los gates de `min_confidence` viven DENTRO de los detectores y el
lote sale de `sl_pips` ⇒ el nudge es frecuencia- y tamaño-neutro **pero hoy INERTE sobre la
ejecución**. Su valor es el registro + la muestra. Leer con
`python tools/score_retrospective_shadow.py` (**regla de shadow: traerlo sin que el user lo pida**).
**v3.57.1-.2 (mismo dia, modo autonomo):** la leccion **ya no depende de que Ollama este arriba**
(se deriva tambien en `archive_trade`, que corre para todo trade cerrado y tiene la verdad del
broker; los 2 paths coexisten porque `add_directional_lesson` es idempotente por `strategy_id`) —
sin eso, un lazo 100% determinista quedaba de rehen de un 7B y `directional_lessons` dejaba de
crecer **sin que nada falle**, que es la clase de bug que ya mato a M15, SMC y al reversal. Y el
**lazo pasa a ser bidireccional**: el post-trade ahora recibe el razonamiento con el que se entro y
devuelve `missed_factor` (lista cerrada, columna propia) = que condicion del contexto NO estaba
mirando la entrada. *Al modelo se le pasan los NUMEROS de la comparacion, no el veredicto: si
leyera "la opuesta pagaba" lo repetiria como loro (el error de la hoja de respuestas de v3.53.7).*
**Antes de usar `missed_factor` mirar su ADHERENCIA** (el scorer la imprime y avisa): si un solo
valor cubre >=80%, el modelo contesta por costumbre y el campo es ruido.

**Gate pre-declarado para pasar a `active`, las 4:** n>=25 `contrarian` cerrados · WR por debajo del
comparador · CI95 de Wilson que NO cruza · PnL/trade negativo y peor. **Si con n>=40 sigue sin
separar ⇒ `RETRO_MODE=off`, no buscarle la vuelta.** *Ojo al leer: que `aligned` rinda bien NO es
evidencia — arrastra el sesgo de que lo que venía ganando sigue ganando; lo que tiene que demostrar
es que detecta lo MALO.*

**🔌 CABLEADO (19 Ago, v3.57.0) — `adjust_setup_confidence` ya se puede aplicar.** Estaba
implementado desde v3.31.0, con lista cerrada de change_types, guard-rails y validación por shadow,
y **`get_confidence_adjustment_for_signal` no se llamaba desde ningún lado** ⇒ el change_type era
inaplicable por construcción. Ahora se invoca en `add_auto_strategy` (el único camino por el que
nacen todos los trades). Con `setup_type` ya poblado (v3.48.0) las 2 mitades del mecanismo existen
por primera vez. Los tests son de **call-site**, no solo de la función: un test que solo ejercitara
la función habría estado en verde los 5 meses en que el mecanismo estuvo muerto.

**🎚️ PERILLA (19 Ago, v3.57.0) — `ENABLE_NEWS_TRACK`, default ON.** Se entrega el mecanismo para
apagar la EJECUCIÓN de news sin borrar el track (el alert se sigue guardando y midiendo con
`measure_news_llm_error.py`). **NO se giró**: la decisión del user del 7-ago es "news no se apaga,
se arregla" y hay veredicto pre-declarado ~28 ago. Girarla es decisión del user, no mía.

**🧪 FASE 2 EN CURSO (18 Ago, corriendo) — ¿el detector tiene edge en el TIMEFRAME DONDE OPERA?**
Fase 1 (`579cc22`) midió `detect_structure_signals` en velas **D1** sobre 21 pares y concluyó que
el problema es el **generador de señal** — que también alimenta structure/m15/h1 en vivo. **Esa
última parte es una EXTRAPOLACIÓN, no una medición**: los tracks vivos corren sobre M5/M15/H1.
Fase 2 mide eso: **M15, 500k velas/par (~20 años), los MISMOS 21 pares** (los 5 que quedaron fuera
por historia corta son exactamente los mismos 5 que Fase 1 descartó ⇒ comparación directa).
Criterio + 3 enmiendas commiteados ANTES de correr: `docs/fase2_criterio_declarado.md`
(`56bbba4`, `d631703`, `2846de6`). **Las 4 condiciones, en las 4 sesiones**: pooled > 0 · CI95
inferior > 0 · positivo en las dos mitades · **por encima del percentil 95 de un control de
entradas ALEATORIAS** (el que le faltó a Fase 1b). *Ojo al leer*: con n ~4,7M por sesión el CI es
minúsculo ⇒ las condiciones 1 y 2 son casi automáticas; **el poder discriminante está en el
control aleatorio**. Pasa 1 y 2 pero no 4 = ruido con muestra gigante, no edge.
**Acción comprometida si NO pasa: se apagan structure/m15/h1 y se pasa a SMC.** Si pasa, el
problema vuelve a ser costo/gestión (reparable) — y un "pasa" es permiso para investigar, NO para
operar. **4 bugs encontrados en el arnés antes de tener números** (todos de la familia
"falla en silencio y devuelve algo plausible"): `load_live_params` devolvía tupla y el `except` se
lo tragaba · MT5 baja la historia async ⇒ iba a excluir 25 de 26 pares como "sin datos" · el
detector consultaba la DB de PRODUCCIÓN una vez por vela (66% del tiempo en I/O, y el valor
cambiaba mientras AIdan escribía ⇒ irreproducible) · `except` sin fail-loud.

**🔬 REVISIÓN CRÍTICA DEL CEREBRO (15 Jun, workflow 5 frentes + verificador adversarial; los 3 tracks COMPARTEN la lógica) — VEREDICTO: falla de DISEÑO, no bugs sueltos.** Un patrón roto se repite: **constantes en pips de M5 + confianza que suma factores colineales**, heredado igual por M15/H1 (las subclases solo cambian `_fetch_candles`+profile). Hallazgos VERIFICADOS por mí en código:
- [ ] **[EL #1, hecho de código no estadística] El R:R que el sistema cree tener es FALSO.** El cap `tp_cap = max(ATR,2)*2` (`technical.py:1430`) recorta el TP nominal. Tracé los 3: **M5 TP 20p→~5p (R:R real 1:1.4)**, **M15 60p→~18p (1:1.2)**, **H1 100p→~48p (1:1.2)**. Con 37% WR + comisión ~1.3p → pérdida matemática (hace falta ~46% WR para empatar a 1:1.2). **Explica mecánicamente "gana poco / avg win 4p".** Todo (sizing, BE, trailing, PM-arm) razona sobre un TP que el motor borra. Ojo: el cap está A PROPÓSITO (20p nunca pegaba en 15min M5) → el fix es **escalarlo por timeframe/expiry**, NO sacarlo (eso de paso arregla H1/M15, donde el cap es claramente erróneo: H1 SÍ puede recorrer 100p en 180min).
- [ ] **[#2, por qué H1 es el PEOR PF 0.36] SL "adaptativo" es mentira en M15/H1.** `final_sl = max(floor, min(cap, ATR*0.8))` con floor=15p/40p domina siempre al ATR (`technical.py:1357-1359`) → **SL FIJO**, no se adapta. Y TODAS las constantes (breakout_dist_max 7p, proximities 12-15p, cluster 5p, volatility 10/4, momentum_consol 10p) están en pips M5 → en velas H1 (12-30p) son sub-vela → el cerebro dispara fuera de fase. **El fix: escalar todo por ATR/TF — solo toca H1/M15.**
- [ ] **[#3, el motor de "conf 90 = 0% WR"] dynamic_conf cuenta el mismo macro-trend ~3 veces** (`technical.py:460-462` + `491-496` + call-site breakout `686`): "todo alineado" suma ~+38 de UNA sola realidad (= el precio ya se movió = entrada tardía). **Calibrar conf→P(win) con 150-300 limpios va a chocar igual** porque el input ya viene podrido. BLOQUEADO por regla propia (<300 limpios) pero el colapso del doble-conteo se puede medir en shadow.
- [ ] **[#4-5, menores] entrada compra el post-cruce** (2 cierres consumados + 0.3-7p extensión = el movimiento ya pasó; `technical.py:680-682`); **S/R = fractal de 2-vecinos sin validar fuerza/toques** (genera niveles de ruido).
- *Plan de ataque (acordado 15 Jun):* **Grupo A (plomería, hecho v3.40.17)** + **Grupo B medido de a uno**.
- [ ] **Sigue en Grupo B:** escalar-las-otras-constantes-por-ATR/TF (breakout_dist, proximities, cluster, SL floor M15/H1 — toca solo H1/M15); confianza (triple-conteo) queda gated por calibración limpia.

**🐞 CAZA DE BUGS DEL PATH VIVO (15 Jun, a pedido del user "asegurate que no haga falta corregir bugs reales") — VEREDICTO: las pérdidas NO son por un bug, son de DISEÑO/calidad de entrada.** 2 workflows tuvieron 7/10 agentes caídos por error 500 → las slices críticas (sizing, BE/trailing, cooldown, etiquetado) las verifiqué A MANO. Path de plata SANO, verificado línea por línea:
- **Sizing** (`mt5_executor.py:171`): risk%/(SL×10), clamp, ~1%/trade. Correcto. **BE/trailing** (`AIdan:3660-3718`): mueve el SL solo a favor (CALL↑/PUT↓), nunca lo afloja, solo tightening. Correcto. **Handoff** señal→orden: SL/TP/dirección/lote llegan intactos, `open_position` reconstruye el lado por dirección (no puede salir invertida), idempotencia sólida. **Cierre/PM**: cierra el ticket correcto, sin doble-fill, el late-close ya no pisa al PM (v3.40.11 verificado en 3 sitios). **P&L/labels**: broker-truth (deals+comisión) una sola vez, archive idempotente. **Cooldown** (`AIdan:1009-1033`): lógica correcta (AR vs AR, guard 0≤elapsed<5).
- [ ] **🔑 HALLAZGO GRANDE (responde "¿se está puliendo?" → NO): el feedback de aprendizaje vivo está MUERTO para structure/m15/h1/smc.** El blend ±15 (`technical.py:536`) consume `get_setup_win_rates()` (`db.py:1803`), que lee de `strategy_results` (5 filas, setup_type vacío) y `signal_results` (356, **todas 'news'**). Los botones Win/Loss que poblaban `strategy_results` los **sacamos en v3.40.6**. `trade_archive` (la tabla buena) guarda `trigger_type` pero `setup_type` está NULL en 384/386. **Resultado: AIdan archiva los resultados pero NO los usa para ajustar confianza en vivo, salvo news (y la conf de news la pone el LLM).** Confirma a Dispatch y más hondo. **NO se arregla wireándolo ahora** (= calibrar sobre data sucia = el error ML rechazado 3×); el fix principista es la **calibración empírica con data limpia ya planeada (~26 jun / 17 jul)** con gate de significancia.
- [ ] **(detalle viejo) cap de lote pre_planned (ya resuelto arriba):** (a) **cap de lote pre_planned muerto** — `get_active_unexecuted_strategies` (`db.py:2002` SELECT, `2010` dict) no devuelve `trigger_type` → el retry (`AIdan:3161`) pasa `None` → el cap 0.05 (`mt5_executor.py:273`) nunca dispara para pre_planned (que se ejecutan SOLO por ese retry); no-op al balance actual, leakea lote bajo consensus-boost/balance-alto — fix 1 línea, importa antes de cuenta real; (b) **PM marca `executed=1` sin mandar orden** cuando la posición ya estaba cerrada por TP/SL (`mt5_executor.py:877` devuelve precio sin order_send; `AIdan:3901`) → no afecta trades/labels, pero **contamina la lectura del experimento PM** (mezcla "cerré yo" con "ya estaba cerrado") → tenerlo en cuenta en el veredicto PM del 26 jun.

**[NO es incidente] AIdan.exe apagado = lo cierra el USER a mano** (aclarado por él 15 Jun: "cada vez que ves AIdan caído soy yo que lo cierro, no pasa nada"). NO es un crash, NO hay problema de estabilidad, NO hace falta el watchdog. **Regla: si el proceso AIdan no está corriendo, asumir que el user lo cerró — no alarmar, no perseguir causa, no sugerir watchdog.** (Aplica retroactivo al "incidente 14 Jun" de más abajo: también era el user.) El rebuild lo levanta normal a v3.40.17, MT5 ok, balance $726.97.

**Experimentos en vivo (midiendo — NO tocar sin data nueva):**
- [ ] **Event-window (conciencia de eventos, v3.40.14)** · `EVENT_WINDOW_MODE=shadow`. Respuesta al pedido del user "tiene que operar alrededor de eventos, pero bien" (12 Jun). Hook en `_try_mt5_execute` (cubre ejecución normal Y retry): etiqueta CADA ejecución con proximidad al evento HIGH/MED más cercano (`event_window_log`, clasificación en el momento) + marca `would_block` si una señal CIEGA (structure/m15/h1/smc) o VIEJA (>10min, caso #625) cae dentro de la ventana (HIGH 15min antes/30 después; MED 5/15). news/pre_planned/calendar NO se marcan (jugadas de evento por diseño). **Plan "operar eventos bien"**: (1) este etiquetado junta data limpia de eventos, (2) shadow del straddle ya corre (feed FF REVIVIDO 12 Jun — verificado: /calendar con eventos), (3) en 2-4 sem decidir LA jugada de evento con data: straddle vs momentum post-release (única con evidencia viva: #604 ganó +5.30 entrando 7min post-CPI) vs skip. Flip a `active` solo con data del shadow.
- [ ] **Bounce-entry** · `SKIP_BOUNCE_ENTRY=shadow`. Juntar clasificación **limpia** en vivo (log al ejecutar, no reconstruida). No activar sin señal robusta varias semanas. Clasificación retrospectiva = frágil.

**Obs 11 Jun (día PPI/ECB: 14 trades, 3W/11L, −$29.22 — 3er día seguido de eventos) — para el checkpoint del viernes:**
- [ ] **PM tuvo su PRIMER día real en ambas direcciones** (evidencia viva para el punto 2 de la agenda): **primer CLOSE_PROFIT de la historia** (#621: se extendió **118min** más allá del expiry —comportamiento nuevo v3.40.11—, llegó a HWM 84% del TP, retrocedió y el PM aseguró +$4.52) + **6 CLOSE_PROTECT** cortando sangrías a −1.4/−1.8/−2.2/−2.9p en vez de SL completo + #627 TP completo (+$9.04). En el peor régimen, el management mostró su cara buena por primera vez. n chico, pero es exactamente lo que el experimento debía demostrar.
- [ ] **[obs, familia del bug #615 pero más leve] Edad/expiry corren desde la SEÑAL, no desde el FILL** — #625 esperó **27min como limit order pendiente** y el fill le llegó con 27 de sus 45min de vida ya comidos (el PM lo evaluó "28/45min" a los 17s del fill). Evaluar si la edad debería correr desde el fill para TODOS los trades → requiere timestamp de fill (columna `mt5_filled_at`, hoy NO existe). No urgente; decidir si vale la migración.
- [ ] **[obs] SL puede ejecutar con slippage GRANDE en spikes**: #625 cerró 1.15504 vs SL 1.15392 = **11p más allá del stop** en una vela de ~30p (el broker llena al siguiente precio). No es bug — es microestructura — pero significa que el "riesgo 1% por trade" puede excederse en velas violentas. Dato para sizing y CRÍTICO para la futura cuenta real.
- [ ] **[obs NUEVA, forense del spike 11 Jun] El retry de ejecución puede vender/comprar a MERCADO una señal VIEJA adentro de un spike** — #625: señal creada 14:01 AR, sin fill por 27min, y el bloque "MT5 retry" la ejecutó a mercado a las 14:28:58 — **dentro del primer minuto del spike** (vela de 19.1p tras un mercado planchado de 0.5p/min). Encima el SL (21.8p, estructural ancho) ejecutó con 11.2p de slippage por los gaps (precio saltando 13-15p/min) → −$13.48, la peor del día. La señal estaba obsoleta: "mejor precio" de fill en plena reversa violenta = selección adversa (te llenan justo cuando el mercado corre en contra). **Candidato a medir (no actuar aún): WR de fills tardíos (fill − señal > 10min) vs fills inmediatos** — medible con broker-truth (order setup time vs created_at). Sumar al script de sospechosos si da el tiempo el viernes.
- *Contexto:* la racha 10-11 Jun cerró en ~−$53 los dos días (CPI whipsaw + PPI/ECB). Verificado de nuevo: sin pérdida de datos, sin bugs de ejecución nuevos (el −13.48 fue slippage de spike), threads vivos, daily loss limit (−$30/día) armado y sin disparar.

**Checkpoint 12 Jun — RESULTADOS DEL REVIEW COMPLETO (workflow 4 frentes + verificador, tarde):**
- [ ] **Bounce log infla por retries**: 304 filas = solo 65 estrategias (#625 logueado 121 veces) → **todo análisis debe dedupear por strategy_id (primera fila)**; dedup real: 28/65 (43%) son bounce — eso es PREVALENCIA, no WR (no confundir). 3 estrategias cambian de clase entre intentos.
- [ ] **⚠️ Universos lifetime SIN reconciliar (no usar ninguno como baseline canónico):** broker 617 posiciones/−$512 vs DB 377/−$352 vs balance-implícito −$273 vs suspects n=363. Pueden coexistir (deals sin linkage, mt5_pnl NULL viejos) pero nadie lo reconcilió. Item para el 19 Jun.
**Checkpoint 12 Jun — DECISIONES TOMADAS:**
**Barrido exhaustivo 14 Jun (broker-truth, 617 posiciones, 4 frentes + verificador) — RESULTADO: el pozo de data sucia está SECO:**
- [ ] **Candidatos a VIGILAR con data limpia (hoy RUIDO, no tocar):** (a) racha "4+ pérdidas seguidas" (n=118, WR 30%, p=0.058, CI cruza por 0.01 — el más cercano); (b) hora 11h AR (peor bucket, p=0.049 pero CI cruza, mismo perfil que las 11h-UTC removidas); (c) vol baja peor que alta (32% vs 41%, roza pero no pasa) → posible ATR-floor, no detector. Re-medir 26 Jun/17 Jul con `tools/measure_streak_recency.py` y `measure_regime_x_trigger.py`.
- [ ] **"m15 sin techo de ATR" NO medible retrospectivo**: `avg_range_pips=0` (sentinel del doble-encode) en 71/87 m15 — solo medible hacia adelante con data limpia v3.40.x.
- *Lección metodológica reconfirmada (workflow):* el gate rechazó correctamente 2 borderline (hora 11h, racha 4+) por CI-cruza-baseline aunque p<0.05 — exactamente para lo que se diseñó. Y un hallazgo "significativo" (régimen×vol) resultó lookahead. Tools nuevos read-only: `measure_streak_recency.py`, `measure_regime_x_trigger.py` (env CUT_BEFORE_S).

**Deudas técnicas / gaps:**
- [ ] **OLLAMA_API/URL/MODEL sin definir** — GUI-only, no afecta trading. Spawneado como task aparte. Baja prioridad.
- [ ] **`calendar` trigger (0 trades en 325) — en SHADOW desde v3.40.4** · `CALENDAR_MODE=shadow`. Investigado 8 Jun, 2 causas: **(1) Feed FF 429** — el cache solo guardaba éxitos (`and events`) → con events vacío re-fetcheaba CADA ciclo → AIdan **se auto-baneó la IP** (hammering). ARREGLADO v3.40.4 (`main.py`): cachea el intento 1h SIEMPRE + User-Agent + loguea el 429 (antes silencio). Ahora le pega a FF máx 1/hora → la IP debería destrabarse en horas/días (no controlable desde acá). **(2) Straddle ROTO** — la anti-contradicción bloquea la 2da pata → solo dispararía CALL. Por eso quedó en shadow (`calendar_shadow_log`): loguea ambas patas SIN operar. **Para activar a vivo:** esperar que FF devuelva data → revisar shadow → arreglar el straddle (ambas patas; OJO doble comisión = problema #1) → recién ahí `CALENDAR_MODE=active`. El path 'active' TODAVÍA tiene el bug del straddle (no flippear sin arreglarlo).
**Auditoría 8 Jun (multi-agente, 5 frentes) — hallazgos CONFIRMados (ninguno rompe trading HOY):**
- [ ] **[LOW/hipótesis] `sync_pending_orders` 'expired' en respuesta vacía transitoria** (`mt5_executor.py:552-589`): clase v3.35.2 al revés. HIPÓTESIS (necesita confirmación runtime). Hardening: confirmar con `history_orders_get` antes de escribir 'expired'.
- [ ] **[LOW] Idempotency `startswith` colisión** (`mt5_executor.py:164`): "AIdan #5" matchea #50/#565; hoy inalcanzable (siempre el id más nuevo). Fix defensa: match delimitado.
- [ ] **PENDIENTE del mismo workflow (fixes de UN SOLO THREAD, en orden de valor/riesgo; ninguno necesita lock):** ~~① cap-delete~~ ✅ **HECHO en v3.53.1** (subselect `_deletable` con `mt5_ticket IS NULL OR mt5_status='closed'`, test de mutación escrito antes del fix, verificado end-to-end sobre copia de la DB). ~~② guard del startup eval~~ ✅ **HECHO en v3.53.2** (fail-closed con el patrón `_tk='unknown'` del gemelo in-loop; saca MT5 de la ecuación, decide con el ticket de la DB). ~~③ doble conteo de la comisión de entrada~~ ✅ **HECHO en v3.53.3** (el fallback reemplaza en vez de acumular; verificado que el caso normal no cambia). *Era:* `sync_closed_positions` (`mt5_executor.py:759-781`): `pnl` no se resetea entre el loop principal y el fallback por tiempo, y la condición de entrada al fallback es `if not deals or close_price == 0` ⇒ entra aunque `deals` no esté vacío, cuando el deal de cierre todavía no propagó. **Toca el cálculo de `mt5_pnl`, que todo el proyecto trata como verdad ⇒ test escrito ANTES, y no shipear junto con nada.** ~~④ kill switch del dashboard~~ ✅ **HECHO en v3.53.5** (una sola fórmula de P&L, no marca `closed` sin deal de cierre, usa `update_mt5_close`, y ya no sostiene el write-lock mientras habla con el broker). ~~⑤ UNIQUE INDEX en `trade_archive`~~ ✅ **HECHO en v3.53.5** (migración que cuenta duplicados primero + `INSERT OR IGNORE`). **⇒ los 7 items del workflow quedaron cerrados.** ~~⑥ el retcode 10022 de la orden límite~~ ✅ **CERRADO en v3.53.4, pero NO arreglando el 10022**: medido 36/36 rechazadas con 36/36 fallbacks a mercado ⇒ el mecanismo nunca operó y arreglarlo sería estrenar una entrada no medida con sesgo adverso estructural. Se apagó el intento (`LIMIT_ORDER_ENABLED=false`), que no cambia el comportamiento efectivo y saca el ruido. La causa del 10022 queda SIN diagnosticar a propósito (3 hipótesis abiertas). ⑦ el **profit-lock cierra en ROJO** etiquetado `CLOSE_PROFIT` (`position_manager.py:92`, `if progress <= keep*hwm` sin piso en cero — verificado ejecutando la función: hwm 35p/progress −8p → `CLOSE_PROFIT`) ⇒ contamina el bucket con el que se mide el propio mecanismo (por eso #678 con −$3,25 aparecía entre las "ganancias").
- [ ] **[MED, DEFERIDO — 2da auditoría 9 Jun] Cierre del PM sin lock** (`mt5_executor` no tiene lock interno; `_mt5_lock` solo protege la referencia): el cierre del PM corre carrera con el cierre por expiry y el orphan-detector sobre el mismo ticket (clase v3.35.2 del lado del cierre). Hoy ENMASCARADO (force-close activo desactivado → lo peor es un cierre duplicado rechazado + log feo, sin doble-fill). Fix = serializar `order_send` con un lock — cambio de concurrencia con riesgo, hacer con cuidado **antes de cuenta real**, no apurado.

**Verificado OK (no tocar):** los 3 fixes de v3.40.0 (htf_bias, rr_ratio, jitter) completos; SL/TP dirección + BE/trailing + lot sizing OK; guard del eval de arranque (phantom-P&L) presente; 3 tracks alcanzables y M15/H1 ya LOGUEAN errores; guard-rails sólidos (incl. force=True); binomial/Wilson correcto; sims no escriben prod; SQL parametrizado. **El #580 sostenido hasta expiry = diseño intencional** (R1 no arma sin +60% TP; antes de soft-expiry el único stop es el SL duro), NO bug.

**Riesgo estructural transversal (los 5 agentes coinciden):** la CLASE de bug que mató M15 (excepción tragada a `logger.debug`) sigue presente arquitectónicamente aunque cada instancia puntual esté arreglada. Todo refactor futuro puede volver a fallar en silencio.

**Bloqueado hasta tener data (NO tocar antes):**
- [ ] **dynamic_conf / calibración de confianza** — bloqueado NO por count sino por **data LIMPIA** (insight del user, 9 Jun: "está lleno de data mala esos 300"). Tenemos 323 por count pero están **sucios**: mezcla ~v3.6→v3.40 (filtros/SL-TP/pipeline cambiaron → un "conf 70" no es comparable entre versiones) + **phantom-P&L pre-v3.40.0** (labels win/loss falsos) + período M15/H1 muerto + regímenes distintos. Calibrar sobre eso = garbage in (por eso el ML v3.35.0 dio espejismo: entrenó sobre esta misma pila sucia). **Limpios del sistema actual (v3.40.x): solo ~31 (desde 5 Jun).** Necesitamos ~150-300 LIMPIOS acumulando desde ahora, clasificados en el momento (no reconstruidos). Mientras: trabajar ALREDEDOR del número (no confiar en él), NO calibrar. Confirmado empíricamente 9 Jun: conf 60-99 todas ~37-40% WR (plano); score reciente invertido (score<70 → 65% WR vs ≥70 → 41%).
- [ ] **ATR ceiling + params overfit "en cola"** — revisar en checkpoint, no antes.

**Principio que rige (lección LinkedIn 8 Jun):** *"most AI failures are **data & architecture** failures, not **model** failures"* → **confirma** la metodología: no perseguir sofisticación del modelo (ML ya refutado a n<300), sí invertir en calidad de datos + evaluación + plomería. El stack RAG (vector DB, embeddings) NO aplica a AIdan. Es validación, no to-do nuevo.

---

## Metodología de trabajo con IA (acordado 29 May 2026)

Cómo trabajar AIdan con asistentes IA. Persiste entre sesiones.

> **🧭 PRINCIPIO RECTOR (acordado 3 Jun 2026): un fix que no arregla nada, EMPEORA.**
> En un sistema de trading en vivo los cambios NO son gratis: un filtro que no separa
> ganar/perder recorta frecuencia para nada; un modelo que no es mejor agrega falsa
> confianza; un tweak sobre ruido sobre-ajusta. Por eso, antes de TODO cambio:
> 1. **Pensarlo dos veces.** ¿Esto realmente arregla algo, o lo creo porque quiero que arregle?
> 2. **Cuestionar la propia evaluación.** ¿Puede estar mal MI medición? ¿Cuál es la medición
>    LIMPIA (real, no simulada; medida en el momento, no reconstruida)? Si la muestra limpia
>    es chica → la respuesta honesta es "no sé" → no actuar.
> 3. **La carga de la prueba la tiene el cambio.** Default = NO tocar. Solo cambiar con
>    evidencia real y verificada.
> 4. **Pero conclusión sin acción tampoco sirve**: cuando la evidencia (real) alcanza, jugarse
>    un juicio calibrado y actuar — y revisarlo con datos nuevos. Ni sobre-confianza ni parálisis.
> Track record que lo justifica (3 Jun): bounce-skip (habría cortado las mejores trades),
> ML predictor v3.35.0 (espejismo), gates v3.34.0 (ruido) — los tres "arreglos" habrían
> empeorado AIdan, frenados por cuestionar antes de aplicar.

1. **Verificación adversarial de hallazgos estadísticos (ANTES de proponer/aplicar)**.
   Todo filtro, block de bucket, o cambio de param pasa primero por un check escéptico:
   - Reportar siempre: `n`, WR del subset vs **baseline 37.4% (294 trades archive)**, p-value de binomial test, e intervalo de confianza 95%.
   - **Default = RUIDO (no proponer)** si: `n < 20-30` **o** el CI 95% del subset cruza el baseline.
   - Si hay sub-agentes disponibles: 3 verificadores independientes, decidir por mayoría.
   - Enchufar este paso **antes del shadow validation** del nightly_analyst (no gastar ciclos de shadow en ruido). Punto de inserción: `tools/nightly_analyst.py:_persist_changes()`.
   - Esto ataca el error recurrente ya documentado (hour gate, late breakout 3p removidos; block_conf_bucket 60-69 revertido; #7/#9/#13 rechazados — todos ruido de muestra chica).
   - **⚠️ REGLA CRÍTICA (3 Jun 2026, lección triple del caso bounce-entry)**:
     1. **Validar con `mt5_pnl` REAL, nunca con outcomes simulados.** El backtest re-simulando SL/TP/expiry dijo "bounce 22% WR, p=0.000"; con outcomes reales fue 43% vs 34% — el sim había INVERTIDO la realidad (penaliza de más trades que arrancan adversos pero se recuperan en vivo).
     2. **El gate de significancia NO protege contra datos sesgados** (corrió p=0.000 sobre sim basura: garbage in, garbage out).
     3. **Aun con outcomes reales, si la CLASIFICACIÓN del subset es frágil, el hallazgo no vale.** Clasificar bounce re-bajando velas MT5 (timezone server-vs-UTC + cuál-vela) es dudoso en TODOS los análisis retrospectivos. La medición limpia = clasificar EN EL MOMENTO (shadow log al ejecutar), no re-construir después. Si la muestra limpia es chica (caso bounce: n=4), la respuesta honesta es "no sé" → no actuar, juntar datos limpios.

2. **Backtests y sweeps en paralelo (sub-agentes / Workflow)**. Los barridos del backlog son INDEPENDIENTES → correr en paralelo, un sub-agente por combinación, recolectar y rankear por PF. Aplica a: #1 (RF/XGBoost vs LR), #2 (gate tuning vel×body ~30 combos), #3 (modelo por trigger_type). Nunca secuencial a mano.

3. **NO adoptar frameworks tipo "superpowers"** (spec→plan→TDD greenfield). AIdan es sistema vivo de research cuantitativo con tests livianos. Única excepción: si se encara #10 (pivot a swing H4/D1), ahí sí conviene fase de diseño/plan formal.

4. **Tests de regresión en el path de ejecución**. Cubrir la clase de bug del v3.35.2 (orden MT5 duplicada en reconexión / idempotencia en `mt5_executor.open_position`). Los tests actuales (db, feed, news) no tocan el broker. **Sube de prioridad antes de Fase 2 (cuenta real)**.

---

## Arquitectura

### Layout

```
F:/AIdan/
├── AIdan_TodoEnUno.py        # Monolito principal (3500+ lines): GUI + analyzer + admin
├── AIdan.spec                # PyInstaller spec
├── start_aidan.bat           # Launcher (Task Scheduler 4 AM AR)
├── dist/AIdan.exe            # Binario producción (~50MB)
├── src/
│   ├── analyzer/
│   │   ├── technical.py            # Structure scanner + market state + adaptive SL/TP
│   │   ├── news_analyzer.py        # Groq + Gemma news scoring
│   │   ├── pre_planner.py          # Pre-market planner LLM
│   │   ├── llm_auditor.py          # Gemma signal audit
│   │   ├── post_trade_analyzer.py  # Gemma post-trade lessons (estructura SL/TP advice v3.15)
│   │   └── smc.py                  # Smart Money Concepts (multi-TF)
│   ├── broker/
│   │   ├── mt5_executor.py    # Orden execution + trailing + BE
│   │   └── price_feed.py      # Candle fetching MT5/Yahoo
│   ├── common/
│   │   ├── config.py          # APP_VERSION + env vars + Groq keys
│   │   └── db.py              # SQLite + learning_adjustments aggregation
│   ├── admin/main.py          # FastAPI dashboard (port 8000)
│   └── optimizer/auto_tuner.py # AutoTuner params iteration
├── tools/                    # Scripts standalone (sims, audits, benchmarks)
└── config/                   # YAML/JSON configs runtime
```

### Datos persistentes

```
%APPDATA%/AIdan/state/
├── financial_news.db    # SQLite — TODA la data (alerts, auto_strategies, trade_archive, learning_insights, etc)
├── aidan.db             # Legacy, pequeña
└── learning_insights_backup_*.csv

%APPDATA%/AIdan/data/YYYY/MM/DD/HH/news.jsonl   # News raw por hora
%APPDATA%/AIdan/config/                          # Copy of config dir from exe
%APPDATA%/AIdan/templates/                       # Copy of templates from exe
```

### Tablas SQLite clave

| Tabla | Propósito |
|---|---|
| `auto_strategies` | Trades activos/cerrados (live state) |
| `trade_archive` | Trades cerrados archivados (histórico ML) |
| `news` | News collected |
| `alerts` | LLM analysis de news → CALL/PUT/NEUTRAL |
| `learning_insights` | Patterns aprendidos de Gemma post-trade |
| `optimizer_params` | AutoTuner runtime params (breakout_dist_max, etc) |
| `blocked_setups` | ML-driven blocks |
| `mt5_config` | Kill switch, risk percent, etc |

### Tipos de estrategia (trigger_type)

| Trigger | Origen | Confianza típica |
|---|---|---|
| `news` | LLM news scoring (Groq llama-3.3-70b) | 50-80 |
| `structure` | Breakout/breakdown detection (technical.py) | 60-85 |
| `smc` | Multi-TF supply/demand zones | 65-85 |
| `pre_planned` | LLM pre-market plan | 60-90 |
| `calendar` | Economic calendar trigger | 50-75 |

---

## Comandos clave

### Verificar AIdan corriendo

```powershell
Get-Process -Name "AIdan" -ErrorAction SilentlyContinue
(Invoke-WebRequest -Uri "http://localhost:8000/version" -UseBasicParsing).Content
```

### Ciclo "edit → rebuild → restart"

```powershell
# 1. Edit src/...
# 2. Kill AIdan
taskkill /F /IM AIdan.exe

# 3. Rebuild
cd F:\AIdan
pyinstaller --clean --noconfirm AIdan.spec

# 4. Launch (sin abrir consola)
Start-Process -FilePath "F:\AIdan\dist\AIdan.exe" -WindowStyle Hidden

# 5. Verificar version nueva
Start-Sleep -Seconds 10
(Invoke-WebRequest -Uri "http://localhost:8000/version" -UseBasicParsing).Content
```

### Endpoints API útiles (localhost:8000)

```
GET /version                  # Version actual
GET /mt5/status               # MT5 connection + balance + positions count
GET /mt5/positions            # Open positions
GET /market-state             # Price, trend, RSI, ATR, regime
GET /structure-status         # Scanner state + watching levels
GET /smc-state                # SMC multi-TF + zones
GET /auto-strategies?limit=10 # Last strategies
GET /performance              # WR, PnL, PF
GET /theme-editor             # Editor visual de paleta CSS (Thariq-style)
GET /what-if                  # What-if simulator sobre trade_archive REAL
GET /trade-archive-data       # JSON con todos los trades archivados (data del what-if)
GET /meta-optimization        # Dashboard meta-optimizer (pending_changes + audit trail)
GET /pending-changes          # JSON lista pending_changes (con filter ?status=X)
GET /pending-changes/{id}     # Detalle de un cambio + history + shadow stats
POST /pending-changes/{id}/approve  # Aplicar al live (skip shadow validation)
POST /pending-changes/{id}/revert   # Revertir cambio aplicado
POST /pending-changes/{id}/reject   # Marcar rechazado
POST /pending-changes/{id}/start-shadow  # Iniciar shadow validation
GET /meta-optimization-status # Resumen counts por status + active filters + baseline
```

### Query DB rápido

```python
import sqlite3, os
db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db)
# ...
```

### Git workflow (sin Co-Authored-By)

```bash
git add <files-explícitos>  # NO usar -A para evitar incluir test files
git commit -m "vX.Y.Z: descripción

Detalle multi-línea sin atribución a Claude."
git push origin main
```

---

## Modelos LLM

### Groq (free tier, cloud)

- `llama-3.3-70b-versatile` — news analysis, pre-planner
- `llama-3.1-8b-instant` — dashboard chat (latencia <500ms)

API keys hardcodeadas en `Config.GROQ_API_KEYS` con rotación. Override via `.env GROQ_API_KEY`.

### Ollama (local, free, GPU 8GB+)

- `qwen2.5:7b` — news pre-filter + signal audit + post-trade analyzer (rebautizado como `GEMMA_MODEL`)

URL: `http://localhost:11434`. Sin Ollama → AIdan usa solo Groq con degradación graceful.

---

## Versiones (últimas — changelog completo en `docs/historial_versiones.md`)

> ⚠️ El changelog largo (v3.6.3 → hoy, con el detalle de cada fix) vive en
> [`docs/historial_versiones.md`](docs/historial_versiones.md). Acá solo el resumen de lo reciente.
> **Al bumpear versión: la entrada larga va a ese archivo, acá solo una línea.**

| Version | Cambio | Estado |
|---|---|---|
| v3.59.0 | **P calibrada de m15 en FASE REGISTRO**: con 309 trades limpios la calibración de Platt PASÓ su gate por 1ra vez (m15 Brier 0.2214 < 0.230); params CONGELADOS en `confidence_calibration.py`, `add_auto_strategy` registra `calibrated_p` en `entry_context` — 0 efecto en decisiones. Leer con `score_calibrated_p_forward.py` (~10 sep) | **actual** |
| v3.58.1 | **Instrumentación (0 cambios de decisión)**: MFE/MAE reales por trade (trailing 1s → `mfe_pips`/`mae_pips` en el archive) + **shadow book** (`rejected_signals`, PRFS: outcome forward de lo que se BLOQUEA) + `signal_age_at_fill_min` + `efficiency_ratio` (Kaufman) en `entry_context` | vigente |
| v3.58.0 | **TCA real**: `log_fill()` existía DESCONECTADO (0 filas en meses) — ahora registra pedido vs fill + spread en cada entrada. Verificado: la cuenta es **Market Execution** ⇒ el `deviation` del request lo ignora el server | vigente |
| v3.57.2 | El **post-trade ve el razonamiento de la entrada** (`{retro_block}` + campo `missed_factor` con lista cerrada, como COLUMNA): cierra el lazo en el sentido que faltaba | vigente |
| v3.57.1 | La **leccion direccional deja de depender de Ollama** — se deriva tambien en `archive_trade` (los 2 paths coexisten, idempotente por `strategy_id`) | vigente |
| v3.57.0 | **Retrospectiva PRE-decision en shadow** (`RETRO_MODE`) + se **cablea** `adjust_setup_confidence` (existia desde v3.31.0 y no se llamaba de ningun lado) + loop `directional_lessons` + toggle `ENABLE_NEWS_TRACK` (default ON) | vigente |
| v3.56.0 | **Groq dio de baja los 2 modelos que usaba AIdan** (16-ago). Reemplazo medido: `gpt-oss-120b` / `gpt-oss-20b` + `reasoning_effort=low` + el health check ahora verifica que el modelo EXISTA | vigente |
| v3.55.0 | **Piso de ATR de m15 de 5 a 8** (`M15_ATR_FLOOR`, env): m15 pierde en chop de forma consistente (≤8p: n=90, WR 27,8%, −$75,59). Frena la sangría, no lo vuelve rentable | vigente |
| v3.54.1 | Baseline del D1 corregido: el titular corría con params default y una sola sesión. Re-medido con params vivos + sweep de las 4 sesiones (read-only) | vigente |
| v3.54.0 | **Track D = swing DIARIO (D1) en SHADOW** — 4to track, nace de 7 años de velas (H4 refutado, D1 PF neto 1,40). No toca `auto_strategies`. | vigente |
| v3.53.7 | Post-trade: el LLM copiaba la hoja de respuestas del template → etiquetas ahora en código, al LLM le queda la lección en texto | vigente |
| v3.53.6 | Una señal nunca ejecutada se mostraba como trade perdido (+ un test escribía en la DB de producción) | vigente |
| v3.53.5 | Kill switch del dashboard: 2 fórmulas de P&L + marcaba `closed` sin deal. UNIQUE INDEX en `trade_archive` | vigente |
| v3.53.4 | Orden LÍMITE apagada: 36/36 rechazadas por el broker, nunca operó | vigente |
| v3.53.3 | Doble conteo de la comisión de entrada en `sync_closed_positions` (tocaba `mt5_pnl`) | vigente |
| v3.53.2 | Guard del startup eval fallaba ABIERTO + medición del costo del break-even (no cuesta plata) | vigente |
| v3.53.1 | El cap-delete podía borrar la fila de una posición VIVA | vigente |
| v3.53.0 | 🔴 El `/kill` de Telegram no cerraba nada (código inalcanzable) + observabilidad del path de cierre | vigente |
| v3.52.1 | Amnesia del HWM: cada modify rechazado por el broker perdía el pico | vigente |
| v3.52.0 | h1 nunca tuvo break-even: el umbral estaba anclado a un TP inalcanzable | vigente |
| v3.51.x | news: más recorrido para los ganadores + guard de ejecución en `trade_archive` + limpieza del histórico fantasma | vigente |
| v3.50.x | Castigo por nivel flojo en m15 · bug que mataba SMC en silencio · loop de auditoría | vigente |
| v3.48.0 | Auditoría completa (`AUDIT_REPORT.md`) + Ola 1 de plomería: `setup_type`, backups, logs persistentes, WAL, 75 tests | vigente |
| v3.6.3 → v3.49.1 | 60+ versiones anteriores (tracks M15/H1, Position Manager, meta-optimizer, gate de significancia, dashboard) | ver historial |

## Estado actual del proyecto (11 May 2026)

### KPIs

- Balance demo: ~$899 (de $1000 inicial = -10.1% en ~4 semanas)
- WR histórico (165 trades archivo): 37.0%
- PnL histórico: **-$167.59**
- PF histórico: **0.55** (target >1.3)
- Frecuencia objetivo: 5-10 trades/día
- Frecuencia REAL reciente: **8 trades/día promedio** (11 May: 8 trades, 1 win = WR 12.5%)

### Diagnóstico estructural

4 problemas conocidos NO resueltos por filtros:
1. **Comisión = 87% pérdida neta**. Para break-even al WR 41% necesitamos avg win 6p (actualmente 4p).
2. **15-min expiry mata trades direccionalmente correctos**. Patrón observado múltiples veces.
3. **Groq mis-interpreta news con frecuencia**. Negaciones de central bank action.
4. **Confidence MAL CALIBRADA** (descubierto 11 May 2026 via what-if simulator). Ver sección dedicada abajo.

### Análisis 11 May 2026 — Calibración de confidence

**Descubrimiento via what-if simulator**: la confidence score (0-100) NO es predictor monotónico del win rate. Subir `min_confidence` empeora resultados porque elimina ganadores chiquitos sin filtrar perdedores.

**Tabla WR por bucket de confidence (165 trades histórico)**:

| Conf | Trades | WR | PnL |
|---|---|---|---|
| 30-39 | 5 | 40% | -$2.70 |
| **40-49** | **7** | **43%** | **+$8.60** ✓ |
| 50-59 | 22 | 36% | -$32.21 |
| 60-64 | 37 | 38% | -$12.56 |
| 65-69 | 17 | 35% | -$36.06 |
| **70-74** | **32** | **34%** | **-$60.12** ✗ |
| 75-79 | 16 | 44% | +$1.00 |
| 80-84 | 11 | 36% | -$1.50 |
| 85-89 | 8 | 50% | -$11.96 |
| **90-94** | **6** | **0%** | **-$23.38** ✗✗ |
| 95-100 | 4 | 50% | +$3.30 |

**Hallazgos clave**:
- Conf **90-94: 0% WR** → las más "confiadas" son las peores
- Conf **40-49: 43% WR** → mejor que muchos buckets altos
- Conf **70-74: -$60.12** (32 trades) → el bucket más perdedor en absoluto
- **NO existe correlación monotónica conf→WR**

**Cumulative "si filtro min_conf >= X"**:

| min_conf | n | WR | PnL |
|---|---|---|---|
| ≥0 | 165 | 37.0% | -$167.59 (baseline) |
| ≥50 | 153 | 36.6% | -$173.49 (peor) |
| ≥60 | 131 | 36.6% | -$141.28 |
| ≥70 | 77 | 36.4% | -$92.66 |
| ≥75 | 45 | 37.8% | -$32.54 |
| ≥85 | 18 | 33.3% | -$32.04 |

**Subir el piso no ayuda**. AIdan ya tiene `conf_ceiling 80` desde v3.11 (anti-predictive) — esto valida que el TECHO sí aporta, no el piso.

**Root cause (hipótesis)**: la fórmula `dynamic_conf` (technical.py:451) suma puntos de factores redundantes (MA trend + HTF + RSI + momentum miden lo mismo). Cuando todos alinean = conf 90+ = **exhaustion entry** (mercado ya se movió, por revertir). Es por eso que existe SIM A (block fully-aligned).

**Análisis por session (165 trades)**:

| Session | Trades | WR | PnL |
|---|---|---|---|
| **london** | 7 | 28.6% | +$2.40 ✓ (muestra inútil) |
| late_ny | 55 | 36.4% | -$50.89 |
| ny | 68 | 38.2% | -$61.40 |
| overlap | 33 | 39.4% | -$44.70 |
| off | 2 | 0% | -$13.00 |

**Lectura**: TODAS las sessions pierden plata (excepto London con 7 trades = ruido). El problema no es de session específica — es estructural.

### Opciones para corregir confidence (post-Fase 1)

1. **Opción A — Bucket-based blocking (rápido, riesgo bajo)**. Block conf 70-74 y 85-94 explícitamente en `blocked_setups`. Allow conf 40-49. Tiempo: 1-2h. Riesgo: overfitting muestra chica.

2. **Opción B — Empirical confidence (medio plazo)**. Reemplazar fórmula por WR real histórico del setup_type. Ya existe `setup_win_rates` cached parcialmente. Tiempo: 2-3 días.

3. **Opción C — Logistic regression / ML proper (largo plazo)**. Entrenar modelo con features del trade_archive → P(win) calibrada. Requiere muestra 500+. Tiempo: 2-3 días + data.

4. **Opción D — A/B test paralelo (validación)**. M5 actual + M5-bucket-filter en paralelo 30 días. Decisión empírica.

### Restricción real: frecuencia de trades vs target

**Target original (CLAUDE.md viejo)**: 200-300 trades para validación robusta.

**Realidad observada (11 May)**: ~8 trades/día. Para 200-300 trades necesitamos **25-37 días más** (final de mayo / mediados de junio). NO vamos a tener muestra robusta antes de eso. Decisiones intermedias serán siempre **provisorias**.

**Implicancia**: cualquier cambio estructural (Opciones A-D arriba) debe esperar a ese horizonte. Fixes surgical (block bucket específico con muestra >20) son aceptables con caveats documentados.

### Próximo checkpoint

**Viernes 12 Jun 2026** — agenda:
1. **⏰ DECISIÓN PRINCIPAL: activar cooldown 5min post-pérdida.** Único hallazgo que pasó el gate adversarial (n=74, WR 24% vs 38%, p=0.010, sostenido 4/5 quincenas, frontera nítida a ~5min; #611 del día CPI = el patrón exacto). Re-correr `tools/measure_entry_suspects.py` (segundos) para confirmar sobre la data más nueva → si sostiene, activarlo como EL próximo cambio (1 a la vez). Detalle completo en NOTAS.
2. Primeros días del experimento PM re-baselineado (v3.40.11): ¿los trades extendidos más allá del expiry (comportamiento NUEVO) ayudan o duelen? Ver `position_manager_log` (CLOSE_MAXHOLD/EXTEND) + avg_win. **Primera evidencia viva (11 Jun, positiva): #621 extendido 118min → profit-lock aseguró +$4.52 a 84% del TP; 6 PROTECTs cortaron sangrías; #627 TP completo.** Ver bloque "Obs 11 Jun" en NOTAS.
2b. De "Obs 11 Jun": decidir si la edad/expiry debería correr desde el FILL (no la señal — #625 perdió 27min pendiente como limit) → requeriría columna `mt5_filled_at`; y tener presente el slippage de SL en spikes (11p en #625) para sizing/cuenta real.
3. Calendar shadow: ¿FF se destrabó (429)? Revisar `calendar_shadow_log` si hay filas.
4. En cola de siempre: ATR ceiling + params overfit; data limpia acumulada (contador desde 5 Jun, sin contaminación m15/h1 desde v3.40.11).

---

## Plan triple-track (decidido 7-8 May 2026)

### Track A — M5 (mantenimiento)

- Continúa la línea v3.18.x con la versión actual.
- Solo fixes surgical, sin cambios estructurales.
- Sigue usando trigger_types: `news`, `structure`, `smc`, `pre_planned`, `calendar`.

## Roadmap aprobado 8 May 2026 (multi-cuenta / multi-moneda / dinero real)

Plan completo en `~/.claude/plans/sorted-meandering-pizza.md`. Resumen:

**Fase 1 (próximas 3-4 semanas)**: validación demo. Dejar M5+M15+H1 corriendo sin tocar arquitectura. Acumular 30+ trades por track. Decisión basada en PF + frecuencia + comisión-drag.

**Fase 2 (1-3 meses post Fase 1)**: cuenta real con TODOS los tracks que pasen PF >1.2. Si los 3 califican → operar los 3 (M5 explosivos, M15 sostenidos, H1 macro = patrones complementarios, NO competidores). Lote 0.01 por track. Risk: max 4 posiciones total, lote dividido entre tracks rentables.

**Fase 3 (6+ meses post real)**: escalar — multi-cuenta (5-7 días refactor) o multi-moneda (2-3 semanas + research por par) o profesionalizar como sistema único.

**Bloqueos actuales**: PF 0.48 (target >1.3), comisión 87% del drag M5, hardcoding EUR/USD en 104 sitios. NO escalar hasta demostrar rentabilidad en demo.

### Track C — H1 (experimental) — IMPLEMENTADO v3.20.0 (8 May 2026)

**Profile H1**:
- SL: 40p, TP: 100p, expiry: 180min (3h)
- min_confidence: 60
- ATR floor: 10p
- Frecuencia esperada: 1-2 trades/día

**trigger_type**: `h1_structure`

**Por qué H1 también**:
- Comisión 0.7p / avg win esperado 30p = **2% drag** (vs 17% M5)
- Cuenta demo, sin riesgo real, stats segregadas
- Más data > menos data para decidir el mejor timeframe

**Loop H1**: cada 5 min (`H1_SCAN_INTERVAL = 300`). H1 candles cambian cada hora.

**UI elementos H1**:
- Botón filtro `🌐 H1 (beta)` violeta
- Badge violeta `🌐 H1 STRUCT` en cards
- Chip header `🌐 H1 NW/NL · X act`
- Tercera card en panel comparativo "Triple Track"

### Track B — M15 (experimental, paralelo) — IMPLEMENTADO v3.19.0 (7 May 2026)

**Implementación**:

| Día | Componente | Archivos |
|---|---|---|
| 1 | `TechnicalAnalyzerM15` subclass + test standalone | `src/analyzer/technical_m15.py`, `tools/test_m15_feed.py` |
| 2 | Loop M15 paralelo en analyzer (cada 60s) | `AIdan_TodoEnUno.py` |
| 3 | UI: filtro `M15`, badge dorado en cards, chip stats | `dashboard_multi_theme.html` |
| 4 | Endpoint `/strategy-performance-by-track` + panel comparativo | `src/admin/main.py`, `src/common/db.py` |
| 5 | Verdict robusto + banner alert "M15 supera M5" | `dashboard_multi_theme.html` |

**Profile M15** (constante en `technical_m15.py:M15_PROFILE`):
- SL: 15p, TP: 60p, expiry: 45min
- min_confidence: 60
- Frecuencia: ~1-3 trades/día (M15 candles cambian cada 15min)

**trigger_type**: `m15_structure` (futuro `m15_smc` cuando se agregue)

**Filtros M15** (subset del M5):
- ATR floor 5p (vs M5 2.5p, M15 escala 3x)
- Counter-both (HTF + M5 ambos contrarios → block)
- Conf ceiling 80
- Anti-spam (no opposite activa)
- SIN late breakout (escala distinta), SIN hour gate (ya removido v3.17)

**Criterios de decisión** (en `loadTrackComparison` UI):
- Bajo 10 trades M15: "esperando data"
- 10-14 trades: comparativa preliminar, no decidir
- 15+ trades:
  - **M15 SIGNIFICATIVAMENTE mejor**: PF > 1.0 + PnL positivo + +$20 sobre M5 → banner "considerar migracion"
  - **M15 mejor moderado**: PF > A_PF * 1.3 + PF >= 0.9
  - **M5 mejor**: A_PF > B_PF * 1.3 + A_PF >= 0.9
  - **Empate**: mantener ambos

**UI elementos**:
- Botón filtro `⏰ M15 (beta)` dorado en barra de filtros del tab Estrategias
- Cards M15 con badge dorado `⏰ M15 STRUCT` distintivo
- Chip header `⏰ M15 NW/NL · X act` (auto-hide si 0 trades)
- Panel "Comparativa Dual-Track" con 2 cards lado a lado
- Banner dorado destacado cuando M15 supera M5 significativamente

**Riesgo al M5**: cero. Track B vive en try/except aislado. Si M15 falla, M5 sigue normal.

**Próximos pasos abiertos**:
- M15_PROFILE en DB en lugar de constante (permite ajuste sin rebuild)
- Cuenta demo MT5 separada para Track B (aislamiento total de capital)
- Más trigger types M15 (`m15_smc`)

---

## Glosario de patrones observados

> 🔄 **Plan de mejora continua del "cerebro"**: `docs/mejora_continua.md` — el loop semanal (medir → gate → shadow → activar UNO → re-medir), el backlog de ideas rankeado por evidencia, el calendario de checkpoints hasta el 17 Jul y los criterios de "ganar". Acordado 12 Jun tras el veredicto "entra mal, no tarde". **Revisar y actualizar en cada checkpoint.**

> 📋 **Playbook de regímenes de mercado**: `docs/market_playbook.md` — registro vivo de los tipos de mercado (lateral muerto, tendencia alineada, ranging/chop, conflicto M5-vs-HTF, falling knife, news stale, volatilidad extrema) y cómo debería accionar AIdan en cada uno. Marca evidencia vs hipótesis-a-verificar. Actualizar en cada checkpoint.

- **Expiry-loss**: trade direccionalmente correcto que cierra por timeout antes de hit TP. Frecuente en M5 con expiry 15min.
- **Catch-the-falling-knife**: AIdan ve un breakdown como "structure breakout" y compra el bottom. SL hit en <2 min.
- **Counter-HTF**: dirección contraria a HTF bias (H1+). Históricamente -EV.
- **Counter-both**: dirección contraria a M5 trend Y HTF bias. Bloqueado.
- **SIM A**: trade fully-aligned (M5+HTF+regime todos en una dirección). Bloqueado por exhaustion entry.
- **Bypass**: news con impact ≥55 puede pasar conf threshold de 30 si NO es counter-HTF.
- **Confidence inversion** (11 May 2026): patrón observado donde conf alta (90+) tiene WR inferior a conf media (40-49). Causa: factores redundantes en `dynamic_conf` se suman → alineación total = exhaustion. Mismo principio que SIM A pero medido numericamente.

---

## Tools disponibles en `tools/`

| Script | Propósito |
|---|---|
| `backtest_h1_m15.py` | Backtest estructural-only sobre velas MT5 históricas (re-corre `detect_structure_signals()`, simula SL/TP/expiry). Solo `structure`. Requiere MT5. |
| `backtest_h4_d1.py` | Paso 0 del track D (13-ago). Igual que el anterior pero H4/D1, en variantes `naive` y `scaled`. **Resultado: H4 refutado (−0,98p/trade, n=451) · D1 positivo. Escalar las constantes por ATR EMPEORA (1,40→1,02).** **v2 (16-ago): `--params live` usa los params reales de `optimizer_params` (el titular usaba los default) y `--session sweep` corre las 4 sesiones porque el paso 7 de `dynamic_conf` lee el reloj — con eso el baseline del D1 pasó a 186-227 señales / +10,8 a +12,7p post-swap / PF 1,25-1,30, positivo en las 4.** Trae un guard que corta si la tabla de sesiones de producción cambia. Requiere MT5. |
| `score_d1_shadow.py` | Scorer FORWARD del D1 en shadow: excursión favorable Y adversa + close al horizonte (3/5/10 velas), **sin re-simular SL/TP**. Descuenta comisión y swap. Ancla en `d1_candle_ts`, no en `created_at`. `--dry-run`. Requiere MT5. |
| `measure_entry_suspects.py` | READ-ONLY sobre deals del broker (timestamps exactos): (A) re-entrada ≤2/5/10/15min tras pérdida, (B) htf_bias vs deriva real 2h previa. Pasa por `verify_finding`. Re-correr cada checkpoint. |
| `measure_dist_to_level.py` | READ-ONLY: ¿la distancia precio↔nivel al fill separa ganar/perder? **La celda `≤0.5 ATR` da 65% WR p=0.006 pero n<25** (nunca pasó el gate; se degradó el 5-ago). No necesita MT5. |
| `measure_news_llm_error.py` | READ-ONLY: cuánto se equivoca el LLM de news, aislado del trading (sobre `alerts`, 753 direccionales). Titular = discriminación P(subió\|CALL) − P(subió\|PUT). **Resultado 24-jul: NO discrimina (edge −1pp, p=0.92) y es ANTI-SKILL (hit 53% vs drift 63%).** Requiere MT5. |
| `measure_post_trade_value.py` | READ-ONLY: ¿el post-trade del LLM sirve? **Resultado 11-ago: no juzga, etiqueta** — `entry_quality='good'` en el 93% de los PERDEDORES, `timing_assessment` constante en el 100%, y el único que separa es tautológico. No necesita MT5. |
| `measure_be_cost.py` | READ-ONLY: cuánto cuesta el break-even del trailing (`position_manager_log` ⋈ `trade_archive`, 4 roles). **Resultado 10-ago: los cortados por el BE terminan en +$2,41 ⇒ no cuesta plata; el 74% nunca arma el BE y ahí vive el 100% de la pérdida ⇒ el lever es la ENTRADA.** Mide la mitad visible de la balanza, nunca un neto. |
| `calibrate_confidence.py` | READ-ONLY: ¿la calibración de Platt vuelve usable la confianza? Split cronológico, Brier held-out, gate pre-declarado <0,230. **5-ago: NO PASA. 20-ago (309 limpios): m15_structure PASA por 1ra vez (0,2214)** ⇒ fase registro v3.59.0. `conf/100` crudo sigue siendo mucho peor que la constante ⇒ **nunca usar la confianza cruda como probabilidad** (p.ej. sizing). |
| `score_calibrated_p_forward.py` | Scorer READ-ONLY de la fase registro v3.59.0: Brier forward de `calibrated_p` (fit congelado 20-ago) vs constante train, con gate pre-declarado (n>=40; a n>=60 sin pasar ⇒ borrar el módulo). Trae tripwire de hook muerto (señal m15 post-deploy sin registro = buscar `calibrated_p no registrada` en el log). No requiere MT5. |
| `audit_code_patterns.py` | Auditoría READ-ONLY de los 7 patrones de bug que ya hicieron daño acá (undefined names, `except` que tragan, ramas mudas de `order_send`, código inalcanzable, umbrales atados al % del TP, DELETE sin guard, estado incoherente). **Lo que lo hace usable es el BASELINE**: solo reporta lo NUEVO. Exit 0 = nada nuevo. Corre sábados vía `aidan-auditoria-semanal`. |
| `score_retrospective_shadow.py` | Scorer READ-ONLY de la retrospectiva pre-decision (v3.57.0). Compara `contrarian` vs el resto con Wilson, y evalua el **gate pre-declarado de 4 condiciones** (n>=25 · WR peor · CI que no cruza · PnL/trade peor). Tambien reporta si el loop de `directional_lessons` se esta CONSULTANDO — 0 consultas = mecanismo escrito y desconectado, el sintoma clasico de este proyecto. |
| `measure_tca.py` | TCA READ-ONLY (v3.58.0): mediana/p90 de slippage y spread desde `slippage_log` + breakdown por hora AR. Umbral pre-declarado: mediana > 0,7p = la ejecucion es un problema material. 0 filas + trades nuevos = el hook de `log_fill` murio (buscar WARNING en aidan.log). |
| `score_rejected_signals.py` | SHADOW BOOK scorer (v3.58.2, PRFS): completa el outcome forward de `rejected_signals` (SU tabla, lo unico que escribe) con velas M5 sin re-simular SL/TP, y evalua el criterio pre-declarado — atr_floor por movimiento ABSOLUTO vs los 7,8p de un ganador; counter_both/active_opposite por save-to-miss (< 1:1 con n>=25 = el filtro bloquea ganadores). **Regla de shadow: traerlo sin que el user lo pida.** Requiere MT5. `--dry-run`. |
| `backfill_directional_lessons.py` | Siembra `directional_lessons` desde `trade_archive` con el MISMO criterio del path vivo, para que la retrospectiva no arranque ciega (19 lecciones desde el 20-jun). **Dry-run por default.** Limite declarado: el archive no guarda MFE, usa `max(0,pips)` como cota inferior => puede emitir falsos positivos de "gestion" etiquetados como "direccion"; se distinguen por el prefijo `[backfill]` en `evidence`. |
| `measure_news_latency.py` | READ-ONLY: ¿news llega tarde por construccion? Nace del research del 19-ago (993 eventos USD 2022-2025: la deriva post-release esta **contenida en las velas +1..+5**; desde la +6 los T dan 0,14-0,69, y ~80% del movimiento se completa en **3 minutos**). **Resultado sobre 871 alerts: mediana 8,9 min, solo 7,7% dentro de los 3 min, y el LLM tarda 0,2 min ⇒ el cuello de botella es el FEED, no el analisis** — un prompt no puede arreglarlo (consistente con que v3.47.0 no moviera el edge). El corte `<=3min` da 60,5% WR vs 51,3% pero **CI [45,6-73,6] cruza el baseline ⇒ NO pasa el gate**, y corre sobre `alert_result`, no broker-truth. *Ojo metodologico: la 1ra version reportaba 398 min por sumar `published_at` en UTC con `fetched_at` en hora AR — el script trae ahora un control de sanidad que falla si el offset se rompe.* |
| `nightly_analyst.py` | LLM analyst on-demand desde el dashboard (▶ Run analyst). Opus → Groq → Ollama. Propone cambios JSON con min-sample + guard-rails; arranca shadow validation vía auto_applier. |
| `backtest_parallel.py` · `backtest_weekly.py` | Backtest paralelo de combinaciones de filtros sobre `trade_archive` + wrapper semanal con aviso por Telegram. |
| `clean_test_rows_v3536.py` | Limpieza de las filas que un TEST escribió en la DB de producción (incidente `#999`). **Dry-run por default.** Criterio = `strategy_id` sobre el máximo jamás asignado (NO «huérfana»), aborta si el id aparece en `aidan.log`. Backup + CSV + rollback. No toca `trade_archive`. |
| `test_m15_atr_floor_v3550.py` | Tests de la perilla `M15_ATR_FLOOR`: que el default siga siendo 5.0 (rebuild sin tocar `.env` = sin cambio de comportamiento), que la env var pise, y **test de mutación** que extrae la condición REAL del gate desde `AIdan_TodoEnUno.py` y la evalúa — si alguien vuelve a hardcodear el 5.0, falla. No toca DB ni MT5. |
| `test_d1_analyzer_v3540.py` | 34 tests del track D1: que el bloque del loop NO contenga `add_auto_strategy`/`_try_mt5_execute`, que ninguna variable quede sin prefijo `_d1`, el guard que rechaza velas no-diarias, fail-closed por fuente, `created_at` en hora AR, + test de mutación. |
| `test_prod_write_guards_v3536.py` · `test_skip_status_v3536.py` | Tests de v3.53.6: que los tests no escriban en la DB de producción; y que `auto_evaluate_strategy` no pise el status de una señal skipeada (+ helper `strategy_was_executed`, tests de mutación). |
| `what_if_simulator.html` | Simulador retroactivo sobre `trade_archive` REAL: sliders de conf/ATR + filtros, recomputa WR/PF/PnL con delta vs baseline, equity curve, heatmap. Endpoint `/what-if`. |
| `meta_optimization.html` · `dashboard_theme_editor.html` | Dashboard del meta-optimizer (pending_changes, shadow PF, audit trail) y editor visual de la paleta CSS. Endpoints `/meta-optimization` y `/theme-editor`. |
| `deep_analysis.py` · `analyze_trending.py` · `ml_feature_analysis.py` | Análisis exploratorio de `trade_archive`: patrones/correlaciones, % de tiempo en tendencia vs lateral, feature importance. |
| `test_m15_feed.py` · `benchmark_llm_models.py` · `aidan_watchdog.py` | Test del feed M15 · benchmark de modelos Ollama · watchdog (**no se usa**: si AIdan no corre, lo cerró el user). |

> Los detalles metodológicos de cada medidor (fórmulas, env vars, límites declarados, por qué se
> eligió cada métrica) están en el **docstring de cada script** — se leen al abrirlo, no cuestan
> contexto en cada sesión.

### Backtest H1+M15 results (30 días, 27 Mar → 8 May 2026)

**M15** (693 signals, sin filtros completos):
- WR 49.2%, PF 1.10, +189.6p, avg 0.27p/trade
- Setup ganadores: `trend_continuation_bull` (+236p), `trend_continuation_bear` (+82p)
- Setup perdedores: `momentum_expansion` (-52p), `breakdown_support` (-71p)

**H1** (212 signals):
- WR 50.5%, PF 1.17, +156.2p, avg **0.74p/trade** (mejor avg)
- Setup ganador estrella: `breakout_resistance` WR 72% +209p
- Setup perdedores: `breakdown_support` (-50p), `momentum_expansion` (-15p)

**Lecturas honestas**:
- 99% de trades terminan en expiry (SL/TP raramente hit) → thresholds holgados vs ATR real
- Ambos tracks tienen edge MARGINAL estructural sin filtros adicionales (PF 1.1 ≈ break-even con fricción)
- H1 confirma tesis de comisión drag bajo: avg 0.74p/trade vs M15 0.27p
- Backtest **infla metricas 20-30%** vs real → PF real estimado ~0.85-0.95 (NO rentable solo)
- Necesita capas adicionales (htf_bias, anti-spam, LLM auditor) que demo SÍ tiene

### Caveats del backtest H1+M15

1. Solo trigger `structure` (sin news ~30% de signals reales)
2. Sin htf_bias derivado de SMC live (filtro counter-HTF inactivo)
3. AutoTuner params actuales sobre data vieja (mild data leakage)
4. Sin spread variable, slippage, latency execution
5. Backtest infla metricas vs producción real con fricción

---

## Cosas que NO se deben hacer

1. ❌ Modificar código sin aprobación explícita del user.
2. ❌ Hacer commits con `Co-Authored-By: Claude`.
3. ❌ Agregar filtros con muestra <6 trades de evidencia.
4. ❌ Tocar `mt5_config` (kill switch, risk_percent) sin permiso.
5. ❌ Borrar trade_archive, learning_insights, o cualquier histórico. *(Excepción única, 8 Ago 2026, con pedido explícito del user: las 19 filas que NUNCA fueron trades — verificadas contra el historial de deals del broker, con backup + CSV de respaldo, vía `tools/clean_phantom_archive.py`. Borrar data que sí llegó al broker sigue prohibido; el script mismo se niega a hacerlo.)*
6. ❌ Modificar `Config.GROQ_API_KEYS` salvo si user pide rotación explícita.
7. ❌ Llamar a APIs reales con dinero. Demo only.
8. ❌ Ejecutar simulaciones que escriban a la DB de producción.
9. ❌ Cambiar el modelo de LLM por uno pago sin permiso.
10. ❌ Hacer deploys (rebuild + commit) sin test previo de imports.
11. ❌ **NO tocar `dynamic_conf` formula con muestra <300 trades** (11 May 2026). Confidence está mal calibrada pero arreglarla con muestra chica = overfitting garantizado. Esperar Fase 1 completa.

## Cosas que SÍ son apropiadas hacer proactivamente

1. ✅ Diagnosticar trades específicos por id si user pregunta.
2. ✅ Reportar estado MT5 + version + posiciones cuando user pide "status".
3. ✅ Sugerir simulaciones standalone en `tools/` para validar antes de change.
4. ✅ Pedir clarification con formato Plan/Razón/Pros/Contras/Opinión.
5. ✅ Loggear tu análisis en español, código en inglés.
6. ✅ Verificar que AIdan arranca sin error tras rebuild (capture stderr).
7. ✅ Sanity import check antes de rebuild: `python -c "from src.common.config import Config; print(Config.VERSION)"`.

---

## Para levantar contexto rápido en una sesión nueva

```bash
# 1. Verificar AIdan corriendo y version
curl -s http://localhost:8000/version

# 2. Estado MT5 + daily PnL
curl -s http://localhost:8000/mt5/status

# 3. Últimas estrategias
curl -s http://localhost:8000/auto-strategies?limit=5

# 4. Performance histórico
curl -s http://localhost:8000/performance

# 5. Leer este CLAUDE.md
cat F:/AIdan/CLAUDE.md
```

---

## Meta-Optimization (v3.31.0)

Sistema de mejora continua autonomo implementado 14 May 2026. Plan completo en `~/.claude/plans/sorted-meandering-pizza.md`.

### Arquitectura

```
LLM Analyst (19:00 AR cron)  →  pending_changes (proposed)
        ↓                              ↓
Shadow Runner (auto)         →  shadow_strategies + shadow_trades
        ↓                              ↓
Auto-Applier (cada 10min)    →  pending_changes (validated → applied)
        ↓                              ↓
Monitor (cada 50 trades)     →  Auto-revert si PF cae >10%
```

### Componentes

- **`tools/nightly_analyst.py`**: ejecutable manualmente desde dashboard (botón ▶ Run analyst). LLM fallback chain: Opus 4.7 → Groq llama-3.3-70b → deepseek-r1:14b → deepseek-r1:7b → qwen2.5:7b. Genera input JSON (stats 24h/7d/30d por buckets conf/trigger/hora/session/htf), invoca LLM, parsea output JSON, persiste como pending_changes con `source='nightly_<kind>_<model>'`. v3.31.2: removida la Task Scheduler diaria — ahora 100% on-demand.
- **`src/optimizer/shadow_runner.py`**: cuando se crea auto_strategy, evalua signal contra todos los pending_changes con status='shadow_validating'. Crea shadow_strategies con decision=taken/skipped. Daemon paralelo simula outcomes con sim_engine.py usando candles posteriores.
- **`src/optimizer/sim_engine.py`**: motor de simulacion SL/TP/expiry compartido (refactor de backtest_h1_m15.py).
- **`src/optimizer/change_manager.py`**: apply/revert engine con guard-rails. Funciones: `apply_change()`, `revert_change()`, `is_signal_blocked_by_meta_filters()`, `get_confidence_adjustment_for_signal()`.
- **`src/optimizer/auto_applier.py`**: daemon. Promueve shadow_validating → validated (si shadow PF > baseline + 0.15 y muestra >= 30 trades). Aplica validated → applied (max 1 a la vez). Monitorea applied; auto-revert si PF live cae >10% en 50 trades.

### Tablas nuevas en DB

- `pending_changes`: cola de cambios. Status: proposed → shadow_validating → validated → applied → reverted | rejected.
- `shadow_strategies`: signals simulados con config alternativa (decision=taken/skipped).
- `shadow_trades`: outcomes simulados.
- `change_history`: audit trail inmutable.
- `active_meta_filters`: filtros activos consumidos por scanner en cada signal.

### Change types soportados (lista cerrada)

`block_setup_type`, `block_conf_bucket`, `block_hour_utc`, `block_session`, `block_pattern`, `tune_optimizer_param`, `adjust_setup_confidence`, `adjust_min_confidence_per_track`.

### Guard-rails hardcoded (NO se pueden tocar)

`mt5_config`, `risk_percent`, `max_lot`, `daily_loss_limit`, `kill_switch`, MT5 credentials, Groq API keys, `dynamic_conf` formula.

### Thresholds del auto-applier

- `SHADOW_MIN_TRADES=30`: minimo shadow trades antes de validar
- `SHADOW_MIN_PF_DELTA=0.15`: shadow PF debe superar baseline + delta
- `VALIDATION_DROP_PCT=0.10`: live PF cayendo >10% post-apply → auto-revert
- `MONITOR_INTERVAL_TRADES=50`: chequeo cada N trades post-apply
- `COOLDOWN_DAYS_AFTER_REVERT=7`: pausa tras revert

### Telegram alerts (formato breve)

```
🌙 Analyst 19:00 — 14 May
Modelo: opus / Trades 24h: 9 (WR 33%)
Propuesta: block conf bucket 70-79
Estado: shadow validation 7-14d

✅ Cambio aplicado
block_conf_bucket {"bucket_lo":70,"bucket_hi":79}
Shadow PF +0.18 vs baseline 0.55

⚠️ Cambio revertido
block_hour_utc {"hours":[16,19]}
PF cayó -12% en 50 trades post-apply
```

NO se reporta costo de tokens en Telegram (solo log local).

### Setup operacional

**v3.31.2**: removida la Task Scheduler. Ahora se ejecuta **manualmente** desde el dashboard:

1. Abrir `http://localhost:8000/meta-optimization` (botón 🤖 en header del dashboard)
2. Seleccionar modelo (Auto-detect / Force Opus / Force Groq / Force Ollama)
3. Click **▶ Run analyst** — corre en background, status polling cada 3s
4. Al terminar (1-5 min típico) muestra:
   - Cambios propuestos (lista con reasoning)
   - Log tail expandible
   - Resultado: success / timeout / error

**Endpoints**:
- `POST /nightly-analyst/run?model=X` — dispara análisis manual
- `GET /nightly-analyst/status` — estado actual (running, last_result, last_changes)

### Riesgos documentados

1. **Muestra chica**: 12 trades/día → shadow 7-14d = 80-160 trades. Min sample per change tipo restringe over-claiming.
2. **Concept drift**: cambios aplicados se re-evaluan implicitamente en monitor (PF live actual).
3. **Cascade failure**: max 1 cambio applied a la vez + cooldown 7d post-revert.
4. **LLM alucina**: schema validation + lista cerrada change_types + guard-rails + min_sample requirements.
5. **Costo runaway Opus**: max 1 sesion/dia, fallback a Groq/local si no disponible.

### Critério de éxito (4 semanas post-deploy)

- ≥ 5 cambios propuestos por LLM
- ≥ 2 validados via shadow
- ≥ 1 aplicado al live
- PF acumulado ≥ 0.70 (vs baseline 0.55)
- 0 violaciones de guard-rails
- ≤ 2 cambios revertidos (significaria que validation funciona)

---

## Estado del repo (ordenado 11 Ago 2026)

- **`CLAUDE.md` (este archivo) es la fuente de verdad.** El `README.md` es la referencia pública
  (qué es, cómo funciona, arquitectura, build, tests, metodología) y **apunta acá** para todo lo que
  cambia seguido. Tenía 1.252 líneas con "v3.21.0" en el título y 840 de changelog duplicado; se
  reescribió a ~200. **No volver a poner el changelog en el README** — vive en la tabla de versiones
  de acá y en git.
- **`.env.example` documenta las perillas reversibles** (los `MODE=shadow/log/active`, los caps por
  env que permiten revertir sin rebuild). Si se agrega una perilla nueva, sumarla ahí.
- **`static/` solo tiene lo que se usa**: `aidan_icon.ico` (spec + monolito) y `vaultboy_avatar.png`
  (notificación del dashboard). El `.spec` empaqueta la carpeta ENTERA ⇒ cualquier archivo que se
  deje ahí viaja dentro del exe (los 5 muertos que se borraron pesaban ~4 MB; el exe pasó de 105,0 a
  96,4 MB).
- **Artefactos generados, fuera de git**: `AIdan_Portable/` (lo recrea `crear_paquete.bat`),
  `trade_archive_enriched.csv` y `trade_archive_ml.csv` (los regeneran las tools de ML). Siguen en
  disco, solo destrackeados.
- **NO se tocó el pipeline de ML** (`compare_models`, `train_*`, `prep_ml_dataset`,
  `revalidate_predictor`, `enrich_archive_features`): la línea está refutada a n=276 pero la
  re-evaluación a 300-500 trades sigue agendada y esos scripts son lo que la haría posible.

---

## Reglas de mantenimiento de este archivo

**IMPORTANTE**: con cada cambio significativo (nueva versión, feature, herramienta, hallazgo de backtest), CLAUDE.md DEBE actualizarse. Antes de cada sesión nueva con asistentes IA, leer este archivo completo para mantener contexto. La última actualización siempre debe coincidir con la versión activa en `Config.APP_VERSION`.

> 💰 **REGLA DE TAMAÑO (13 Ago 2026, para bajar el costo por sesión).** Este archivo se carga
> ENTERO en cada sesión de cada asistente ⇒ cada KB acá se paga en TODAS las sesiones futuras.
> El 13-ago pasó de 292 KB (~75k tokens) a ~90 KB (~23k) bajando el histórico cerrado a
> `docs/`. **Mantenerlo debajo de ~100 KB.** Reglas concretas:
> - **Versiones**: la entrada larga va a [`docs/historial_versiones.md`](docs/historial_versiones.md);
>   acá **UNA línea** en la tabla corta. No volver a escribir párrafos de 5 KB en la tabla.
> - **NOTAS**: cuando un hilo se cierra (✅), **moverlo** a
>   [`docs/historial_notas.md`](docs/historial_notas.md), no dejarlo tachado acá.
> - **"Última actualización"**: máximo ~5 líneas. El razonamiento largo va al historial.
> - Si el archivo pasa los 100 KB, hacer una pasada de bajada antes de seguir agregando.

**Checklist tras cada cambio**:
- ✅ Bumpear `APP_VERSION` en `src/common/config.py`
- ✅ Actualizar tabla de versiones en CLAUDE.md (**una línea**; el detalle a `docs/historial_versiones.md`)
- ✅ Bajar a `docs/historial_notas.md` los hilos que se cerraron en la sesión
- ✅ Si agregaste tool nuevo → línea en sección Tools
- ✅ Si cambió diagnóstico/KPI → actualizar "Estado actual"
- ✅ Sanity check imports antes de rebuild
- ✅ Rebuild AIdan.exe
- ✅ Verificar `/version` en endpoint
- ✅ Commit (sin Co-Authored-By)
- ✅ Push a origin/main
- ✅ Actualizar línea final "Última actualización"

---

## Backlog de ideas para probar (ordenadas por esfuerzo/impacto)

Ideas de mejora identificadas el 22 May durante el refactor mayor.
Cada una NO probada todavía. Listadas para no perderlas y atacar en orden:

### Quick wins (horas → 1 día)

1. ~~**Random Forest / XGBoost** (en vez de logistic regression)~~ ✅ RESUELTO (31 May, workflow ml-model-bench)
   - Hipótesis: "capaz el problema es no-lineal". **REFUTADA.**
   - 4 modelos (LR/RF/XGBoost/HistGB) sobre 276 trades, split cronológico 80/20, verificación adversarial.
   - **Ningún modelo supera AUC 0.60 robusto.** Los 3 que tocaron ~0.60 en holdout (XGBoost 0.600, structure 0.607, news 0.625) fueron REFUTADOS por CV/multi-seed/permutation test → AUC real 0.44-0.48 (debajo de azar). Train AUC 0.68-0.99 vs CV ~0.44-0.54 = overfit textbook.
   - Los árboles NO le ganan a LR — overfit más (RF train 0.91, gap 0.36). No es problema de linealidad.
   - **HALLAZGO CLAVE (3 agentes independientes): `confidence` SOLA da AUC ~0.59, MAYOR que los modelos ML completos.** El feature engineering no es el cuello de botella — a n=276 no hay señal aprendible más allá de lo que confidence ya captura.

3. ~~**Modelos separados POR trigger_type**~~ ✅ RESUELTO (31 May, mismo workflow)
   - Hipótesis: "news/structure/smc tienen patrones distintos". **No verificable a este n.**
   - Por-trigger (structure 112, m15 56, news 50, h1 30): test sets de 6-23 filas → AUC inútil. Todos overfit (train 0.89-0.99 vs CV ~azar), todos refutados.
   - **Bug de data detectado**: las features enriched están 100% vacías para h1_structure (30/30) y body_atr_ratio 100% vacío para m15_structure. El pipeline de enriquecido no cubre esos triggers.
   - **Conclusión #1+#3**: ML proper necesita 300-500+ trades limpios. Coincide con la regla "no tocar dynamic_conf con <300 trades". Re-evaluar en Fase 1.
   - ⚠️ **Implicancia para v3.35.0**: el ML predictor de producción (news AUC 0.75 claim) huele al mismo artefacto de split único que este workflow debunkeó (news 0.625→0.462 tras verificar). Pendiente: re-validar los modelos v3.35.0 con esta rigurosidad antes de confiar en USE_ML_CONFIDENCE.

2. ~~**Auto-tuning de gates v3.34.0**~~ ✅ RESUELTO (29 May, v3.38.1)
   - `tools/sweep_entry_gates.py` corrió los 30 combos (vel 3-8 × body 1.1-1.5) con gate de significancia
   - **Hallazgo: los 30 combos dan blocked-set = RUIDO** (CI cruza baseline 37.4% en todos). Los gates NO separaban ganadores de perdedores en ningún threshold — solo recortaban frecuencia.
   - **Acción: gates DESACTIVADOS por default** (config-driven, `ENTRY_GATES_ENABLED=false`). Reactivables con tuning si en 300+ trades aparece threshold significativo.

   *(#3 "modelos por trigger_type" resuelto junto con #1 arriba — ambos refutados, ver bloque #1)*

### Mediano esfuerzo (1-2 días)

4. **Volume features (MT5 tick_volume)**
   - MT5 da tick_volume (no real volume forex pero proxy)
   - Volume spike en breakout = signal más fuerte
   - Volume bajo = posible false breakout
   - Esfuerzo: 1 día (extracción + feature + validación)

5. **Confluencia multi-TF concreta (no binaria)**
   - Hoy solo htf_bias = bullish/bearish/neutral (3 valores)
   - Falta: score 0-10 de alineación M5+M15+H1+H4+D1
   - Cuanto más alineados, mejor el trade
   - Esfuerzo: 1 día (MTFAnalyzer ya tiene trends, solo sumar)

6. **Niveles psicológicos como features**
   - Números redondos (1.1700, 1.1750, 1.1800)
   - High/low de los últimos 3-5 días (no solo día previo)
   - Distance to nearest level como feature
   - Esfuerzo: 1 día

7. **Régimen del mercado (trending vs ranging)**
   - Detectar régimen con ADX o similar
   - Confidence diferente por régimen
   - Esfuerzo: 1-2 días

### Mayor esfuerzo (3+ días)

8. **Timing features finos**
   - mins_since_last_swing_high/low
   - candles_since_breakout (cuán reciente el setup)
   - pullback_depth (cuánto retrocedió antes de continuar)
   - consolidation_duration antes del move
   - Esfuerzo: 2-3 días (feature engineering complicado)

9. **News sentiment cuantificado (más granular)**
   - Hoy solo impact_score 0-100 como entrada
   - Falta: sentiment direction score numérico (no solo categórico)
   - Time decay del impact (news 1h vs 1 día)
   - Esfuerzo: 2 días

10. **Pivot a swing trading (TF más largo)**
    - Operar H4/D1 en vez de M5/M15
    - TP/SL más grandes → comisión % mucho menor
    - Menos sensible al timing exacto
    - Esfuerzo: 1-2 semanas (rediseño parcial del scanner)

### NO factibles con data actual (necesitan otro feed)

11. **Orderbook / liquidity zones** (no tenemos data)
12. **Inter-market correlation (DXY, treasuries, oil)** (requiere feed adicional)
13. **News sentiment cualitativo del LLM mejor estructurado**

### Próximos pasos planeados (orden)

- **Weekend 23-24 May**: probar #1 (Random Forest), #2 (gate tuning), #3 (modelo por trigger)
- **Si alguno mueve AUC >0.6**: continuar con #4 (volume) + #5 (multi-TF score)
- **Si ninguno mejora**: discutir con user pivot a #10 (swing) o cierre

---
---

**Última actualización**: 20 Ago 2026 — **v3.59.0: la calibración de confianza se desbloqueó
(309 limpios) y m15 dio el primer PASA del gate** (Brier 0.2214 < 0.230). Fase registro:
params congelados + `calibrated_p` en `entry_context`, 0 efecto en decisiones. Leer ~10 sep
con `score_calibrated_p_forward.py`; no mezclar con la lectura del ~1-sep del ATR floor.
Suite: 23 tests nuevos + regresiones db en verde.

**Anterior**: 19 Ago 2026 — **v3.58.0/.1: se ejecutó el roadmap completo del
research** ([`RESEARCH_INVESTIGATION.md`](RESEARCH_INVESTIGATION.md)): TCA enchufado (log_fill
estaba muerto), MFE/MAE reales, shadow book de rechazos (PRFS), signal_age + efficiency_ratio, y
cuenta CENT descartada por costo. Todo instrumentación: **0 cambios de decisión**, no contamina
las 4 lecturas agendadas. Suite 136 + 24 nuevos en verde. Detalle en
[`docs/historial_versiones.md`](docs/historial_versiones.md).

**Anterior**: 19 Ago 2026 — **v3.57.2: el lazo de decision queda cerrado en los DOS
sentidos y deja de depender del LLM.** Sobre v3.57.0 (retrospectiva pre-decision en shadow +
cableado de `adjust_setup_confidence`) se agregaron dos cosas en modo autonomo: **(a)** la leccion
direccional se deriva tambien en `archive_trade` — antes vivia solo en el path del LLM y con Ollama
caido el lazo moria en silencio; **(b)** el post-trade recibe el razonamiento de la entrada y
devuelve `missed_factor` contra lista cerrada, en columna propia. Suite **75 → 136** tests. Todo
verificado E2E contra copias de la DB, produccion intacta. Detalle y criterio de lectura en
[`PROGRESS.md`](PROGRESS.md).

**Anterior**: 19 Ago 2026 — **v3.57.0: la retrospectiva PRE-decisión (en shadow), el
cableado que faltaba, y un research que cierra dos puertas.** Pedido del user: que AIdan pueda razonar
*"esta señal era CALL y no PUT por X razones"* **antes** de la próxima decisión, sin bajar frecuencia.
Implementado como **nudge de confianza, nunca filtro** (`RETRO_MODE=shadow` por default: calcula y
registra con delta 0, porque todavía no hay UNA medición de que el veredicto discrimine). Cierra el
loop con `directional_lessons`, cuyo criterio se deriva en **código** — perdió **y** nunca se puso a
favor **y** pegó el SL, las tres juntas — no lo escribe el LLM. **Lo que apareció al armarlo:**
`setup_type` codifica la dirección (`trend_continuation_bull` es siempre CALL) ⇒ el lado opuesto tenía
n=0 SIEMPRE y la pregunta era inrespondible; de ahí las familias dirección-neutras. Se descubrió
ejecutándolo contra la DB real, no leyéndolo. **Además** se cableó `adjust_setup_confidence`, que
existía desde v3.31.0 y **nunca se llamaba desde ningún lado**, y se entregó la perilla
`ENABLE_NEWS_TRACK` (default ON: la decisión de girarla es del user). **Honestidad sobre el alcance:**
los gates de `min_confidence` viven dentro de los detectores y el lote sale de `sl_pips` ⇒ el nudge es
frecuencia- y tamaño-neutro **pero hoy inerte sobre la ejecución**; su valor es el registro y la
muestra. Suite 75 → 111 tests. Gate de 4 condiciones pre-declarado en
`tools/score_retrospective_shadow.py`; si con n≥40 no separa, `RETRO_MODE=off`.
**Del research** ([`docs/research_mercado_2026-08-19.md`](docs/research_mercado_2026-08-19.md)): el
edge bruto intradía por debajo del costo es la norma (14/14 familias fallaron en 947 días), el
pullback-entry queda refutado por dos vías, y el piso de ATR debería ser por **percentil** y no en
pips fijos. Y midiendo la latencia de news salió que **el cuello de botella es el feed (mediana 8,9
min), no el LLM (0,2 min)** — con lo que ningún prompt puede arreglar ese track.

**Anterior**: 16 Ago 2026 — **v3.55.0: el piso de ATR de m15 pasa de 5 a 8, como perilla
de env.** Salió de preguntar por qué m15 pierde tanto (es el peor track: −$124 lifetime, −$24,59 de
los −$37 de la última quincena). La respuesta no es "m15 está roto" sino **"m15 sangra en chop"**:
necesita ~40,5% de WR para empatar (ganador medio +7,8p, perdedor −5,3p) y con ATR ≤8p saca **27,8%**
(n=90, −$75,59), contra 51,6% con ATR >8p (n=31). Único hallazgo de m15 que pasa el gate completo
(p=0,0042, CI sin cruzar, mismo período). **Al revisarlo adversarialmente el lado bueno resultó
frágil** (2 días aportan casi todo el +$18,80) **pero el lado malo no** (pierde en las dos mitades)
⇒ la expectativa honesta es que m15 deje de sangrar, no que pase a rentable. Cuesta el 74% de su
frecuencia. Revertir = `M15_ATR_FLOOR=5.0`, sin rebuild. Forward ~1 sep.

**Anterior**: 16 Ago 2026 — **v3.54.1: el baseline contra el que se va a leer el
track D1 estaba mal, y se corrigió antes de la 1ra lectura (no después).** El titular del 13-ago
(242 señales, PF 1,40) corría con los params default y con un único `conf_adj` de sesión — el de la
hora en que se ejecutó el script. Re-medido con los params vivos y barriendo las 4 sesiones:
**186-227 señales, +10,8 a +12,7p post-swap, PF 1,25-1,30, positivo en las cuatro.** El edge no
dependía del reloj; el nivel baja ~10-15% y la frecuencia ~20%. Read-only, no se tocó el vivo.

**Anterior**: 13 Ago 2026 — **v3.54.0: track D = swing DIARIO (D1) en SHADOW.**
Nace de 7 años de velas, no de 171 trades: H4 refutado (−0,98 pips/trade), D1 con PF neto 1,40 y
19 de 19 combinaciones de parámetros positivas. Arranca en shadow por dos razones medidas — el swap
(−0,82 pips/noche) deja el CI95 cruzando cero, y el lote mínimo 0,01 no permite respetar el 1% con
SL de 82p en una cuenta de $639. No toca `auto_strategies` ni manda órdenes. 1ra lectura ~15 sep.

> 📚 **El changelog detallado de TODAS las versiones está en**
> [`docs/historial_versiones.md`](docs/historial_versiones.md) — incluye el bloque largo de
> "Última actualización" con el razonamiento de cada versión, y los historiales de jun/may 2026.

> 📁 **Los hilos ya CERRADOS de NOTAS están en**
> [`docs/historial_notas.md`](docs/historial_notas.md) — mediciones refutadas, bugs resueltos y
> checkpoints viejos. Consultarlo antes de re-proponer algo que ya se midió.
