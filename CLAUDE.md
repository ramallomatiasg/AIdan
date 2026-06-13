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

**⏰ LÍNEA DE TIEMPO — EJECUTAR SIN QUE EL USER LO PIDA (acordado 12 Jun: "cuando llegue el momento lo hacés directamente").** Al abrir sesión en/después de cada fecha pendiente, arrancar el item solo. Mediciones/shadows: hacer y reportar. Activaciones en vivo: llevar números + recomendación en el mismo turno (el OK sigue siendo del user). Marcar ✅ al cumplir:
- [ ] **Lun 15 Jun** — revisar `calendar_debug_log` con el primer evento: ¿el straddle shadow escribió, o el stage dice dónde muere? Si sigue 0 → debug dirigido.
- [ ] **Semana 15-19 Jun** — construir detector de régimen en SHADOW (idea 6 de `docs/mejora_continua.md`).
- [ ] **Vie 19 Jun (mini-checkpoint)** — 1ra lectura cooldown · PM intermedio · calendar · reconciliar universos lifetime · query canónica del censo · decisión mt5_filled_at + #632.
- [ ] **Vie 26 Jun (CHECKPOINT)** — veredicto PM (keep/revert) + **1er intento de calibración empírica** (~150 limpios) + 2da lectura cooldown.
- [ ] **Vie 3 Jul** — decidir la jugada de eventos (straddle vs momentum post-release vs skip) con el shadow acumulado.
- [ ] **Vie 10 Jul** — régimen: ¿celdas régimen×trigger bloqueables?
- [ ] **Vie 17 Jul (CHECKPOINT GRANDE)** — calibración robusta (~300 limpios) + decisión estructural (¿pivot a swing / nicho?).

**Experimentos en vivo (midiendo — NO tocar sin data nueva):**
- [ ] **Event-window (conciencia de eventos, v3.40.14)** · `EVENT_WINDOW_MODE=shadow`. Respuesta al pedido del user "tiene que operar alrededor de eventos, pero bien" (12 Jun). Hook en `_try_mt5_execute` (cubre ejecución normal Y retry): etiqueta CADA ejecución con proximidad al evento HIGH/MED más cercano (`event_window_log`, clasificación en el momento) + marca `would_block` si una señal CIEGA (structure/m15/h1/smc) o VIEJA (>10min, caso #625) cae dentro de la ventana (HIGH 15min antes/30 después; MED 5/15). news/pre_planned/calendar NO se marcan (jugadas de evento por diseño). **Plan "operar eventos bien"**: (1) este etiquetado junta data limpia de eventos, (2) shadow del straddle ya corre (feed FF REVIVIDO 12 Jun — verificado: /calendar con eventos), (3) en 2-4 sem decidir LA jugada de evento con data: straddle vs momentum post-release (única con evidencia viva: #604 ganó +5.30 entrando 7min post-CPI) vs skip. Flip a `active` solo con data del shadow.
- [ ] **Position Manager (experimento #1)** · `POSITION_MANAGER_MODE=active`. **RE-BASELINEADO 10 Jun (v3.40.11)**: hasta ahora el late-close pisaba al PM → solo corría su mitad defensiva; desde v3.40.11 los trades pueden por primera vez extenderse más allá del expiry (hasta MAX_HOLD 90/120/240min o SL/TP). Medir ~2 sem desde 10 Jun: avg_win / WR / PF; revertir a `log` si empeora. *Obs 8 Jun (sigue válida):* pasivo en perdedores pre-soft-expiry (diseño). *Obs 10 Jun:* el PM SÍ protege (CLOSE_PROTECT #610 a −2.9p vs SL −10.2p) y los HOLD ahora van a poder sostener de verdad. Vigilar los primeros días: trades viviendo 90-240min es comportamiento NUEVO en vivo.
- [ ] **Bounce-entry** · `SKIP_BOUNCE_ENTRY=shadow`. Juntar clasificación **limpia** en vivo (log al ejecutar, no reconstruida). No activar sin señal robusta varias semanas. Clasificación retrospectiva = frágil.

**Forense 10 Jun (día CPI, tarde -$23.73 en 6 trades 0W) — 2 BUGS REALES confirmados → RESUELTOS v3.40.11:**
- [x] ✅ **[MED-HIGH] Late-close pisaba al Position Manager** — RESUELTO v3.40.11 (`AIdan_TodoEnUno.py` late-close): con `POSITION_MANAGER_MODE=active` ya NO cierra por `'expired'` — gobiernan PM (R2/R4 MAX_HOLD 90/120/240min) + SL/TP duro; `auto_win`/`auto_loss` se siguen cerrando; en mode log/off sin cambios. Evidencia que lo motivó: cerró #609/#613/#614 a segundos del expiry pisando HOLDs del PM, y cortó al ganador #603 (+5.8p de 17p TP). **⚠️ EXPERIMENTO PM RE-BASELINEADO desde 10 Jun (v3.40.11):** lo medido del 5-10 Jun era solo la mitad defensiva (la extensión estaba muerta); ahora por primera vez los trades pueden vivir más allá del expiry hasta MAX_HOLD. Medir ~2 sem desde acá. Riesgo aceptado: si el thread del PM muriera (tiene guard FATAL v3.40.3), la salida es solo SL/TP (diseño: "SL/TP duro = única salida forzada").
- [x] ✅ **[MED-HIGH] entry_context m15/h1 doble-JSON-encodeado** — RESUELTO v3.40.11: los 2 call sites (`AIdan_TodoEnUno.py` m15/h1) pasan dict crudo (sin `json.dumps`); `get_entry_context` además hardened (doble-loads si encuentra str → filas viejas no crashean). El archive directo vuelve a correr para m15/h1 → features enriched dejan de salir vacías → la data limpia v3.40.x deja de contaminarse. Testeado funcional (fila vieja doble + fila nueva → ambas dict).
- [x] ✅ **[MED] P&L del header del dashboard era FALSO (caso "+6.87 en día de −33", 11 Jun, lo cazó el user)** — RESUELTO v3.40.13: `get_mt5_daily_pnl` sumaba SOLO el buffer vivo `auto_strategies` (rotativo ~8 filas) → al archivarse/purgarse los perdedores del día, desaparecían del número y quedaba la suma de los sobrevivientes (justo los ganadores) → "+6.87" en un día de −33. Fix: el dashboard ahora usa **broker-truth** (`MT5Executor.get_daily_pnl`: deals MT5 del día AR, comisiones de entrada+salida incluidas, offset servidor derivado en vivo del tick → robusto a DST) con fallback DB corregido (UNION con archive por `created_at`, dedup). Verificado en vivo: header pasó de +6.87 → −33.36 (= historial MT5). Lección repetida: TODA métrica mostrada debe salir del broker o de la unión completa, nunca del buffer vivo. el PM calculaba la edad del trade desde `created_at`, que para pre-plans es cuando se PLANEÓ (día anterior), no cuando se llenó la orden → "985min en trade" a los 20s del fill → CLOSE_MAXHOLD ejecutado ANTES del evento PPI para el que existía (el primer pre-plan activado con PM active lo expuso; irónicamente ese cierre ahorró plata — el rally post-PPI lo habría llevado al SL — pero hacía inútiles a TODOS los pre-plans). Fix: edad = `expires_at − expiry_minutes` (expires_at se re-escribe a activación+expiry al activarse; para trades normales da exactamente created_at; guard `>` + fallback a created_at si parse raro). Testeado: #615 real → 0.1min (antes 985), trade normal idéntico, expires malformado no crashea.
- [x] ✅ **[LOW] Timestamps UTC en logs** — RESUELTO v3.40.11: `position_manager_log`, `bounce_entry_log` y `calendar_shadow_log` ahora sellan `created_at` con `now_ar()` explícito (filas previas quedan UTC — cutover 10 Jun ~19:00 AR, para forense histórico tenerlo en cuenta). Idem inferencia trigger del instant-eval: ahora reconoce `[M15-STRUCT]`/`[H1-STRUCT]` (tags exactos, un title m15 puede MENCIONAR 'H1').
- *Contexto del día (no bug):* la pérdida fue **calidad de entrada en régimen hostil**, no gestión — los 6 de la tarde entraron con `htf_bias='bullish'` REZAGADO mientras el precio caía ~34p post-CPI (Régimen 4 del playbook); whipsaw de 18.4p mató #611 (conf 90 = peor pérdida, inversión de confidence RECONFIRMADA en vivo) y #612 (dirección correcta, timing contra rebote = Régimen 8). El management vivo funcionó: SL duros con slippage ≤0.6p, PM salvó ~$3 en #610 (PROTECT a -2.9p vs SL -10.2p), threads vivos toda la sesión. La mañana tuvo 3 wins (#603-608, ya purgados de auto_strategies por el cap — el "0 wins" era solo la tarde).

**Obs 11 Jun (día PPI/ECB: 14 trades, 3W/11L, −$29.22 — 3er día seguido de eventos) — para el checkpoint del viernes:**
- [ ] **PM tuvo su PRIMER día real en ambas direcciones** (evidencia viva para el punto 2 de la agenda): **primer CLOSE_PROFIT de la historia** (#621: se extendió **118min** más allá del expiry —comportamiento nuevo v3.40.11—, llegó a HWM 84% del TP, retrocedió y el PM aseguró +$4.52) + **6 CLOSE_PROTECT** cortando sangrías a −1.4/−1.8/−2.2/−2.9p en vez de SL completo + #627 TP completo (+$9.04). En el peor régimen, el management mostró su cara buena por primera vez. n chico, pero es exactamente lo que el experimento debía demostrar.
- [ ] **[obs, familia del bug #615 pero más leve] Edad/expiry corren desde la SEÑAL, no desde el FILL** — #625 esperó **27min como limit order pendiente** y el fill le llegó con 27 de sus 45min de vida ya comidos (el PM lo evaluó "28/45min" a los 17s del fill). Evaluar si la edad debería correr desde el fill para TODOS los trades → requiere timestamp de fill (columna `mt5_filled_at`, hoy NO existe). No urgente; decidir si vale la migración.
- [ ] **[obs] SL puede ejecutar con slippage GRANDE en spikes**: #625 cerró 1.15504 vs SL 1.15392 = **11p más allá del stop** en una vela de ~30p (el broker llena al siguiente precio). No es bug — es microestructura — pero significa que el "riesgo 1% por trade" puede excederse en velas violentas. Dato para sizing y CRÍTICO para la futura cuenta real.
- [ ] **[obs NUEVA, forense del spike 11 Jun] El retry de ejecución puede vender/comprar a MERCADO una señal VIEJA adentro de un spike** — #625: señal creada 14:01 AR, sin fill por 27min, y el bloque "MT5 retry" la ejecutó a mercado a las 14:28:58 — **dentro del primer minuto del spike** (vela de 19.1p tras un mercado planchado de 0.5p/min). Encima el SL (21.8p, estructural ancho) ejecutó con 11.2p de slippage por los gaps (precio saltando 13-15p/min) → −$13.48, la peor del día. La señal estaba obsoleta: "mejor precio" de fill en plena reversa violenta = selección adversa (te llenan justo cuando el mercado corre en contra). **Candidato a medir (no actuar aún): WR de fills tardíos (fill − señal > 10min) vs fills inmediatos** — medible con broker-truth (order setup time vs created_at). Sumar al script de sospechosos si da el tiempo el viernes.
- [ ] **[obs] M15 disparó 9 trades el 11 Jun** (la mayoría PUTs al serrucho de mediodía) — el track más frecuente justo en el peor régimen. Se suma a la observación previa "M15 sin techo de ATR" (data retrospectiva no existe — destruida por el bug del doble-encode; medible solo hacia adelante desde v3.40.11).
- *Contexto:* la racha 10-11 Jun cerró en ~−$53 los dos días (CPI whipsaw + PPI/ECB). Verificado de nuevo: sin pérdida de datos, sin bugs de ejecución nuevos (el −13.48 fue slippage de spike), threads vivos, daily loss limit (−$30/día) armado y sin disparar.

**Checkpoint 12 Jun — RESULTADOS DEL REVIEW COMPLETO (workflow 4 frentes + verificador, tarde):**
- [x] ✅ **PM sanity read (2 días de re-baseline)**: la MECÁNICA probada — 12/23 cierres se extendieron de verdad post-expiry; profit-lock #621 +$4.52; MAXHOLD #638 +$2.34 (antes moría al expiry); 10/11 PROTECTs cortaron antes del SL teórico (~113p cota superior, ⚠️ 34% de eso es UN solo trade H1 #637 — citar siempre con caveat). Cohorte extendida 2W/10L −$15.43 (régimen hostil, n=2 días) → **veredicto formal 26 Jun, no tocar**. Fix v3.40.12 verificado (0 edades absurdas post-fix). Obs nueva: #624 = un PROTECT dentro de un spike puede cerrar PEOR que el SL teórico (gap 3.4p) — sumado al item slippage/sizing.
- [x] ✅ **Idea #7 (agotamiento por run-up crudo) MEDIDA → DESPRIORIZADA**: ningún bucket de pips-recorridos-antes separa del baseline en la medición limpia. **LECCIÓN METODOLÓGICA CLAVE: el bucket ">15p/60min" daba 56% WR p=0.010 con cutoff −60s — era LOOKAHEAD de la vela en formación al entry; con cutoff −300s cae a ruido. REGLA NUEVA: toda medición retrospectiva sobre velas debe cortar ≥300s antes del entry.** El "agotamiento" que rima (SIM A, bias-confirmado 22%, conf 90) es de ALINEACIÓN DE INDICADORES REZAGADOS, no de corrida cruda — solo medible con etiquetado en-el-momento; al backlog sin prioridad.
- [ ] **Calendar shadow ROJO → instrumentado v3.40.16**: 0 filas con 2 eventos UoM Medium elegibles y proceso vivo el 12 Jun — 4 salidas SILENCIOSAS verificadas en código (S/R≤0 sin log, cache /calendar vacío en ventana, spread-gate, excepción por-evento a debug) = la clase M15. Fix: tabla `calendar_debug_log` + `_cal_dbg()` (throttled) en cada salida (detected/sr_zero/autotuner/spread/minconf/exception/feed_empty). **Vigilar el próximo evento (lunes): si detected aparece y shadow sigue en 0, el stage dice exactamente dónde muere.** (Al instrumentar casi meto un NameError de utc_now — cazado pre-ship.)
- [ ] **Bounce log infla por retries**: 304 filas = solo 65 estrategias (#625 logueado 121 veces) → **todo análisis debe dedupear por strategy_id (primera fila)**; dedup real: 28/65 (43%) son bounce — eso es PREVALENCIA, no WR (no confundir). 3 estrategias cambian de clase entre intentos.
- [ ] **Data limpia: 62 trades desde 5 Jun (~10/día hábil) → ~150 el 24-25 Jun (1er intento calibración), ~300 el 15-16 Jul (robusta).** Fix entry_context m15/h1 VERIFICADO end-to-end (17/17 post-cutover con features pobladas; pre-cutover vacíos como control). Fuga menor: #632 archivó con mt5_pnl NULL (investigar, el censo depende de ese campo). ⚠️ El contador necesita query CANÓNICA (dedup + cutoff explícito): el mismo día dio 62 vs 68 según la hora.
- [ ] **⚠️ Universos lifetime SIN reconciliar (no usar ninguno como baseline canónico):** broker 617 posiciones/−$512 vs DB 377/−$352 vs balance-implícito −$273 vs suspects n=363. Pueden coexistir (deals sin linkage, mt5_pnl NULL viejos) pero nadie lo reconcilió. Item para el 19 Jun.
- *Agenda 19 Jun:* 1ra lectura cooldown (skips + qué evitó) · PM lectura intermedia (camino al veredicto 26 Jun) · calendar: ¿escribió con la instrumentación? · re-censo limpio con query canónica · reconciliar universos · descartar las 3 filas pre-fix del event-window · decisión mt5_filled_at + #632.

**Checkpoint 12 Jun — DECISIONES TOMADAS:**
- [x] ✅ **Cooldown 5min post-pérdida ACTIVADO (v3.40.15)** — re-confirmado sobre data fresca el mismo día (n=76, WR 24% vs 37%, p=0.009, −$170, CI sin cruzar; siguió sumando pérdidas durante la semana). Implementación: gate en `_try_mt5_execute`; señal generada <5min después de una pérdida → **SKIP definitivo** (`skipped_cooldown`), NO delay (la señal nace de la vela de pánico; la franja 5-10min ya rinde 43% con señales frescas, no delayed). `COOLDOWN_AFTER_LOSS_MIN=5` (0=off). **Es EL cambio del checkpoint (1 a la vez); medir su efecto + el del PM en el próximo.**
- [x] ✅ **"¿Entra tarde o entra mal?" (pregunta del user) → RESPONDIDO con broker-truth: entra MAL, no tarde.** Sospechoso C del script: **94% de los fills son inmediatos (<1min, n=338) y al precio planeado (±3p, n=363) — y pierden al baseline (38% WR, −$324)**. Fills tardíos/corridos = ~20 casos, ~$37 (fuga menor; #625 la peor). Conclusión: la ejecución NO es el problema — **el problema es la DECISIÓN (qué/cuándo señala)** = vía 1 del user (mejorar el razonamiento), que es el programa en curso: data limpia → calibración empírica (~150 trades limpios) + event-awareness (shadow corriendo) + playbook. La vía 2 (precio-condicional estricto) NO ataca el grueso; el escudo de señales viejas (event-window shadow) ya cubre la fuga chica.
- [ ] *(arrastrado)* **Hallazgo original 10 Jun:** Re-entradas ≤5min tras una pérdida: **n=74, WR 24% vs 38% baseline, −$156 (34% de TODA la pérdida histórica en 12% de los trades), p=0.010, CI no cruza** (sobrevive Bonferroni 4 tests). Robustez: clasificación por timestamps EXACTOS de deals del broker (inmune a la fragilidad del caso bounce); sostenido en 4/5 quincenas; frontera nítida (franjas exclusivas: 0-2min 26% WR, 2-5min 23%, **5-10min 43%, 10-15min 48%** — la toxicidad termina exacto a los ~5min). CAVEATS: muestra históricamente cargada (78% del bucket es de abril; el sistema actual ya casi no re-entra rápido: ~16 casos en may-jun, ~−$42), y la pila es la sucia multi-versión. #611 del 10 Jun (peor pérdida del día, creado 2s tras cerrar #610 en rojo) es EXACTAMENTE este patrón. **Decisión pendiente (checkpoint viernes): activar cooldown 5min post-pérdida.** NO activado aún por "1 cambio a la vez" (experimento PM re-baselineado 10 Jun corriendo). Re-medir sobre data limpia v3.40.x es trivial (re-correr el script).
- [x] ✅ **Sospechoso "htf_bias rezagado" — REFUTADO como culpable general** (mismo script): trades con bias contradicho por la deriva real 2h previa = WR 41% (mejor que baseline, n=39, RUIDO); los con bias CONFIRMADO por la deriva = **22% WR, −$62 (n=27)** — otra rima con el tema exhaustion (todo alineado = entrada tardía). El día CPI fue un caso puntual, no un patrón. **NO tocar el mecanismo de bias.** (2do reflejo evitado del día: el conf ceiling 80 en M15 también se verificó al revés — conf>80 en M15/H1 rinde MEJOR: 45% vs 35%.)

**Deudas técnicas / gaps:**
- [ ] **Evaluation gap del news LLM** — Groq malinterpreta news (negaciones de bancos centrales, problema estructural #3) y **no medimos cuán seguido**. Gap de evaluación legítimo (lección LinkedIn 8 Jun). Idea: medir tasa de error con muestra etiquetada. No urgente.
- [ ] **OLLAMA_API/URL/MODEL sin definir** — GUI-only, no afecta trading. Spawneado como task aparte. Baja prioridad.
- [ ] **`calendar` trigger (0 trades en 325) — en SHADOW desde v3.40.4** · `CALENDAR_MODE=shadow`. Investigado 8 Jun, 2 causas: **(1) Feed FF 429** — el cache solo guardaba éxitos (`and events`) → con events vacío re-fetcheaba CADA ciclo → AIdan **se auto-baneó la IP** (hammering). ARREGLADO v3.40.4 (`main.py`): cachea el intento 1h SIEMPRE + User-Agent + loguea el 429 (antes silencio). Ahora le pega a FF máx 1/hora → la IP debería destrabarse en horas/días (no controlable desde acá). **(2) Straddle ROTO** — la anti-contradicción bloquea la 2da pata → solo dispararía CALL. Por eso quedó en shadow (`calendar_shadow_log`): loguea ambas patas SIN operar. **Para activar a vivo:** esperar que FF devuelva data → revisar shadow → arreglar el straddle (ambas patas; OJO doble comisión = problema #1) → recién ahí `CALENDAR_MODE=active`. El path 'active' TODAVÍA tiene el bug del straddle (no flippear sin arreglarlo).
- [x] ✅ **`smc` "dormido" = FALSA ALARMA (mía)** — investigado 8 Jun: `/smc-state` lo muestra VIVO (detectando zonas, "esperando confirmación M5" en zona demand); `smc.py` sin cambios desde v3.6.0; cadencia SIEMPRE fue lumpy (gaps de varios días normales). El "último trade 06-02" del archivo me asustó pero la data viva dice que está sano. NO tocar. Lección: chequear estado vivo antes de gritar bug.
- [x] ✅ **Sincronizar CLAUDE.md ↔ APP_VERSION** — sincronizado en v3.40.3 (línea *Última actualización* coincide con `Config.APP_VERSION`). Regla permanente: re-chequear en cada bump.

**Auditoría 8 Jun (multi-agente, 5 frentes) — hallazgos CONFIRMados (ninguno rompe trading HOY):**
- [x] ✅ **[HIGH] Significance gate `adjustment` vs `delta`** — RESUELTO v3.40.3 (`significance.py:194`): ahora lee `delta` (fallback `adjustment`). Testeado funcional: delta<0→worse, delta>0→better.
- [x] ✅ **[HIGH] Thread del PM con imports sin guard** — RESUELTO v3.40.3 (`AIdan_TodoEnUno.py:3588`): setup envuelto en try/except con log FATAL. Verificado en vivo: PM arranca y gestiona #585.
- [x] ✅ **[MED] Timezone applied_at/reverted_at** — RESUELTO v3.40.3 (`db.py:3172`): sella con `now_ar()` (AR), igual que `created_at`; el monitor de auto-revert ya no se desfasa 3h.
- [x] ✅ **[MED] `smc_status` sin guard 1er ciclo** — RESUELTO v3.40.3 (`AIdan_TodoEnUno.py:2082`): init `smc_status = None` junto a htf_bias/daily_ctx.
- [ ] **[LOW/hipótesis] `sync_pending_orders` 'expired' en respuesta vacía transitoria** (`mt5_executor.py:552-589`): clase v3.35.2 al revés. HIPÓTESIS (necesita confirmación runtime). Hardening: confirmar con `history_orders_get` antes de escribir 'expired'.
- [ ] **[LOW] Idempotency `startswith` colisión** (`mt5_executor.py:164`): "AIdan #5" matchea #50/#565; hoy inalcanzable (siempre el id más nuevo). Fix defensa: match delimitado.
- [ ] **[nota, NO fix apurado] HWM no lo persiste el PM** (`AIdan_TodoEnUno.py:3647`): R1 profit-lock depende de que el thread de trailing (1s) escriba `mt5_high_water`. Funciona hoy; el fix naive clobberea el trailing step → arreglar con helper HWM-only, sin apuro.
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

## Versiones recientes (changelog top-of-mind)

| Version | Cambio | Estado |
|---|---|---|
| v3.6.3 | Baseline (-$93 sobre 100 trades, PF 0.59) | superada |
| v3.7-3.17 | Filter tuning iterations (ver historial git) | superada |
| v3.18.0 | Late breakout 3→7p (recuperar frecuencia) | superada |
| v3.19.0 | Track B M15 implementado (paralelo M5) | activo |
| v3.20.0 | Track C H1 implementado (paralelo M5+M15) | activo |
| v3.21-3.27 | LLM provider primario, news improvements, etc | superada |
| v3.28.0 | Telegram bot bidireccional + daily loss limit + consensus boost + spread guardian | activo |
| v3.29.x | Dashboard equity curve + heatmap + trade modal + slippage stats + filter contrib | activo |
| v3.30.0 | Performance: 15 DB indexes + cache TTL + polling redundante eliminado | activo |
| v3.30.1 | MTF candle fetch paralelo + news LLM analysis paralelo | activo |
| v3.30.2 | Shutdown rapido <2s + LRU cache news + query optimization /auto-strategies | activo |
| v3.30.3 | Fix /recent Markdown (escape `_`) + drawdown alert daily-basis (no spam lifetime) | activo |
| v3.30.4 | HTML interactive tools: theme editor + backtest report (inspired by Thariq/Anthropic) | activo |
| v3.30.5 | Theme editor: font-size + card-padding sliders ahora cascadean visualmente (em units) | activo |
| v3.30.6 | What-if simulator: filtros retroactivos sobre trade_archive REAL (164 trades) | activo |
| v3.30.7 | Remove backtest HTML report + tutorial inline en what-if simulator | activo |
| v3.31.0 | Meta-Optimization: shadow mode + LLM nightly analyst (19h AR) + auto-applier + monitor con rollback | activo |
| v3.31.1 | Full autopilot: auto_start_shadow_for_proposed() — proposed→shadow_validating automatico, max 3 simultaneos, dedup | activo |
| v3.31.2 | Manual trigger: boton ▶ Run analyst en dashboard reemplaza Task Scheduler (user puede correr cuando quiera) | activo |
| v3.31.3 | Hotfix: NameError `logger` en start_services (splash quedaba colgado en "Iniciando Dashboard API") | activo |
| v3.31.4 | Hotfix pre-plan: sanity check expandido + SL/TP del LLM (no profile M5) + min_conf 60 + lot cap 0.05 | activo |
| v3.31.5 | UI fix: pre-plans ejecutadas mostraban created_at (ayer 5pm) en vez de event_time. Priorizar event_time siempre | activo |
| v3.31.6 | Hotfix nightly_analyst: claude CLI `--input-file` no existe → usar stdin + `--dangerously-skip-permissions` (Opus funciona) | activo |
| v3.31.7 | Warmup gate M15 (30min) + H1 (60min): bloquea trades en primeros minutos post-restart (sobre-operacion fix) | activo |
| v3.31.8 | CRITICO: shadow runner bugs — hour_utc/session/setup_type vacios → filtros block_hour/block_session/block_setup nunca disparaban | activo |
| v3.32.0 | Math fixes: TP 15→20p + BE trigger 50% + trail 80% (atacar "gana poco/pierde mucho") | activo |
| v3.32.1 | User awake window: no abrir H1 después de 19h AR (expiry 3h cae en madrugada). Configurable via env. | activo |
| v3.33.0 | REFACTOR Fase B: macro context (htf_bias + daily_ctx) ahora GARANTIZADO en M5/M15/H1 (antes None si M5 skipped). + tool train_confidence_model.py (Fase A preparatoria, Brier 0.28 vs 0.39) | activo |
| v3.34.0 | REFACTOR Fase C: Entry Quality Gates basados en hallazgos ML | activo |
| v3.35.0 | ML Confidence Predictor: modelos dedicados (news AUC 0.75, m15 AUC 0.625) + feature flag USE_ML_CONFIDENCE (default OFF). Endpoints `/ml-predictor/status` y `/ml-predictor/test`. | activo |
| v3.35.1 | Counter-HTF news gate: threshold 65 → 60 (= base min_conf). 26 May: 4 news directional, 0 strategies. v3.34.0 entry gates + v3.35.0 ML predictor ya filtran exhaustion/low-P(win), duplicar con 65 acumulaba filtros sin evidencia. Tambien: cleanup meta-filters viejos (revert #10, reject #7/#9/#13). | activo |
| v3.35.2 | Bugfix: duplicate MT5 order durante reconexion. Strategy #537 (26 May post-MT5 reconnect 11:07) genero 2 tickets en MT5 (limit order send tiro exception pero orden si llego al server). Orphan detector cerro la duplicada al spread (-$0.80 commissions waste). Fix: idempotency check en open_position + en _try_limit_order failure paths via comment match "AIdan #{strategy_id}" en positions/orders. | activo |
| v3.35.3 | ATR floor M5 bajado 2.5 → 2.0p (news + structure + SMC). Semana 26 May: mercado quieto (ATR 1.8-2.3p casi todo el dia, lunes feriado US/UK) dejaba AIdan con 0-1 trades/dia. ML predictor (v3.35.0) actua como red de seguridad. M15 (5p) y H1 (10p) sin cambios. | activo |
| v3.36.0 | Live Position Manager (Fase 1: reglas, sin LLM). Gestor en vivo que decide HOLD/CLOSE_PROFIT/CLOSE_PROTECT/CLOSE_MAXHOLD sobre posiciones abiertas, reemplazando el expiry ciego + force-close por mechas re-analizadas (bug del #538). Thread cada 15s. MODE=log/active/off. MAX_HOLD 90/120/240min (M5/M15/H1). Profit-lock arma a 60% TP, cierra si retrocede 40% del pico. Tabla position_manager_log. | activo |
| v3.37.0 | Position Manager Fases 2+3 construidas (defaults seguros). Fase 2: LLM Exit Advisor (`src/analyzer/exit_advisor.py`). Fase 3: endpoints `/position-manager/state`+`/stats` + dashboard `/position-manager`. | activo |
| v3.37.1-3 | Boton 🎛️ Position Manager en dashboard + panel muestra HOLDs ademas de closes. | activo |
| v3.37.4 | Counter-HTF news gate reforzado: usa ML conf adicional al LLM conf (caso #542). | activo |
| v3.38.0 | Gate de significancia adversarial (`src/optimizer/significance.py`). Todo block/adjust de subset pasa por verify_change_proposal ANTES de persistir en pending_changes. Binomial one-sided + Wilson CI 95% vs baseline 37.4%. Default=RUIDO si n<25 o CI cruza baseline. | activo |
| v3.38.1 | Entry Quality Gates v3.34.0 DESACTIVADOS (config-driven `ENTRY_GATES_ENABLED=false`). Sweep mostró que los 30 combos vel×body son ruido. | activo |
| **v3.39.0** | **Skip bounce-entry (modo SHADOW por default). Filtro que detecta cuando AIdan entra sobre una vela contra-direccion (PUT sobre vela verde / CALL sobre roja) — validado p=0.000: bounce-entries 22% WR vs 45% normales, sostenido en todas las epocas, sin subgrupo salvable (ni esperar ni SL ancho lo arreglan, solo SKIP). Hook central en `_try_mt5_execute`. Config SKIP_BOUNCE_ENTRY=off/shadow/active. Shadow registra "habria saltado" sin actuar → tabla `bounce_entry_log` + endpoint `/bounce-entry/stats`. Validar en vivo antes de flip a active. Origen: caso #565 + insistencia del user.** | **actual** |

### Filtros activos (v3.18.0)

```
Warmup gate M5 (10 min tras arrancar)
Warmup gate M15 (30 min — 2 velas frescas)  -- v3.31.7
Warmup gate H1 (60 min — 1 vela fresca)      -- v3.31.7
ATR floor 2.0p (M5 — v3.35.3, antes 2.5p)
ATR ceiling 6p
Counter-HTF (news regular path requiere conf≥60 — v3.35.1)
Counter-both (M5+HTF ambos contrarios → block)
SIM A (fully-aligned trades blocked, exhaustion entries)
Min conf 60 (bypass a 30 si impact≥55 y NO counter-HTF)
Conf ceiling 80 (anti-predictive)
Late breakout 7p
AutoTuner setup-type block
ML-driven blocked_setups patterns
Market hours (sesiones activas)
Anti-contradiction pre_planned (no PUT+CALL simultáneos)
```

### Filtros REMOVIDOS por evidencia contaminada (no re-introducir sin data limpia)

- Hour gate UTC 12/14/20 (v3.17.0)
- Late breakout 3p (v3.18.0, ahora 7p)

---

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
| `backtest_h1_m15.py` | Backtest estructural-only sobre candles MT5 históricas. Re-corre `detect_structure_signals()` y simula SL/TP/expiry hit. Solo trigger `structure`, sin news/calendar/pre_planned/smc-live. |
| `dashboard_theme_editor.html` | Editor visual standalone con color pickers + sliders para todos los CSS vars del dashboard. Live preview de cards/charts/tables. Presets (Dark/Light/Midnight/Terminal/Sunset). Botón export CSS al clipboard. Endpoint: `/theme-editor`. |
| `what_if_simulator.html` | Simulador retroactivo sobre `trade_archive` REAL (164+ trades). Sliders min_conf/conf_ceil/atr_floor/atr_ceil + checkboxes trigger/dir/session/dow/hour/htf_bias + bloqueo counter-HTF + exclude SL-hit-only. Recomputa WR/PF/PnL al instante, delta vs baseline real. Equity curve, heatmap por hora, breakdown trigger. Endpoint: `/what-if`. Data via `/trade-archive-data`. |
| `meta_optimization.html` | Dashboard del meta-optimizer v3.31.0. Muestra pending_changes por status, baseline vs shadow PF, audit trail por cambio, action buttons (approve/revert/reject/start-shadow). Endpoint: `/meta-optimization`. |
| `nightly_analyst.py` | Manual trigger desde dashboard (botón ▶ Run analyst). LLM analyst (Opus → Groq → Ollama fallback chain) analiza stats 24h/7d/30d y propone cambios JSON estructurados. Min sample thresholds + guard-rails hard-coded. Inicia shadow validation automaticamente vía auto_applier. v3.31.2: removida la Task Scheduler. |
| `backtest_parallel.py` | Backtest paralelo de combinaciones de filtros sobre `trade_archive` (trades ya ejecutados). |
| `backtest_weekly.py` | Wrapper semanal de `backtest_parallel.py` con notificación Telegram. |
| `test_m15_feed.py` | Test standalone del feed M15 (verificar candles + indicators). |
| `analyze_trending.py` | Analiza % tiempo en tendencia vs lateral del histórico. |
| `deep_analysis.py` | Análisis profundo de trade_archive (patrones, correlaciones). |
| `ml_feature_analysis.py` | Feature importance ML sobre features de trades. |
| `benchmark_llm_models.py` | Benchmark velocidad/calidad de modelos Ollama. |
| `aidan_watchdog.py` | Watchdog que reinicia AIdan si se cuelga. |
| `measure_entry_suspects.py` | Medidor READ-ONLY de sospechosos de calidad de entrada sobre deals del broker (timestamps exactos, inmune a la fragilidad de re-derivar velas). Mide: (A) re-entrada ≤2/5/10/15min tras pérdida vs resto, (B) htf_bias contradicho/confirmado por la deriva real 2h previa. Pasa cada subset por `significance.verify_finding`. Re-correr en cada checkpoint sobre data nueva. |

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
5. ❌ Borrar trade_archive, learning_insights, o cualquier histórico.
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

## Reglas de mantenimiento de este archivo

**IMPORTANTE**: con cada cambio significativo (nueva versión, feature, herramienta, hallazgo de backtest), CLAUDE.md DEBE actualizarse. Antes de cada sesión nueva con asistentes IA, leer este archivo completo para mantener contexto. La última actualización siempre debe coincidir con la versión activa en `Config.APP_VERSION`.

**Checklist tras cada cambio**:
- ✅ Bumpear `APP_VERSION` en `src/common/config.py`
- ✅ Actualizar tabla de versiones en CLAUDE.md
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

**Última actualización**: 12 Jun 2026 — v3.40.16 (cierre del checkpoint): instrumentación del path calendar-straddle (`calendar_debug_log` + `_cal_dbg()` throttled en cada salida que era silenciosa: detected/sr_zero/autotuner/spread/minconf/exception/feed_empty) — el shadow del calendar dio 0 filas con 2 eventos elegibles el 12 Jun y era imposible saber por qué (4 salidas mudas, clase M15); el lunes el primer evento dice dónde muere. Review completo del checkpoint en NOTAS (PM sanity ✓ mecánica probada, idea agotamiento medida→despriorizada con lección lookahead −300s, data limpia 62→150 el ~24-25 Jun, universos lifetime sin reconciliar). v3.40.15 (CHECKPOINT): **cooldown 5min post-pérdida ACTIVADO** (la decisión agendada; re-confirmado mismo día sobre data fresca: n=76, 24% vs 37%, p=0.009) — señales nacidas <5min tras una pérdida se skipean (`skipped_cooldown`); es el cambio único del checkpoint. + Respondida la pregunta del user "¿entra tarde o mal?" con broker-truth (sospechoso C nuevo en `measure_entry_suspects.py`): **entra MAL — 94% de fills inmediatos al precio planeado pierden al baseline**; la ejecución no es el problema, la decisión sí (vía: data limpia → calibración + event-awareness). + fix shadow event-window: `trigger_type` se lee de la DB (los call sites no lo pasan → un news post-UoM quedó mal marcado would_block el primer día). v3.40.14: event-window en SHADOW ("operar eventos, pero bien" — pedido del user tras el forense del spike). Módulo `src/common/event_window.py` (proximidad al evento HIGH/MED más cercano, cache 10min sobre /calendar) + tabla `event_window_log` + hook en `_try_mt5_execute` (cubre normal Y retry): etiqueta cada ejecución y marca would_block para señales ciegas/viejas dentro de la ventana del evento (HIGH 15/30, MED 5/15) SIN bloquear. Contexto: el calendario FF se DESTRABÓ (fix v3.40.4 hizo efecto) — la mañana del 11 Jun (ECB+PPI 08:15-08:45 ET) estaba publicada y AIdan entró ciego (#618 a 3min de la decisión ECB, #619 durante el PPI); el spike de las 20:28 server en cambio NO era evento agendado (headline sorpresa, solo manejable con SL/sizing). Verificado en vivo: /calendar con eventos, proximidad funcionando ("UoM Sentiment en 489min"), tabla creada, tests de ventanas/would_block pasan. v3.40.13: P&L del header del dashboard era FALSO (mostraba "+6.87" en un día de −33; lo cazó el user): `get_mt5_daily_pnl` sumaba solo el buffer vivo `auto_strategies` y al purgarse los perdedores al archive quedaba la suma de los sobrevivientes. Ahora: broker-truth (`MT5Executor.get_daily_pnl`, deals del día AR con comisiones, offset servidor auto-derivado) + fallback DB con UNION al archive. Verificado: header +6.87 → −33.36 (= historial MT5). v3.40.12: fix del PM matando pre-plans recién activados (caso #615: edad calculada desde `created_at` = cuando se planeó, no desde el fill → "985min en trade" a los 20s → CLOSE_MAXHOLD antes del evento PPI). Edad real = `expires_at − expiry_minutes` (= activación para pre-plans, = created_at para trades normales), guard + fallback. Contexto del día: racha de 11 pérdidas seguidas desde el mediodía del 10 (≈−$38, CPI+PPI whipsaw dos días seguidos — Régimen 7/8); verificado: sin pérdida de datos, SLs acotaron cada pérdida al ~1% configurado, la extensión post-expiry de v3.40.11 NO causó ninguna pérdida, daily loss limit armado (−$30/día). Decisión: NO tocar estrategia por la racha (n=11 en régimen hostil); cooldown 5min se decide el viernes. v3.40.11: fixes del forense del día CPI (tarde -$23.73, 6 trades 0W; la mañana tuvo 3W +$15 brutos — el "0 wins" era solo la tarde). El management estaba VIVO y funcionó (SL slippage ≤0.6p, PM salvó ~$3 con PROTECT en #610, threads cubrieron todo); la pérdida fue calidad de entrada (htf_bias 'bullish' rezagado vs caída de 34p post-CPI + whipsaw 18.4p; #611 conf 90 = peor pérdida → inversión de confidence reconfirmada). 2 bugs REALES arreglados: **(1) late-close pisaba al PM** — cerraba todo 'expired' a segundos del expiry sin chequear POSITION_MANAGER_MODE (pisó 3 HOLDs y cortó al ganador #603 a +5.8p de 17p TP); ahora con PM active gobiernan PM/MAX_HOLD/SL-TP → **experimento PM re-baselineado desde 10 Jun** (antes solo medía su mitad defensiva). **(2) entry_context m15/h1 doble-JSON-encodeado** — `.get()` sobre str → AttributeError tragado → archive directo NUNCA corría para m15/h1 (explica las features enriched vacías; contaminaba la data limpia); fix: dict crudo en los 2 call sites + `get_entry_context` hardened para filas viejas. Menores: 3 logs (PM/bounce/calendar-shadow) sellaban created_at en UTC → ahora `now_ar()` (cutover 10 Jun ~19hs AR); inferencia trigger del instant-eval reconoce [M15-STRUCT]/[H1-STRUCT]. Forense via workflow multi-agente (4 frentes + verificador adversarial que además corrigió el encuadre del día y detectó el bug 2). v3.40.10: 2da auditoría completa (6 frentes, read-only). **Veredicto: código nuevo limpio** — `_resolve_slot` y el gate shadow del calendar verificados CORRECTOS (ejecutados), 0 undefined names, los fixes de v3.40.0/v3.40.3 intactos, guard-rails sin bypass. 4 fixes del "set seguro": (1) `tune_optimizer_param` tiraba **TypeError** (`change_manager` llamaba a `_save_params(..., iteration=)` que no existe) → todo cambio de ese tipo se auto-rechazaba (lever muerto del meta-optimizer) → sacado el kwarg; (2) guard del `analyze` serial del news loop (un throw ahí abortaba el ciclo entero incl. SMC/M15/H1 — el pre-planner y calendar YA estaban guardados, el agente sobre-estimó); (3) `expires_at` de pre-plans con doble offset TZ → normalizado a AR naive (arregla el "Invalid Date" en la card planned); (4) `auto_applier` comparaba con `utcnow()` vs stamps AR (~3h) → `now_ar()`. **Deferido (documentado en NOTAS, no urgente):** lock de threading del cierre del PM + hardenings chicos (prof_sl, time_in_trade log, entry_price>0, sync_pending_orders). v3.40.9: pre-planner — la consolidación de planes del mismo evento ya NO elige por confianza más alta (ese número lo auto-reporta el LLM y está mal calibrado: conf 90 → 0% WR). Ahora **vota la dirección** entre las N líneas (cada una = 1 voto); **empate → NO opera** (señal incoherente); confianza consolidada = **promedio del lado ganador** (un outlier confiado del lado minoritario NO gana). Caso real: el CPI (3 PUT 50/50/55 + 1 CALL 60) ahora resuelve a PUT~52 → **SKIP** por el gate conf-60 (antes el viejo "max conf" operaba la CALL outlier). `_resolve_slot` testeado (CPI→skip, empate→skip, unánime fuerte→opera, outlier no gana). Los 4 pre-plans existentes del CPI marcados auto_skipped. **El confidence del news/pre-plan LLM sigue mal calibrado de raíz (evaluation gap), esto solo evita confiar ciegamente en él.** v3.40.8: pre-planner — arreglado bug que generaba **4 planes contradictorios para un mismo evento** (el CPI sale en 4 líneas —y/y, m/m, Core y/y, Core m/m— al MISMO horario → 4 planes, a veces direcciones opuestas). **Causa raíz = misma clase que el bug de M15**: la dedup intra-run estaba rota (l.523 hacía `planned_hours.add(event_hour)`, nombres de un refactor viejo ya inexistentes → NameError silencioso tragado por el try → `planned_slots` nunca se actualizaba dentro de la corrida). Fix: consolidar por slot UTC y crear UN solo plan (el de mayor confianza = señal más fuerte del informe). Existentes consolidados (quedó #601 CALL 60; los 3 PUT <60 marcados auto_skipped — igual se saltean al activar por el gate conf-60). NOTA: el LLM dando direcciones opuestas para el mismo informe sigue siendo el "evaluation gap del news LLM" (no resuelto acá, queda en cola). v3.40.7: dashboard — los pre-plans ahora muestran la hora de **activación** explícita ("⏰ Se activa ~09:25 · evento 09:30", en hora AR; activación = 5min antes del evento por `activate_due_planned_strategies(minutes_before=5)`). Antes solo se veía la hora del evento, no la de activación. Bug menor anotado (no urgente): el `expires_at` de pre-plans en estado planned está malformado (doble offset `-04:00-03:00`); se sobrescribe limpio al activarse, no afecta la UI. v3.40.6: dashboard cards más limpias — (1) removidos los botones de abajo (Win/Loss/Skip + Pausar): AIdan auto-evalúa y el PM gestiona; (2) la explicación ya no repite el prefijo `[H1-STRUCT]`/emoji (el badge de color arriba ya lo dice) — solo el texto; (3) hora: apertura abajo (⏰) + cierre al lado (🏁) más grande (17px), sin duplicarla arriba. Nota: la hora de cierre real (mt5_closed_at) no la expone la API → en activas muestra el expiry (exacto); en cerradas el badge de P&L ya dice el resultado. v3.40.5: dashboard — badge de P&L en las cards sin prefijo "MT5" y agrandado (12→16px) para leerse mejor (el badge activo ticket+lote queda igual). v3.40.4: trigger `calendar` revivido en SHADOW. Análisis de estrategias (323 trades reales) mostró que `calendar` nunca operó (0/325) y `smc` es el único +EV (PF 1.14, n=27). Investigado `calendar`: 2 causas — (1) feed Forex Factory 429 porque el cache solo guardaba éxitos → re-fetch cada ciclo → auto-ban de la IP (hammering); arreglado (cache 1h siempre + User-Agent + log del 429, antes silencioso). (2) el straddle está roto (anti-contradicción bloquea la 2da pata → solo CALL). Quedó en `CALENDAR_MODE=shadow` (tabla `calendar_shadow_log`: loguea ambas patas sin operar); flip a `active` solo tras ver shadow real + arreglar el straddle. SMC investigado = FALSA ALARMA (sano, cadencia lumpy normal). — v3.40.3: 2da auditoría multi-agente (5 frentes, read-only). 4 hallazgos confirmados arreglados — (1) significance gate leía `params['adjustment']` cuando todo el sistema usa `delta` → corría la hipótesis direccional al revés (gate adversarial mal calibrado para `adjust_setup_confidence`); (2) thread del Position Manager con imports sin guard → ahora try/except + log FATAL (defiende contra la clase de bug que mató M15); (3) `applied_at`/`reverted_at` sellados en UTC vs `created_at` en AR → ahora `now_ar()` (el monitor de auto-revert ya no se desfasa 3h); (4) `smc_status` sin init → NameError 1er ciclo. Verificado en vivo: PM gestiona #585 (h1), 0 errores, fix significance testeado funcionalmente. Hardening menor (sync_pending_orders 'expired' transitorio, idempotency `startswith`, HWM coupling) documentado en NOTAS sin tocar (default = no tocar lo que anda). v3.40.2: chip `profile_name` fuera del dashboard. v3.40.1: timedelta NameError en pre-plan.

**Historial 5 Jun 2026 — v3.40.0**: arreglados 5 bugs confirmados por auditoría multi-agente. **CRÍTICO: M15 (Track B) y H1 (Track C) estaban MUERTOS desde el 23 May** (v3.33.0 borró `_htf_bias_now`/`_htf_bias_h1` pero dejó las lecturas → NameError silencioso en cada señal; 0 trades m15/h1 en 2 semanas — esto explicaba la baja frecuencia). Fix: → `htf_bias`. También: rr_ratio NameError en compute_adaptive_sl_tp (override learning + SL estructural), eval de arranque ignoraba MT5 (P&L fantasma en trade_archive), jitter random ±3 removido (decisiones deterministas), y preservación del TP override en ensanche estructural. dynamic_conf (triple-conteo, ±15 minSize, calibración) NO tocado (regla <300 trades). Re-baseline del experimento PM tras esto.

### Checkpoint 5 Jun (pre-bugfix) Semana (por cierre, real): NETO +$10.52, 38 trades, WR 47% (vs histórico 37% y sangrado -$93/sem). Veredicto calibrado: sangrado FRENADO (confianza alta, real) pero NO probado rentable (margen microscópico, n chico). El mayor logro fue el PROCESO (limpieza de overfit + metodología + 2 casi-desastres evitados). **DECISIÓN (fase demo = sandbox, testear en vivo sin miedo a plata ficticia, 1 cambio a la vez): Experimento #1 = Position Manager ACTIVADO** (`POSITION_MANAGER_MODE=active`). Ataca el problema #1 (expiry mata trades buenos), solo validable en vivo (contrafáctico=sim=trampa). Medir 2 semanas avg_win/WR/PF vs previas; revertir a 'log' si empeora. Bounce sigue en shadow; ATR ceiling y params overfit en cola.

### Historial bounce-entry (3 Jun)
Skip bounce-entry **NO CONCLUYENTE** (queda en `SKIP_BOUNCE_ENTRY=shadow`, no activar). Round 1 (sim): bounce 22% WR p=0.000. Round 2 (outcomes reales): 43% vs 34% — opuesto, el sim invertia. Round 3 (user cuestiona la validacion): ambos clasifican "bounce" re-bajando velas MT5 (timezone/cual-vela = fragil); clasificacion limpia tiene n=4 → no concluye. NO sabemos si bounce es bueno/malo. Decision robusta: no activar, dejar shadow juntando clasificacion LIMPIA en vivo varias semanas. Lección triple en Metodología punto 1.

### Historial previo
**31 May 2026 — v3.38.1 (sin cambio de código; cambios de config/research).**
- Workflow ml-model-bench (backlog #1+#3): RF/XGB/LR y modelos por-trigger TODOS refutados a n=276 (overfit, AUC real <0.5 tras verificación adversarial). `confidence` sola ≈ AUC 0.59 > cualquier modelo ML. Sin señal aprendible hasta 300-500+ trades.
- **ML predictor v3.35.0 APAGADO** (`USE_ML_CONFIDENCE=false` en .env). `tools/revalidate_predictor.py` confirmó que el AUC 0.75/0.625 era espejismo de corte único (~12 trades test); AUC honesto ~0.57 ambos, no significativo (p 0.17-0.34). La heurística vieja (~0.59) es igual o mejor. AIdan vuelve a confianza heurística en todos los triggers. Reactivable solo con 300+ trades + CV honesto.
