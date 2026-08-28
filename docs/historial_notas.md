# Historial de hilos CERRADOS (NOTAS de CLAUDE.md)

Archivo de solo-lectura. Acá bajan los hilos de `CLAUDE.md` > NOTAS cuando se cierran (✅),
para que CLAUDE.md quede con lo ABIERTO y no cueste ~20k tokens de contexto en cada sesión.
Nada se borró: los bloques están verbatim como estaban.

Regla (acordada 8 Jun 2026): hilo cerrado → marcar ✅ y **bajar a este archivo**; hilo nuevo → agregar a CLAUDE.md.

---

- [x] ✅ **Detector de régimen MEDIDO 14 Jun → NO se construye** (barrido exhaustivo): ninguna celda régimen×trigger pasó el gate; la única que pasó era régimen×vol y frágil al lookahead. Plan corregido: etiquetar en vivo y re-medir ~17 Jul. (En lugar de construir el detector esta semana.)
- [x] ✅ **#4 SESGO DIRECCIONAL — REFUTADO como bug.** El precio CAYÓ ~160p en 3 días (entry prices 1.161 el 16 → 1.145 el 19). "Todo PUT" era la dirección CORRECTA. NO hay sesgo equivocado que corregir (otra vez: medir antes de tocar evitó "arreglar" algo sano).
- [x] ✅ **#1 Cooldown — RE-VALIDADO** (≤5min n=76 WR 24% vs 36%, p=0.014, CI no cruza; ≤10/15min siguen RUIDO). Ya está activo (v3.40.15), sin cambio. Bias-stale (suspecto B) RE-REFUTADO (36%=baseline).
- [x] ✅ **v3.40.20 — pullback-QUALITY en SHADOW (construido 19 Jun, workflow diseño+verificación adversarial).** El workflow REFUTÓ mi propuesta original antes de codear: el "pullback puro" YA EXISTE (bloque 7 `trend_continuation`) y es la PEOR familia (n=103, 28% WR, −$153) vs breakout (41%). **El edge real NO es el timing — es la CALIDAD DEL NIVEL** (por eso SMC es el único +EV: zonas validadas vs fractal de ruido de structure). Pivot: detector que dispara solo sobre **nivel validado (≥2 toques, como SMC) + vela de rechazo**, anclado a htf_bias, downtrend=vender rally / uptrend=comprar dip. **SHADOW** (`PULLBACK_ENTRY_MODE=shadow`, default): loguea a `pullback_shadow_log` con candle snapshot SIN appendear a signals → **M5 vivo 100% intacto** (solo M5, las subclases M15/H1 se excluyen). Scorer `tools/score_pullback_shadow.py` mide el movimiento real FORWARD (~1h, sin re-simular SL/TP) → respuesta empírica en 2-3 sem vía comparación pareada vs breakdown + gate de significancia. **Predicción calibrada honesta: ~60% que el shadow lo confirme ruido** (consistente con los 103 trades); si pasa → activar; si no → el lever real es calidad-de-nivel / más peso a SMC (plan B explícito). El RSI gate del diseño original se SACÓ (la data probó que rsi>38 no separa). Activar a ciegas = el error de bounce/ML/gates (3×). Es el cambio que el user pidió ("hora de cambios") hecho SIN arriesgar el vivo.
- [x] ✅ **v3.40.21 — CALIDAD DE NIVEL (plan B) medida EN PARALELO (pedido del user: "no se puede atacar los dos a la vez en shadow?").** SÍ se puede y es MÁS limpio: en vez de un setup angosto, se tagea CADA señal de structure que se ejecuta con los toques de su nivel EN EL MOMENTO (`level_quality_log`, join por strategy_id a trade_archive). NO cambia comportamiento (solo loguea). Mide sobre TODA la señal viva (mucha más data que el pullback) si nivel-validado (≥2 toques, como SMC) separa WR del ruido (fractal 2-vecinos). Si separa → justifica un filtro de calidad-de-nivel que mejora TODOS los setups de structure (no solo un detector). `technical.py` enriquece cada señal con `level_touches`; el scan loop lo loguea tras crear la estrategia. Corre junto al pullback_quality, sin chocar.
- [x] ✅ **Vie 26 Jun (CHECKPOINT) — corrido el DOM 28 Jun** (el viernes quedó sin hacer; se ejecutó con 2 días de atraso). **RESULTADO: NINGÚN cambio de código — y eso es correcto, la data de una semana no justifica tocar nada (la metodología funcionando, no inacción).**
  - **Semana 22-26 Jun MEJORÓ fuerte pero sigue en rojo:** 31 trades, WR 42%, **−$16.96** vs semana previa 15-19 (40 trades, WR 18%, −$52.84). WR más que se duplicó, pérdida cortada a un tercio.
  - **⚠️ La mejora es VARIANZA de m15, no probada.** Por track esta semana: m15 +$9.08 (10/18, 56%) · h1 +$1.86 · structure −$3.7 · smc −$7.4 · **news 0/5 −$16.8** (se comió toda la ganancia de m15). Secuencia m15: antes-15jun 34% WR → **15-19 jun 0% (0/17, −$40)** → 22-26 **56% (+$9)**. Salto 0%→56% en semanas consecutivas con n~17 = ruido + cambio de régimen (el EUR/USD dejó de caer). m15 lifetime desde 10-jun sigue **−$72.78**. NO tocar por una buena semana.
  - **🔴 news = fuga estructural CONFIRMADA** (problema #3): desde 10-jun 21% WR, **−$39.84 en 28 trades** — el peor track con data suficiente. Esta semana 5/5 fueron PUT y perdieron chico (−2 a −7) en una semana de "Dollar Jumps to Highest Since November" → dirección PUT correcta (dólar subió = EUR/USD bajó) pero perdió igual = otra vez **"perdemos estando bien parados"** (entry/management) + evaluation gap del LLM. La conf de news la pone el LLM (gated). Candidato a medir tasa de error del news LLM (backlog).
  - **① Veredicto PM → KEEP (no revertir).** La extensión post-expiry (lo nuevo de v3.40.11) se pagó: **CLOSE_MAXHOLD +$25.63** (11 trades). Los **34 CLOSE_PROTECT** cortaron perdedores (−$76.4 total = sangrías acotadas, su trabajo defensivo). Único punto raro: **CLOSE_PROFIT 5 trades −$3.95** (profit-lock neto negativo, n chico — VIGILAR si crece). — **⚠️ ALARMA RETIRADA el 8-ago: NO reproduce.** Esas mismas 5 estrategias (#548, #621, #661, #678, #709) suman **+$9,67** con `mt5_pnl` REAL del broker, y el bucket completo hoy es **n=13, 12W/1L, +$28,97** (los cierres realmente ejecutados: **n=9, 9/9 wins, +$23,52**). El "profit-lock neto negativo" que se venía vigilando no existía. *Pero ese +$28,97 tampoco prueba que el mecanismo aporte valor: es casi **tautológico** — solo dispara sobre trades que YA llegaron al 60% del TP y los cierra al 60% del pico ⇒ cualquier regla así muestra ~100% WR. El gate lo rechaza correctamente (n=13 → sig=False pese a p=0,0001). El contrafáctico real (¿esos 9 hubieran ido al TP o se daban vuelta?) exige velas = no medible con las reglas de la casa.*
  - **② Calibración empírica ~150 limpios → POSPUESTA a ~10 Jul.** Censo limpio real desde 10-jun = **n=99** (la estimación "10/día" era optimista; real ~7/día). Recién llega a 150 cerca del 10-jul.
  - **③ 2da lectura cooldown → HECHA el DOM 28 (MT5 reconectó a la noche; AIdan cerrado para correr el script standalone, re-levantado después).** **RE-VALIDADO por 3ra vez:** ≤5min n=76 WR **24% vs 36%** baseline, **p=0.012, CI [16%,34%] no cruza** = SIGNIFICATIVO (consistente con 10-jun p=0.010 y 12-jun p=0.009). La toxicidad sigue terminando exacto a los ~5min (≤2min, ≤10min, ≤15min todos RUIDO). El gate ya está activo (v3.40.15) → **NINGÚN cambio, solo confirmación.** Sospechoso B (bias stale) RE-REFUTADO otra vez (p=0.497, RUIDO). Sospechoso C reconfirma "entra MAL no tarde" (402 fills inmediatos al precio planeado = 36% WR baseline). Universo broker = 681 pos / −$582, balance demo **$657.81** (de $726.97 el 14-jun = el sangrado de las semanas rojas).
  - **Scorer pullback shadow:** corrido DOM 28 → n=9 (M5 7 + M15 2), avg_fav 4.2p M5 — **insuficiente (necesita ~2-3 sem), sin comparación pareada vs breakdown aún.** Level-quality log: 22 filas. Ambos siguen acumulando.
- [x] ✅ **Vie 3 Jul (CHECKPOINT) — HECHO. Cambio de enfoque pedido por el user: "mejorar, no sacar".** El reflejo de la metodología venía siendo "medir → si no es significativo, no tocar" = sesgo a la inacción/recorte; el user lo marcó ("meses de pruebas y se sacan cosas en lugar de mejorarlas, es cuenta demo, hay que MEJORAR"). Análisis profundo de los 4 tracks sobre data limpia (n=123 desde 10-jun):
  - **Semana 27jun-3jul roja: −$19.10, WR 31%** (peor que previa −$16.96/42%). news 0/6 −$15.50 otra vez; m15 volvió a bajar (40%, confirma que el +$9 previo era VARIANZA); structure +$1.30 único verde.
  - **🔑 EL DIAGNÓSTICO VIEJO ("expiry mata trades") ESTÁ MUERTO en data limpia:** de 123 trades solo **6 expiran**. La realidad: **83 (67%) hit STOP LOSS**, 34 TP. El problema es la ENTRADA, no la salida.
  - **🔑 HALLAZGO GRANDE (mejora, no recorte): AIdan gana en EXPANSIÓN y muere en CHOP.** Crucé por ATR-14 al entrar (`avg_range_pips`, pre-trade, sin lookahead): **chop (ATR 3-8p): n=58, 16% WR, −$124** (casi TODA la pérdida, p=0.0002, sobrevive Bonferroni) vs **expansión (ATR>8p): n=35, 46% WR, +$0.6**. En m15 (el volumen): chop 13%/−$71 vs vol 54%/+$5 (fisher p=0.0016). **El 57% de los 83 SL-hit están en el chop.** Es un sistema breakout/momentum: el breakout sigue en expansión (edge real) y es FALSO en chop (serrucha → toca el stop). No le falta filtro, le falta saber en qué régimen está.
  - **Confianza NO invertida en data limpia** (desmiente miedo viejo): conf 90+ = 46% WR (el MEJOR bucket), 80+ avg win 12.6p; los flojos son 60-79 (79% del volumen = correlaciona con chop). Se puede volver a confiar en conf alta.
  - **Decisión de eventos (lo agendado):** SKIP straddle. Shadow 0 filas en 3 sem; el debug (v3.40.16) dice por qué: detecta el evento pero SIEMPRE muere en `sr_zero` (get_market_state devuelve support=0/resistance=0), y los eventos son todos speeches Medium (Trump/Lagarde), no releases. No vale arreglar sr_zero para activar una familia perdedora (news, el track reactivo-a-eventos que YA existe, es la peor fuga). Momentum post-release tampoco (sin data).
  - **[EN CURSO] v3.45.0 — FADE-EN-CHOP en SHADOW (la mejora, construida hoy con OK del user).** En vez de SACAR los ~58 trades de chop, convertirlos: en chop el breakout es falso → lógica INVERSA (fadear el extremo de un nivel validado ≥2 toques + vela de rechazo; PUT en resistencia / CALL en soporte, ambas direcciones, SIN exigir htf porque es rango). `FADE_CHOP_MODE=shadow` (default): loguea a `fade_chop_shadow_log` con ATR+snapshot SIN operar (vivo intacto). Scorer `tools/score_fade_chop_shadow.py` mide FORWARD favorable Y adverso (un fade puede ir a favor y darse vuelta). Banda chop ATR 3-8p (tuneable, se loguea el ATR crudo). Activar solo tras comparación pareada vs breakout en el mismo régimen + gate. **Caveat:** parte del split vol/chop puede arrastrar el régimen del período → por eso shadow forward, no hardcode.
- [x] ✅ **Vie 10 Jul — NO se registró** (la semana 6-12 jul tuvo solo 7 trades; el 17-jul lo absorbió). Sin lectura formal.
- [x] ✅ **Vie 17 Jul (CHECKPOINT GRANDE) — HECHO. Resultado: AIdan en su MEJOR momento; NINGÚN cambio de código (correcto).** Balance **$672.64** (de ~$657.81 el 28-jun). Data limpia n=164 desde 10-jun.
  - **🟢 1ra semana VERDE de toda la data limpia: 13-17 jul = +$36.92, WR 41%, n=34.** Motor: **m15 +$39.50 (50% WR, n=20)**. El sangrado PARÓ: **post-fixes (≥20 jun) n=93 WR 40% −$2.13 (breakeven)** vs **pre-fixes (10-19 jun) n=71 WR 20% −$118.80**. m15 post-fixes: n=52, WR 50%, **+$47.66** = el único track que gana. *Caveat honesto:* parte de la mejora es régimen (el crash de 160p del EUR/USD cayó en la ventana pre-fixes 15-19 jun). Pero esta semana el mercado estuvo LATERAL (1.142→1.144) y ganó igual — el clima donde "debería" sufrir.
  - **🔑 EL "CHOP TÓXICO" (base del 3-jul) SE VE DEPENDIENTE DEL RÉGIMEN.** Esta semana el **chop productivo GANÓ +$28.74** (n=24, 42% WR) — lo OPUESTO al hallazgo del 3-jul (chop −$124). Full census chop sigue −$96.78 (n=88, 24%) pero la tesis "en chop el breakout es falso" quedó en duda.
  - **fade-chop shadow (v3.45.0) → REFUTADO.** n=57 scoreadas: avg_fav **+1.0p** vs avg_adv **9.2p** (fadear te pasa por arriba 9 a 1); **se dio vuelta entre n=25 y n=57** (antes sup pésimo, después res pésimo = inestable). + el chop productivo ganó (nada que "convertir"). **Decisión user: dejarlo 1 checkpoint más** (es no-op, no cuesta nada) → **re-leer ~24-jul**; la lean es "no sirve". pullback shadow: n=13, ruido (como se predijo). level-quality: **no existen niveles de <5 toques** → el "fractal de ruido 2-vecinos" del brain-review era MITO, no hay filtro que aplicar (niveles validados +$38.87/46% = toda la población de structure).
  - **h1 = loser crónico confirmado con data:** SL clavado en el floor 40p en el **100%** de los trades (ATR·0.8 nunca supera 40; ATR medio h1 = 12.9p); breakout dispara a 7p = media vela H1 = sub-vela. Lifetime −$42 (36% WR), post-fixes −$6 (18%, n=11). Problema = calidad de ENTRADA (el SL/TP ya se arregló v3.40.18).
  - **🎯 GRUPO B — diseñado (workflow diseño+verificación adversarial) y MEDIDO (Paso 0), NO se construyó shadow.** El workflow **auto-refutó la idea original "escalar constantes por ATR hacia arriba"**: entrar MÁS LEJOS del nivel = PEOR WR (evidencia v3.13.0: 1-2p 80% / 3-5p 38% / 5-7p 25%, + el auto_tuner ya bajó breakout_dist_max 15→7 solo = prefiere TIGHT). El **Paso 0** (retro read-only `tools/measure_dist_to_level.py`, level_quality_log ⋈ trade_archive por strategy_id, P&L REAL, sin shadow) confirmó: **el lever es la entrada PEGADA al nivel** — ≤0.5 ATR = **65% WR, +$24.2, p=0.006** (celda estrella) vs >1 ATR = ~37% (baseline, negativo); en m15 dist≤3p 64% / 3-7p 54% / >7p 35%. **PERO n=23 < gate 25 (a 2 trades).** m15 quizá gana PORQUE su ventana quedó accidentalmente tight (~1 ATR). **No hace falta shadow: el edge ya se mide con P&L real vía level_quality_log** (el shadow solo servía para el "would-add"/widen, muerto). **Decisión user: esperar ~1 sem y re-medir ~24-jul**; si la celda pegada pasa el gate (n≥25, CI que no cruza) → proponer **`breakout_dist_max` relativo-a-ATR y MÁS TIGHT** (~1 ATR: aprieta M5, deja m15 casi igual, alineado con lo que el tuner ya prefiere). Es "mejorar" quedándose con las entradas buenas.
- [x] ✅ **Vie 24 Jul (CHECKPOINT) — HECHO. La celda "entrada pegada" PASÓ EL GATE → se implementó el tighten (v3.46.0, con OK del user).**
  - **🎯 Distancia-al-nivel — PASÓ (n=93 joinable, touches≥2):** `≤0.5 ATR = n=26, WR 58%, p=0.028, CI [39-74%] NO cruza baseline → SIGNIFICATIVO`. El 17-jul estaba a 2 trades (n=23). Por PnL: **≤1 ATR = +$42.5 (58 trades) vs >1 ATR = −$11.9 (35 trades)** → el cap a 1 ATR corta la cola perdedora dejando la zona que gana. Raw m15 confirma (≤3p 58% / 3-7p 46% +$27.7 / >7p 35%). La cola >1 ATR la puebla sobre todo M5 (ATR chico → 7p = varios ATR = tardío).
  - **✅ IMPLEMENTADO v3.46.0 (tighten relativo-a-ATR).** `technical.py` líneas breakout/breakdown: `dist_cap(fixed) = min(fixed, max(avg_range*MULT, FLOOR))` con `BREAKOUT_DIST_ATR_MULT=1.0`, `BREAKOUT_DIST_ATR_FLOOR=2.0` (Config, env). **MONOTÓNICO** (min() al final → nunca afloja vs los 7p fijos, solo aprieta). Efecto: M5 se aprieta a su ATR (2-6p), **m15/h1 quedan en 7p** (el `min` los deja → el motor m15 NO se toca; su zona rentable ya vive ≤7p). MULT=0 = apagado (reversa por env sin rebuild). Verificado: py_compile OK, fórmula testeada por track, MT5 reconectó ($661.44, 0 pos). **MEDIR FORWARD 1-2 sem:** ¿M5 mejora sin caer feo la frecuencia? Si no → MULT=0 y revierte.
  - **fade-chop 2da lectura — REFUTADO otra vez (n=91):** res_M15 fav 0.0p vs adv 12.0p, res_M5 fav 1.0p vs adv 8.8p, sup marginal (fav≈adv). Fadear te pasan por arriba, la resistencia es lo peor. **✅ APAGADO 28-jul (v3.47.1, `FADE_CHOP_MODE` default `off`)** tras 3ra lectura (n=102: res_M15 fav 0.8p vs adv 10.8p, res_M5 1.0 vs 9.1, sup fav≈adv) — refutado 3×, no se activa. pullback: ruido (n=21), como se predijo.
  - **Breakeven post-fixes se SOSTUVO** pero la semana volvió al rojo: post-fixes ≥20-jun **n=115, WR 37%, −$6.83** (~flat en 6 semanas). Semana 13-jul +$36.92 (verde) → semana 20-jul −$4.70 (23% WR, n=22) = la verde era en parte variancia/régimen (como se avisó). Balance $672.64 (17-jul) → **$661.44** (−$11.20). Tracks post-fixes: **m15 +$40.38 (motor)** · structure +$3.70 · h1 −$7.61 · smc −$12.60 · **news −$30.70 (fuga #1, se come lo de m15)**.
- [x] ✅ **news LLM MEDIDO (24-jul, `tools/measure_news_llm_error.py`, diseñado por workflow adversarial) → VEREDICTO: CERO habilidad direccional.** Sobre 581 alertas direccionales ancladas (raw 753, dedup 749, −166 sin price, −2 tz): la **discriminación P(subió|CALL)−P(subió|PUT) = −1pp, Fisher p=0.92 = RUIDO PURO** — el LLM dice CALL y sube 37%; dice PUT y sube 37% (idéntico) → su dirección NO lleva información. + **ANTI-SKILL vs el drift** (hit global 53% vs "siempre la dirección dominante" 63%, `verify_finding` SIGNIFICATIVO worse). + tradeabilidad net +0.5p bruto, **−0.8p tras comisión**. Confirma la hipótesis de la literatura (lee TONO no IMPACTO, ~25pp perdidos → acá edge=0). Hint débil: HARD_DATA discrimina +10pp vs TONE +2pp (n=70, no significativo). El "ya-en-precio" 21%. **DECISIÓN PENDIENTE del user (mejorar-no-sacar vs cero-skill probado):** gatear news a solo-dato-duro-con-sorpresa / apagar la ejecución direccional de news / dejarlo y re-medir. La conf de news la pone el LLM (mal calibrada) → subir el piso no sirvió antes.
- [x] ✅ **news — INTENTO DE ARREGLO aplicado (v3.47.0, con OK "intentá arreglarlo").** Investigado el POR QUÉ: mayormente estructural (57% acierto en movers ≥5p = ≈moneda) + misread sistemático BCE dovish→CALL (6/9, abril-jul, ACTUAL; el prompt tenía la regla pero la IA la salteaba). Fix = prompt POSTURA-PRIMERO (PASO 3 stance HAWKISH/DOVISH + advertencia "hike≠hawkish" + few-shot + campo `stance`; PASO 4 dirección derivada con coherencia obligatoria). Sanity 3/3 en LLM real (dovish que fallaba → PUT ok). A/B offline imposible (rate-limit Groq compartido con exe). **NO vuelve rentable news** (edge direccional sigue ~0), solo arregla la lectura.
- [x] ✅ **Medir FORWARD — HECHO 5 Ago. Resultado: NINGUNA de las dos mediciones concluye, y hay 1 hallazgo nuevo que sí.**
  - **(1) tighten v3.46.0 → SIN VEREDICTO por falta de volumen, con una señal de alarma.** El track objetivo (`structure`/M5) hizo **3 trades en 10 días** post-tighten (WR 100%, +$4.20) vs 20 en las 5 semanas previas. La frecuencia cayó de **2,00 → 1,00 trades/día-con-trades = −50%**, exactamente el riesgo que se anotó al shipearlo. Los controles quedaron intactos como se predijo (m15 dist/ATR mediana 0,70→0,71; h1 0,59→0,57) ⇒ el filtro hace lo que dice, solo aprieta M5. **No se revierte todavía** (n=3 no dice nada del WR), pero **si en 2 semanas M5 sigue en ~1/día sin ganancia clara → `BREAKOUT_DIST_ATR_MULT=0`** (reversa por env, sin rebuild).
  - **⚠️ Y la celda que justificó el cambio SE DEGRADÓ:** `≤0.5 ATR` pasó de n=26/58% WR/p=0,028 (24-jul, pasaba el gate) a **n=39/51% WR/p=0,054, CI [36,2–66,1%] que ya cruza el baseline = RUIDO**. Reversión a la media clásica: el hallazgo que apenas pasó el gate no se sostuvo al sumar 13 trades. Lección para el registro: **pasar el gate por poco ≠ hallazgo robusto** — el gate es piso, no garantía.
  - **(2) fix news v3.47.0 → NO JUZGABLE aún.** Solo **43 alertas direccionales** post-fix (25-jul→3-ago) y **2 casos con postura** en la muestra — los dos razonados bien (Fed dovish→CALL ✔, BOE dovish→euro fuerte→CALL ✔), y **cero casos de BCE dovish**, que era justo el misread que el fix apuntaba. La medición global sigue diciendo lo mismo de siempre: discriminación **−11 pp (Fisher p=0,28 = ruido)** y **ANTI-SKILL vs el drift** (hit 43% vs 59% de la mejor constante, significativo *worse*). *Caveat de medición:* la muestra anclada se encogió a 158 (de 581 el 24-jul) por `tz_unreconciled=457` — artefacto del fetch de velas, no cambio de data.
  - **🔴 Y el track news sigue siendo la fuga #1:** post-tighten n=7, WR 43%, **−$10,10**; acumulado post-fixes **23 trades, −$40,80**. Se come lo que gana m15. La decisión pendiente (apagar la ejecución direccional de news) **sigue pendiente y ya lleva 2 semanas sin evidencia a favor de dejarlo**.
  - **Contexto de la ventana:** post-tighten (25-jul→3-ago) n=39, **WR 49%** (vs 37% pre), PnL **−$10,94**. WR arriba y plata abajo = las pérdidas son más grandes que las ganancias en esta ventana. Semanas: W31 n=32 WR 53% −$1,38 · W32 n=7 WR 29% −$9,56. Balance **$650,56** (de $661,44 el 24-jul).
  - **Shadows (regla de shadow):** pullback n=29 → sigue **RUIDO** como se predijo (el bolsillo grande `bear_M5` n=19 avg_fav 4,3p, debajo del umbral de 6p; 7/19 llegan a 6p). fade-chop apagado desde v3.47.1, sin filas nuevas.

- [x] ✅ **IMPLEMENTADO 5 Ago con OK del user — v3.50.0: castigo de confianza por NIVEL FLOJO en m15.** `technical.py`, en el mismo lugar donde ya se taggean los toques: si `1 ≤ level_touches ≤ 10` → `confidence −= 15`, y **se re-aplica el piso `min_confidence`** ahí mismo (el gate original corre antes, cuando la confianza todavía no tenía el castigo — sin el re-filtro una señal castigada a 53 salía igual). Config: `LEVEL_QUALITY_PENALTY=15`, `LEVEL_QUALITY_MAX_TOUCHES=10`, `LEVEL_QUALITY_TRACKS=M15` (env; `PENALTY=0` apaga sin rebuild). **Solo M15**: es donde se midió; M5 ya tiene la frecuencia golpeada por el tighten (3 trades en 10 días) y su muestra joinable es n=22, H1 n=20 → sumarles un filtro no medido sería apilar recortes a ciegas.
  - **⚠️ Lo que el castigo realmente logra (probado contra los 10 flojos reales, no asumido): bloquea 4/10** (los de conf<75) y evita **~$11,3 de los −$29,7**. **Se le ESCAPAN los dos peores**, que entraban con conf 90 y 83 (#683 −4,69 y #834 −6,40). Con −25 bloquearía 8/10 (~$25,2) pero eso ya es casi un block de la familia y a n=10 no hay evidencia para tanto → se eligió la versión conservadora. **Subir a 25 es una env var** si el forward confirma que los flojos de conf alta siguen perdiendo. *El "$11,3 evitado" es indicativo, NO un contrafáctico*: bloquear una señal cambia el estado posterior (cooldown, slots de posición).
  - **MEDIR FORWARD ~2 sem (≈19 Ago):** ¿la frecuencia de m15 cayó más que el ~12% estimado? ¿mejoró el WR del resto? ¿cuántos DROP loguea (`Level quality [M15]: DROP`)?
  - Verificado: 6 casos de test (los 10 flojos reales, nivel validado intacto, `touches=0` sin castigo, M5/H1 intactos, `PENALTY=0` apaga, método real compila), 75 tests, rebuild v3.50.0 en `/version`, MT5 $650,56.
- [x] ✅ **~~PROPUESTA~~ (era: pedía OK): penalizar la confianza cuando el NIVEL es flojo en m15.** → implementado arriba. Evidencia que la respaldó: El criterio pre-declarado el 31-jul se cumplió: llegó a **n=10** (era 6), sigue en **20% WR** y **−$29,70** — **9 de 10 pierden**. Contra `>10 toques = n=73, 47% WR, +$61,70`. Prevalencia **12%** (10/83), mediana 20 toques ⇒ cortarlo cuesta poca frecuencia. **NO pasa el gate formal** (n=10 < 25, p=0,21) y por prevalencia quizá **nunca** lo pase ⇒ como se acordó, decidir con juicio calibrado. Dato que ayuda: los flojos entran con **confianza ALTA** (90, 90, 83, 81, 78, 75, 73, 73, 68, 60) ⇒ un castigo de ~−15 con el piso 60 filtra los de conf<75 sin apagar la familia. *Contra:* n=10, y `level_touches` usa tolerancia `max(2, ATR×0,5)` ⇒ correlaciona con volatilidad, no es calidad pura. **No implementado, espera tu OK.**
- [x] ✅ **PROFIT-LOCK del PM en h1 — MEDIDO 8 Ago (workflow 5 ángulos + 3 refutadores adversariales) → NO SE IMPLEMENTA. Unanimidad: 5/5 mediciones lo refutan, 3/3 refutadores dicen `no_implementar`.** El user lo pidió tras v3.52.0 (el otro umbral muerto de h1: arma a 32p, HWM máx 26,3p). **La razón principal no es que sea malo — es REDUNDANTE:** una vez que existe el BE de v3.52.0, su marginal es **+2,5 pips en 34 trades y ~2,5 meses (~$0,55)**, y el **signo se da vuelta** según la resolución del muestreo (stride 3 → −5,6p · stride 2 → +2,4p). Indistinguible de cero. **Y lo que compra es de mala calidad:** corta los 3 mejores h1 de la historia (#835 +16,5→+11,2 · #851 +10,4→+3,9 · #844 +6,5→+3,1 = **−15,2p**) para rescatar migajas sobre trades que el BE ya salva. **Mecánica:** el profit-lock **cierra** la posición (trunca el upside), el BE solo **mueve el stop** (protege y deja correr) — en un TF cuyo ruido mide lo mismo que el umbral de armado, una regla de retroceso porcentual dispara sobre ruido. Control cruzado que lo sella: el mismo cap aplicado a todos los tracks habría **destruido m15 (−71,8p)**, cortando 4 del top-10 de ganadores. **Alternativas evaluadas y también descartadas:** capear el **trailing** en vez del profit-lock (el que mejor rankeó: +17,7p con mecha 0, pero **+0,2p con mecha 2p** en mi propia simulación, más pesimista que la del agente) · **TP más chico** (no monotónico: 8p +21,3 · 10p +30,8 · 12p +8,8 = firma de overfit; y out-of-sample en m15 da −24,7p = "vendé a tus ganadores temprano") · **tocar `KEEP`** (converge al trailing hecho mal: discreto, cada 15s, cerrando a mercado) · **MAX_HOLD/expiry** (refutado, ver Simpson abajo). **Medibilidad de fondo:** cualquiera de estos dispara en ~6/34 trades ⇒ llegar a n=25 tomaría ~9 meses ⇒ **nunca va a pasar el gate**; se decide con juicio calibrado o no se decide. **Dato honesto sobre h1 que salió de acá: su SL muerto de 40p NO cuesta plata, LIMITA EL DAÑO** — como `lote = riesgo$/(SL×10)`, ese SL grande hace que los pips de h1 sean los más baratos del sistema (~6x vs structure/news); "arreglar" la geometría triplicaría el lote sobre un track cuyos pips son negativos (−41,2p en 34 trades). **No tocar la geometría de h1 hasta que su edge sea positivo.**
- [x] ✅ **COSTO DEL BREAK-EVEN — MEDIDO 10 Ago (`tools/measure_be_cost.py`) → NO SE TOCA, y la medición REFUTÓ mi propia hipótesis.** Origen: el user vio un SMC ganador cerrado en pérdida (#882: llegó a +4,4p, el BE armó, el precio retrocedió y tocó el stop de +1p; **después alcanzó el TP** ⇒ el BE dejó **+5,7p** sobre la mesa). Yo planteé que el stop de BE quedaba "dentro del ruido" (arma a 50% del TP y deja solo ~1,85p de aire con spread ~1p) y que eso nos costaba plata. **La data dice que no.** Post-fixes (n=171 con pico registrado): **cortados por el BE n=12 → +$2,41** (breakeven, NO pérdida) · **armaron BE y siguieron n=32 → +$142,52** · **nunca armaron BE n=127 → −$167,76**. Lifetime igual: 22 cortados = +$1,95. **🔑 EL HALLAZGO GRANDE ES OTRO Y ES MÁS IMPORTANTE: el 74% de los trades (127/171) nunca llega a estar a mitad de camino del TP, y ahí vive el 100% de la pérdida.** Llegar a estar decentemente en verde es un discriminador brutal ⇒ **el problema es de ENTRADA, no de gestión de salidas** (rima exacto con el veredicto del 12-jun "entra mal, no tarde"). Tocar el BE sería mover la perilla equivocada. Lo que sí se confirmó es la MECÁNICA: al cortarse, el pico era el **51% del TP** (mediana) = el BE arma en su umbral y corta casi enseguida. Bolsillo a seguir mirando: **m15** (3 trades post-fixes, 20,1p devueltos, mediana 9,6p — #697 devolvió 11,6p de un TP de 25p), n=3 no alcanza para nada. h1 post-v3.52.0: el único cortado (#862) devolvió 1,5p ⇒ sin alarma temprana. **Límites del medidor, documentados adentro:** el "pico devuelto" solo es plata perdida si el precio siguió a favor (verificado en 2 de 22: #658 y #882) — exige velas posteriores, no se mide; y **no se mide lo que el BE SALVA** ⇒ el número es la mitad visible de la balanza, nunca un neto. *Trampa anotada: subir `BE_OFFSET` EMPEORA (más offset a favor = stop más cerca del precio = se toca antes). La perilla correcta sería armar más tarde con un colchón mínimo en pips absolutos, no en % del TP — pero no hay evidencia que lo justifique.*
- [x] ✅ **P&L fantasma del eval de arranque — CERRADO en v3.51.1, y la causa era OTRA (mejor) que la que yo había anotado.** Mi hipótesis del 7-ago era "la posición cerró en el broker con el exe apagado y el startup eval la archiva antes de tener el P&L real". **Falsa.** Al leer los logs de los 2 casos: **ninguna de las dos estrategias se ejecutó jamás.** #865 lo frenó el **cooldown** (`COOLDOWN post-perdida: skip #865`) y #881 el gate de cierre de mercado (`MT5 blocked: market closing soon`) — cero ticket, cero deal, cero posición. `get_strategies_pending_evaluation()` **no filtra por ejecución**, así que el eval por precio las trataba como trades y `archive_trade` las metía en la tabla de plata con los pips **teóricos** del TP/SL nominal. **22 de 600 filas, ~2 por semana parejo desde abril** (abr 2 · jun 9 · jul 9 · ago 2) — el "ritmo que subió" era ruido de muestreo, siempre fue el mismo goteo. Fix = guard en `archive_trade` (UN solo lugar, cubre los 3 callers): sin `mt5_ticket` y sin `mt5_pnl` no entra al archivo. La evaluación a nivel **señal** (`strategy_results`) no cambia — ahí una señal no operada SÍ corresponde. **Histórico intacto** (regla de la casa): las 22 siguen y siguen excluidas por `mt5_pnl IS NOT NULL`.
- [x] ✅ **VIE 31 JUL — RE-MEDIDO el 5 Ago** (dos días tarde). Resultado arriba: n=6→**10**, 20% WR, −$29,70, 9/10 pierden ⇒ el criterio pre-declarado se cumplió y quedó como **propuesta abierta** (ver bloque 🟡). Detalle original del item:
- [x] ✅ **[EL #1 — HECHO v3.40.18, 17 Jun] TP escalado por timeframe/expiry.** El user cuestionó (con razón) por qué esperar a medir si el R:R roto es hecho de código, no estadística → adelantado (no se esperó al 26 Jun). `technical.py:1427`: `tp_cap = ATR×cap_mult` con `cap_mult = clamp(2.0 + expiry_min/60, 2.0, 5.0)` (M5 2.25×, M15 2.75×, H1 5×) en vez del fijo `ATR×2`; bounds piso R:R 1.2 (NUNCA peor que antes) + techo 2.5 + nunca > nominal. **El SL/riesgo NO cambia, solo crece el objetivo.** Verificado con la función real: **H1 1:1.2→1:2.5** (el peor track), M5 1:1.2→1:1.9, M15 sin regresión (piso lo protege en ATR bajo; su límite es el SL floor 15p = el sgte lever). Simulador cazó y corrigió un bug de mi 1ra versión (rompía M15 a 1:0.73). Mide su efecto vs cooldown+PM queda mezclado — trade aceptado (esos baselines corrían sobre lógica rota igual).
- [x] ✅ **Grupo A de la revisión — HECHO (v3.40.17, vivo idéntico, solo mata bugs silenciosos):** (1) `import random` muerto removido de dynamic_conf (jitter ya removido v3.39.1); (2) **SMC reversal-en-zona estaba MUERTO** por la clase-de-bug-M15: el gate leía `setup.get('htf_bias')` (clave inexistente — la real era `htf_trend`) → caía al bias ORIGINAL → bloqueaba el flip siempre → **el PF 1.14 de SMC NO viene de "paciencia/reversal" sino solo de los SMC a-favor-de-HTF**. Fix: alias `htf_bias` + flag `reversal` explícito en `smc.py`; el reversal queda **APAGADO explícitamente** en el gate (1 línea, vivo idéntico) pendiente de medición (es contra-tendencia, sin evidencia). **NO incluidos en A (pasan a B, medido): trend-desync** (el gate SIM-A usa MA9/21 vs el setup usa MTF-M5 — tocar el gate del único +EV sin re-derivar la matriz = riesgo) y **demand/supply sin enforce en `_find_active_zone`** (cambia qué SMC dispara).

- [x] ✅ **(a) cap de lote pre_planned — HECHO v3.40.18** (batcheado con el TP): `get_active_unexecuted_strategies` ahora devuelve `trigger_type` (`db.py:2002`+dict) → el retry ya puede aplicar el cap 0.05. Additivo, no-op al balance actual.
- [x] ✅ **(b) PM marca `executed=1` sin mandar orden — HECHO v3.40.19.** `close_strategy_position(sid, return_sent_flag=True)` ahora devuelve `(price, did_send)`; el PM marca `executed=1` SOLO si `did_send` (mandó la orden), no cuando la posición ya estaba cerrada por TP/SL. Hecho con **parámetro opcional** → los otros 2 callers (in-loop eval 2943, late-close 3196) reciben el float de siempre, cero cambio. Limpia la lectura del experimento PM (26 jun).
- [x] ✅ **[BUG, lo cazó el user en #658] BE offset no cubría la comisión — HECHO v3.40.19.** `BE_OFFSET_PIPS` 0.5→1.0p. El "break-even" cerraba NETO negativo (−0.20 en #658) porque 0.5p < comisión real ~0.8p (round-turn IC + spread salida). El comentario decía "cubrir comisión" pero el valor no lo hacía. Ahora el BE cierra neto ≥0. Trade-off: el stop de BE salta un toque más seguido, pero ya no en rojo (que era su propósito). *(Caso #658: PUT con señal CORRECTA — el precio terminó cayendo al TP — pero el BE lo cortó en el retroceso a −0.20 y después corrió sin nosotros. El user pidió relabelearlo a WIN; NO se hizo: el realizado fue −0.20, relabelear = contaminar el aprendizaje con un contrafáctico (regla broker-truth). El dato honesto es justo el que muestra "el management corta ganadores".)*
- [x] ✅ **[MED-HIGH] Late-close pisaba al Position Manager** — RESUELTO v3.40.11 (`AIdan_TodoEnUno.py` late-close): con `POSITION_MANAGER_MODE=active` ya NO cierra por `'expired'` — gobiernan PM (R2/R4 MAX_HOLD 90/120/240min) + SL/TP duro; `auto_win`/`auto_loss` se siguen cerrando; en mode log/off sin cambios. Evidencia que lo motivó: cerró #609/#613/#614 a segundos del expiry pisando HOLDs del PM, y cortó al ganador #603 (+5.8p de 17p TP). **⚠️ EXPERIMENTO PM RE-BASELINEADO desde 10 Jun (v3.40.11):** lo medido del 5-10 Jun era solo la mitad defensiva (la extensión estaba muerta); ahora por primera vez los trades pueden vivir más allá del expiry hasta MAX_HOLD. Medir ~2 sem desde acá. Riesgo aceptado: si el thread del PM muriera (tiene guard FATAL v3.40.3), la salida es solo SL/TP (diseño: "SL/TP duro = única salida forzada").
- [x] ✅ **[MED-HIGH] entry_context m15/h1 doble-JSON-encodeado** — RESUELTO v3.40.11: los 2 call sites (`AIdan_TodoEnUno.py` m15/h1) pasan dict crudo (sin `json.dumps`); `get_entry_context` además hardened (doble-loads si encuentra str → filas viejas no crashean). El archive directo vuelve a correr para m15/h1 → features enriched dejan de salir vacías → la data limpia v3.40.x deja de contaminarse. Testeado funcional (fila vieja doble + fila nueva → ambas dict).
- [x] ✅ **[MED] P&L del header del dashboard era FALSO (caso "+6.87 en día de −33", 11 Jun, lo cazó el user)** — RESUELTO v3.40.13: `get_mt5_daily_pnl` sumaba SOLO el buffer vivo `auto_strategies` (rotativo ~8 filas) → al archivarse/purgarse los perdedores del día, desaparecían del número y quedaba la suma de los sobrevivientes (justo los ganadores) → "+6.87" en un día de −33. Fix: el dashboard ahora usa **broker-truth** (`MT5Executor.get_daily_pnl`: deals MT5 del día AR, comisiones de entrada+salida incluidas, offset servidor derivado en vivo del tick → robusto a DST) con fallback DB corregido (UNION con archive por `created_at`, dedup). Verificado en vivo: header pasó de +6.87 → −33.36 (= historial MT5). Lección repetida: TODA métrica mostrada debe salir del broker o de la unión completa, nunca del buffer vivo. el PM calculaba la edad del trade desde `created_at`, que para pre-plans es cuando se PLANEÓ (día anterior), no cuando se llenó la orden → "985min en trade" a los 20s del fill → CLOSE_MAXHOLD ejecutado ANTES del evento PPI para el que existía (el primer pre-plan activado con PM active lo expuso; irónicamente ese cierre ahorró plata — el rally post-PPI lo habría llevado al SL — pero hacía inútiles a TODOS los pre-plans). Fix: edad = `expires_at − expiry_minutes` (expires_at se re-escribe a activación+expiry al activarse; para trades normales da exactamente created_at; guard `>` + fallback a created_at si parse raro). Testeado: #615 real → 0.1min (antes 985), trade normal idéntico, expires malformado no crashea.
- [x] ✅ **[LOW] Timestamps UTC en logs** — RESUELTO v3.40.11: `position_manager_log`, `bounce_entry_log` y `calendar_shadow_log` ahora sellan `created_at` con `now_ar()` explícito (filas previas quedan UTC — cutover 10 Jun ~19:00 AR, para forense histórico tenerlo en cuenta). Idem inferencia trigger del instant-eval: ahora reconoce `[M15-STRUCT]`/`[H1-STRUCT]` (tags exactos, un title m15 puede MENCIONAR 'H1').
- [x] ✅ **PM sanity read (2 días de re-baseline)**: la MECÁNICA probada — 12/23 cierres se extendieron de verdad post-expiry; profit-lock #621 +$4.52; MAXHOLD #638 +$2.34 (antes moría al expiry); 10/11 PROTECTs cortaron antes del SL teórico (~113p cota superior, ⚠️ 34% de eso es UN solo trade H1 #637 — citar siempre con caveat). Cohorte extendida 2W/10L −$15.43 (régimen hostil, n=2 días) → **veredicto formal 26 Jun, no tocar**. Fix v3.40.12 verificado (0 edades absurdas post-fix). Obs nueva: #624 = un PROTECT dentro de un spike puede cerrar PEOR que el SL teórico (gap 3.4p) — sumado al item slippage/sizing.
- [x] ✅ **Idea #7 (agotamiento por run-up crudo) MEDIDA → DESPRIORIZADA**: ningún bucket de pips-recorridos-antes separa del baseline en la medición limpia. **LECCIÓN METODOLÓGICA CLAVE: el bucket ">15p/60min" daba 56% WR p=0.010 con cutoff −60s — era LOOKAHEAD de la vela en formación al entry; con cutoff −300s cae a ruido. REGLA NUEVA: toda medición retrospectiva sobre velas debe cortar ≥300s antes del entry.** El "agotamiento" que rima (SIM A, bias-confirmado 22%, conf 90) es de ALINEACIÓN DE INDICADORES REZAGADOS, no de corrida cruda — solo medible con etiquetado en-el-momento; al backlog sin prioridad.
- [x] ✅ **Cooldown 5min post-pérdida ACTIVADO (v3.40.15)** — re-confirmado sobre data fresca el mismo día (n=76, WR 24% vs 37%, p=0.009, −$170, CI sin cruzar; siguió sumando pérdidas durante la semana). Implementación: gate en `_try_mt5_execute`; señal generada <5min después de una pérdida → **SKIP definitivo** (`skipped_cooldown`), NO delay (la señal nace de la vela de pánico; la franja 5-10min ya rinde 43% con señales frescas, no delayed). `COOLDOWN_AFTER_LOSS_MIN=5` (0=off). **Es EL cambio del checkpoint (1 a la vez); medir su efecto + el del PM en el próximo.**
- [x] ✅ **"¿Entra tarde o entra mal?" (pregunta del user) → RESPONDIDO con broker-truth: entra MAL, no tarde.** Sospechoso C del script: **94% de los fills son inmediatos (<1min, n=338) y al precio planeado (±3p, n=363) — y pierden al baseline (38% WR, −$324)**. Fills tardíos/corridos = ~20 casos, ~$37 (fuga menor; #625 la peor). Conclusión: la ejecución NO es el problema — **el problema es la DECISIÓN (qué/cuándo señala)** = vía 1 del user (mejorar el razonamiento), que es el programa en curso: data limpia → calibración empírica (~150 trades limpios) + event-awareness (shadow corriendo) + playbook. La vía 2 (precio-condicional estricto) NO ataca el grueso; el escudo de señales viejas (event-window shadow) ya cubre la fuga chica.
- [x] ✅ **Sospechoso "htf_bias rezagado" — REFUTADO como culpable general** (mismo script): trades con bias contradicho por la deriva real 2h previa = WR 41% (mejor que baseline, n=39, RUIDO); los con bias CONFIRMADO por la deriva = **22% WR, −$62 (n=27)** — otra rima con el tema exhaustion (todo alineado = entrada tardía). El día CPI fue un caso puntual, no un patrón. **NO tocar el mecanismo de bias.** (2do reflejo evitado del día: el conf ceiling 80 en M15 también se verificó al revés — conf>80 en M15/H1 rinde MEJOR: 45% vs 35%.)

- [x] ✅ **NADA pasó el gate en 4 dimensiones**: temporal (hora/sesión/día), racha/recencia, estado-de-mercado, régimen×trigger. El cooldown 5min ya extrajo la única señal real que tenía la pila histórica. **Confirmación dura: NO hay más levers fáciles escondidos en la data sucia → el camino es calibración con data LIMPIA, no más minería retrospectiva.**
- [x] ✅ **Régimen detector NO justificado** (ver arriba) — no se construye.
- [x] ✅ **`smc` "dormido" = FALSA ALARMA (mía)** — investigado 8 Jun: `/smc-state` lo muestra VIVO (detectando zonas, "esperando confirmación M5" en zona demand); `smc.py` sin cambios desde v3.6.0; cadencia SIEMPRE fue lumpy (gaps de varios días normales). El "último trade 06-02" del archivo me asustó pero la data viva dice que está sano. NO tocar. Lección: chequear estado vivo antes de gritar bug.
- [x] ✅ **Sincronizar CLAUDE.md ↔ APP_VERSION** — sincronizado en v3.40.3 (línea *Última actualización* coincide con `Config.APP_VERSION`). Regla permanente: re-chequear en cada bump.

- [x] ✅ **[HIGH] Significance gate `adjustment` vs `delta`** — RESUELTO v3.40.3 (`significance.py:194`): ahora lee `delta` (fallback `adjustment`). Testeado funcional: delta<0→worse, delta>0→better.
- [x] ✅ **[HIGH] Thread del PM con imports sin guard** — RESUELTO v3.40.3 (`AIdan_TodoEnUno.py:3588`): setup envuelto en try/except con log FATAL. Verificado en vivo: PM arranca y gestiona #585.
- [x] ✅ **[MED] Timezone applied_at/reverted_at** — RESUELTO v3.40.3 (`db.py:3172`): sella con `now_ar()` (AR), igual que `created_at`; el monitor de auto-revert ya no se desfasa 3h.
- [x] ✅ **[MED] `smc_status` sin guard 1er ciclo** — RESUELTO v3.40.3 (`AIdan_TodoEnUno.py:2082`): init `smc_status = None` junto a htf_bias/daily_ctx.
- [x] ✅ **[nota, NO fix apurado] HWM no lo persiste el PM — RESUELTO en v3.52.1, y NO "funcionaba hoy" como decía esta nota.** El diagnóstico original era correcto (R1 depende de que el thread de trailing escriba `mt5_high_water`) y la solución prevista también (*"el fix naive clobberea el trailing step → arreglar con helper HWM-only"*), pero le faltaba el modo de falla concreto: la escritura estaba bajo `if success:` y el respaldo colgaba del `elif` de `new_sl`, no de `success` ⇒ **cada modify rechazado por el broker perdía el pico. 101 filas en 21 trades.** Resuelto con `update_mt5_high_water()` (helper HWM-only, como la nota pedía).
- [x] ✅ **BLOQUEANTE #1 (serializar el path de ejecución) — CERRADO 10 Ago POR LA VÍA DE LA EVIDENCIA, no implementando.** Workflow de 5 frentes + 3 refutadores adversariales (40 carreras mapeadas, 6 "críticas", 30 marcadas alcanzables) → veredicto **`no_tocar`**, y lo verifiqué a mano. **(1) El lock chico no arregla nada:** todas las carreras de cierre son check-then-act con el check en la MISMA función que el send (`close_strategy_position` hace `positions_get` en :940 y `order_send` en :973; idem `close_all_positions` :986/:1015, orphan :696/:737, `modify_position_sl` :566/:590) ⇒ un lock alrededor del `order_send` deja pasar a los dos threads por el check y después mandan la orden igual, solo ordenaditos. Es el caso de manual de *"un fix que no arregla nada, EMPEORA"*. **(2) El lock grande tiene 4 auto-deadlocks verificados en código** (`toggle→close_all_positions`, `sync_closed_positions→sync_pending_orders` —que además tiene caller externo, así que no lo salva la regla "lockeá solo las públicas"—, `open_position→_try_limit_order/_market_order` con `_find_existing_mt5_for_strategy` a dos profundidades, `reconnect→disconnect+connect`) y se sostendría sobre operaciones largas: **12 segundos reales medidos en UNA llamada a `sync_closed_positions`** (7-ago 17:50:08→17:50:20), con ~30s teóricos porque el instant-eval construye `TechnicalAnalyzer` y `get_market_state` dentro del `for` y ese path cae a Yahoo/TwelveData/FXCM con `timeout=10` cada uno — justo el escenario degradado para el que se querría el lock. Un `RLock` tapa los auto-deadlocks pero no toca nada de esto. **(3) El modo de falla de la cura es INVISIBLE:** un deadlock no tira excepción ni escribe una línea; el síntoma sería "AIdan no operó hoy", que por regla de la casa se atribuye a que lo cerró el user ⇒ sería **peor** que la clase de bug que mató a M15/SMC/el reversal/el loop de aprendizaje, porque esos al menos dejaban excepción que los logs persistentes terminaron cazando. **(4) La enfermedad no dispara:** 0 `auto-close failed` en 223.632 líneas de log, 0 órdenes duplicadas, 0 tickets compartidos entre `strategy_id`, 0 `strategy_id` con dos tickets, 0 duplicados en 581 filas de `trade_archive`, 0 `database is locked`. El peor caso documentado sigue siendo un cierre duplicado **rechazado** por el broker + un log feo. **Lo que sí salió del ejercicio y valía 10x más: los cierres que fallan son de UN SOLO THREAD y fallaban MUDOS** (25/174 = 14%) ⇒ arreglado con observabilidad en v3.53.0. *Caveat honesto anotado: los logs persistentes existen desde el 31-jul (v3.48.0) = pocos días; los 2,5 meses salen de `position_manager_log`/`trade_archive`, que son durables pero gruesos ⇒ "cero ocurrencias" tiene ese sesgo.* **Si algún día se reactiva el force-close o se agrega otro camino de cierre, revisar esto de nuevo.**

---

## Bloques superados / huérfanos bajados el 13 Ago 2026

**Forense 10 Jun (día CPI, tarde -$23.73 en 6 trades 0W) — 2 BUGS REALES confirmados → RESUELTOS v3.40.11:**
- *Contexto del día (no bug):* la pérdida fue **calidad de entrada en régimen hostil**, no gestión — los 6 de la tarde entraron con `htf_bias='bullish'` REZAGADO mientras el precio caía ~34p post-CPI (Régimen 4 del playbook); whipsaw de 18.4p mató #611 (conf 90 = peor pérdida, inversión de confidence RECONFIRMADA en vivo) y #612 (dirección correcta, timing contra rebote = Régimen 8). El management vivo funcionó: SL duros con slippage ≤0.6p, PM salvó ~$3 en #610 (PROTECT a -2.9p vs SL -10.2p), threads vivos toda la sesión. La mañana tuvo 3 wins (#603-608, ya purgados de auto_strategies por el cap — el "0 wins" era solo la tarde).

- *Agenda 19 Jun:* 1ra lectura cooldown (skips + qué evitó) · PM lectura intermedia (camino al veredicto 26 Jun) · calendar: ¿escribió con la instrumentación? · re-censo limpio con query canónica · reconciliar universos · descartar las 3 filas pre-fix del event-window · decisión mt5_filled_at + #632.

**[INCIDENTE 14 Jun] AIdan.exe estaba CAÍDO** (proceso 0; terminal MT5 seguía vivo) — restaurado a v3.40.16, reconectó sano (MT5 ok, balance $726.97). **Causa no determinable** (AIdan no persiste logs — gap conocido); ventana del 12 al 14 + el barrido corrió MT5 desde varios procesos en paralelo (`mt5.initialize()`/`shutdown()` sobre el terminal compartido). **LECCIÓN/regla nueva: NO correr MT5 pesado desde subagentes en paralelo mientras el exe vivo opera** — usar solo DB/endpoints, o pausar el exe primero. (El watchdog `aidan_watchdog.py` existe pero no estaba corriendo; evaluar activarlo.)

---

## Hilos cerrados el 13 Ago 2026 (repaso de los vencidos por fecha)

Estaban marcados `[ ]` en CLAUDE.md con fechas de jun/jul ya pasadas. Se revisó uno por uno contra la evidencia y estos 10 ya estaban resueltos — la razón del cierre va en la última línea de cada uno.

- [x] ✅ **Lun 15 Jun** — revisar `calendar_debug_log` con el primer evento: ¿el straddle shadow escribió, o el stage dice dónde muere? Si sigue 0 → debug dirigido.
  - **✅ CERRADO — la instrumentación (v3.40.16) SÍ escribió y dijo dónde muere: `sr_zero` (get_market_state devuelve S/R=0). Con eso el 3-jul se decidió SKIP straddle.**

- [x] ✅ **Semana 15-19 Jun** — (régimen despriorizado, ver arriba) seguir acumulando data limpia; opcional: etiquetar régimen en vivo en shadow si se quiere seguir la pista.
  - **✅ CERRADO — la data limpia se acumuló (el régimen quedó despriorizado y nunca se etiquetó en vivo; el detector de régimen ya estaba refutado el 14-jun).**

- [x] ✅ **Vie 19 Jun — CHECKPOINT COMPLETO (el user pidió 17 Jun: "revisar TODO sin excepciones, empezar a meter mano y corregir").** Revisar c/u CON DATA y decidir corrección, sin parquear por defecto:
  1. **Cooldown** (1ra lectura, v3.40.15): ¿los skipeados eran perdedores? (medible: qué pasó tras cada skip). Re-correr `measure_entry_suspects.py`.
  2. **PM** intermedio (camino al veredicto 26 jun): ¿avg_win subió? + confirmar que el log quedó limpio tras el fix executed=1 (v3.40.19).
  3. **TP escalado por TF (v3.40.18)** 1ra lectura: ¿los TP más grandes ayudan, o en chop bancan menos wins chicos? Data desde 17 jun.
  4. **🔴 SESGO DIRECCIONAL (hallazgo 17 Jun, PRIORIDAD)**: 15-17 jun casi TODO PUT, **3 días en rojo (~−$31; 17 jun 1W/7L −$12.35, 8/8 PUT)**. ¿Régimen real (EUR/USD bajó parejo) o le vendimos al rebote/chop (= sesgo bajista pegado, "todo aligned = entrada tardía")? Medir bias vs deriva real (sospechoso B de `measure_entry_suspects.py`). Si es patrón real (no ruido n chico) → meter mano.
  5. **GRUPO B** (escalar constantes por ATR/TF — vol 10/4, breakout 7p, prox 12-15p, cluster 5p, SL floor): es LÓGICA no bug, no medible retro (data M15/H1 destruida por avg_range_pips=0), toca el cerebro de M5. Opción: modelar **M15/H1-only con M5 CONGELADO**, medido hacia adelante. DECIDIR: modelar+activar o esperar data limpia.
  6. **calendar**: ¿escribió con la instrumentación v3.40.16? (revisar `calendar_debug_log`).
  7. **Universos lifetime** sin reconciliar (broker vs DB vs balance) + query canónica del censo limpio.
  8. **mt5_filled_at** (edad desde fill, obs #625) + **#632** (pnl NULL): decisión.
  9. **Repasar el resto de NOTAS sin excepción**: SMC reversal (medición pendiente, hoy apagado), demand/supply enforce, trend-desync MA9/21 vs MTF, feedback de aprendizaje muerto (±15 sobre tablas no pobladas → calibración limpia), deudas técnicas (lock cierre PM, evaluation gap news LLM).

  - **✅ CERRADO — el checkpoint se hizo; los resultados son el bloque "Checkpoint 19 Jun — RESULTADOS". De los 9 sub-items, los que siguen vivos están como hilos propios (Grupo B, universos lifetime, mt5_filled_at).**

- [x] ✅ **🔴 VIE 31 JUL (agendado 29 Jul a pedido del user) — RE-MEDIR "NIVEL FLOJO" EN m15 (candidato #1 barato).** Origen: el user preguntó por qué falló AIdan el 29-jul (6 trades 2W/4L, −$17.79) y "por qué no hubo control de pérdidas" en los −11.6p y −15p. **Respuesta: SÍ hubo — el SL** (ambos cerraron en/antes del stop planeado de 15p, −$4.92 y −$6.40 ≈ 1% cada uno). Lo que no hay es corte intermedio: el PM es pasivo con perdedores hasta el soft-expiry (#829 estuvo 45min en rojo con 9 HOLD, cortó a −11.6 al soft-expiry) y el BE solo arma con ≥50% del TP a favor (HWM fue 1.8p y 0.2p → nunca armó; #834 murió al SL en <5min). **Se midieron y REFUTARON 2 hipótesis de fix el mismo día:**
  1. **SL de m15 fijo 15p → NO tocar.** El sizing es `riesgo$/(SL×10)` (`mt5_executor.py:171`, verificado con lotes reales: SL 15p→0.04, SL 10.9p→0.06, SL 60p→0.01) ⇒ **el SL NO define la pérdida en plata, la define el 1%**. Apretar el SL no reduce la pérdida por trade: solo baja el WR (más stop-outs, peor en chop) y sube el R:R. Mi encuadre inicial ("pierde grande en mercado chico") era cierto en pips, falso en plata — la decisión se toma en plata.
  2. **Distancia al nivel en m15 → NO aplicar el tighten de v3.46.0 a m15.** `measure_dist_to_level.py` (m15 n=68): ≤0.5 ATR 61% WR n=23 (falla el gate por n, p=0.019, MISMO "a 2 trades" del 17-jul) · >1 ATR 35% pero **+$0.1 = planchado, no hay cola perdedora que cortar**. Y decisivo: **los 3 perdedores del 29-jul ya entraron PEGADOS** (dist 2.5p / 1.2p / 3.1p; dos dentro de la celda estrella ≤0.5 ATR) → el filtro no habría bloqueado ninguna. Falló **el nivel**, no la distancia.
  - **LO QUE SÍ QUEDÓ (medir el viernes):** toques del nivel en m15 (n=68, P&L real): **≤10 toques (flojo) = n=6, 17% WR, −$19.4** vs **>10 toques = n=62, 47% WR, +$53.1** (toda la ganancia de m15 vive arriba de 10 toques; el #834 de hoy tenía 2 toques y era CALL contra htf bearish, conf 83). Los niveles flojos son RAROS: 6/68 = 9%, mediana 18 toques → **reconfirma que el "fractal de ruido de 2 vecinos" es un mito también en m15**. **NO monotónico** (16-30 → 57% p=0.049 n=23, pero >30 baja a 40% ⇒ eso es ruido, no relación real: no usar "más toques = mejor").
  - **Acción el 31-jul:** re-correr el corte de toques en m15 (habrá ~8-10 filas nuevas). Si el bolsillo flojo llega a n≥10 y sigue ~15-20% WR con PnL claramente negativo → **proponer formal, NO como block sino como "mejorar": penalizar la confianza cuando el nivel es flojo** (con el piso 60 filtra los peores sin apagar la familia). Costo de frecuencia estimado: 6 trades cada 7 semanas (9%) = ratio muy distinto a un filtro que recorta 30% del volumen. **Caveat:** `level_touches` se cuenta con tolerancia `max(2, ATR×0.5)` (v3.40.22) ⇒ los toques CORRELACIONAN con volatilidad — no leerlo como calidad pura. Y por volumen (6 casos en 7 semanas) esto **quizá nunca pase el gate de n≥25** → decidir con juicio calibrado, no esperar significancia eterna.
  - **Hint suelto a vigilar (misma corrida):** m15 con **ATR>8p (expansión) = 13 trades, 77% WR** vs ATR 5-8p = 53 trades 34%. n chico, pero rima con el hallazgo del 3-jul (gana en expansión, muere en chop) y sería un lever más limpio que cualquier ajuste de SL.

  - **✅ CERRADO — re-medido el 5-ago e IMPLEMENTADO en v3.50.0 (castigo de confianza por nivel flojo en m15, `LEVEL_QUALITY_PENALTY=15`). El forward de ese cambio se mide ~19 ago.**

- [x] ✅ **Position Manager (experimento #1)** · `POSITION_MANAGER_MODE=active`. **RE-BASELINEADO 10 Jun (v3.40.11)**: hasta ahora el late-close pisaba al PM → solo corría su mitad defensiva; desde v3.40.11 los trades pueden por primera vez extenderse más allá del expiry (hasta MAX_HOLD 90/120/240min o SL/TP). Medir ~2 sem desde 10 Jun: avg_win / WR / PF; revertir a `log` si empeora. *Obs 8 Jun (sigue válida):* pasivo en perdedores pre-soft-expiry (diseño). *Obs 10 Jun:* el PM SÍ protege (CLOSE_PROTECT #610 a −2.9p vs SL −10.2p) y los HOLD ahora van a poder sostener de verdad. Vigilar los primeros días: trades viviendo 90-240min es comportamiento NUEVO en vivo.
  - **✅ CERRADO — veredicto tomado el 26-jun: **KEEP, no revertir** (CLOSE_MAXHOLD +$25,63 en 11 trades, 34 CLOSE_PROTECT). El PM queda `active` como configuración normal, ya no es experimento.**

- [x] ✅ **[obs] M15 disparó 9 trades el 11 Jun** (la mayoría PUTs al serrucho de mediodía) — el track más frecuente justo en el peor régimen. Se suma a la observación previa "M15 sin techo de ATR" (data retrospectiva no existe — destruida por el bug del doble-encode; medible solo hacia adelante desde v3.40.11).
  - **✅ CERRADO como observación de un día — superada por las mediciones de m15 con data limpia (nivel flojo → v3.50.0; el hint de ATR>8p sigue abierto como hilo propio).**

- [x] ✅ **Calendar shadow ROJO → instrumentado v3.40.16**: 0 filas con 2 eventos UoM Medium elegibles y proceso vivo el 12 Jun — 4 salidas SILENCIOSAS verificadas en código (S/R≤0 sin log, cache /calendar vacío en ventana, spread-gate, excepción por-evento a debug) = la clase M15. Fix: tabla `calendar_debug_log` + `_cal_dbg()` (throttled) en cada salida (detected/sr_zero/autotuner/spread/minconf/exception/feed_empty). **Vigilar el próximo evento (lunes): si detected aparece y shadow sigue en 0, el stage dice exactamente dónde muere.** (Al instrumentar casi meto un NameError de utc_now — cazado pre-ship.)
  - **✅ CERRADO — la instrumentación funcionó: detecta el evento y muere SIEMPRE en `sr_zero`. Eso más "los eventos elegibles son speeches Medium, no releases" fundamentó el SKIP straddle del 3-jul.**

- [x] ✅ **Data limpia: 62 trades desde 5 Jun (~10/día hábil) → ~150 el 24-25 Jun (1er intento calibración), ~300 el 15-16 Jul (robusta).** Fix entry_context m15/h1 VERIFICADO end-to-end (17/17 post-cutover con features pobladas; pre-cutover vacíos como control). Fuga menor: #632 archivó con mt5_pnl NULL (investigar, el censo depende de ese campo). ⚠️ El contador necesita query CANÓNICA (dedup + cutoff explícito): el mismo día dio 62 vs 68 según la hora.
  - **✅ CERRADO — la muestra llegó y la calibración se intentó y REFUTÓ dos veces (Platt 5-ago, Brier 0,2522 vs constante 0,2424, n=167). El `mt5_pnl` NULL se cerró aparte en v3.51.1 (`trade_archive` solo acepta trades que llegaron al broker).**

- [x] ✅ *(arrastrado)* **Hallazgo original 10 Jun:** Re-entradas ≤5min tras una pérdida: **n=74, WR 24% vs 38% baseline, −$156 (34% de TODA la pérdida histórica en 12% de los trades), p=0.010, CI no cruza** (sobrevive Bonferroni 4 tests). Robustez: clasificación por timestamps EXACTOS de deals del broker (inmune a la fragilidad del caso bounce); sostenido en 4/5 quincenas; frontera nítida (franjas exclusivas: 0-2min 26% WR, 2-5min 23%, **5-10min 43%, 10-15min 48%** — la toxicidad termina exacto a los ~5min). CAVEATS: muestra históricamente cargada (78% del bucket es de abril; el sistema actual ya casi no re-entra rápido: ~16 casos en may-jun, ~−$42), y la pila es la sucia multi-versión. #611 del 10 Jun (peor pérdida del día, creado 2s tras cerrar #610 en rojo) es EXACTAMENTE este patrón. **Decisión pendiente (checkpoint viernes): activar cooldown 5min post-pérdida.** NO activado aún por "1 cambio a la vez" (experimento PM re-baselineado 10 Jun corriendo). Re-medir sobre data limpia v3.40.x es trivial (re-correr el script).
  - **✅ CERRADO — el cooldown se ACTIVÓ en v3.40.15 y se re-confirmó sobre data fresca (n=76, WR 24% vs 37%, p=0.009). Este hilo era el duplicado del hallazgo original.**

- [x] ✅ **Evaluation gap del news LLM** — Groq malinterpreta news (negaciones de bancos centrales, problema estructural #3) y **no medimos cuán seguido**. Gap de evaluación legítimo (lección LinkedIn 8 Jun). Idea: medir tasa de error con muestra etiquetada. No urgente.
  - **✅ CERRADO — el gap se midió el 24-jul con `tools/measure_news_llm_error.py` sobre 753 alertas: **el LLM no discrimina (edge −1pp, Fisher p=0.92) y es ANTI-SKILL (hit 53% vs drift 63%)**. Ya no es un gap de evaluación: es un resultado.**


---

## Cerrado 16 Ago 2026 — baseline del track D1 corregido (v3.54.1)

*(Bajado de CLAUDE.md el 26-ago-2026 por la regla de tamano: el hilo estaba cerrado con ✅ y seguia ocupando lugar en el archivo que se carga entero en cada sesion.)*

- [x] ✅ **CERRADO 16-ago (v3.54.1) — el baseline del D1 estaba mal y ya se corrigió.** Se tomó la opción (1): re-correr el backtest con los params vivos, read-only, sin tocar producción. Lo verificado: **(a)** los params vivos difieren del default en 4 claves, pero solo 2 afectan al D1 (`breakout_dist_max`/`breakdown_dist_max` 15→7); `block_outside_sessions` se aplica en los loops de M5/news/smc/calendar y **NO en el bloque D1**, y `min_pips_for_win` es de etiquetado del tuner. **(b)** El `conf_adj` de sesión en vivo depende de a qué hora el loop ve la vela nueva y **no se puede reconstruir honestamente** ⇒ no se inventó un "auto": se agregó `--session sweep`, que corre las 4 sesiones y reporta el rango. **Resultado — el titular del 13-ago se reproduce exacto con `--params default --session off` (242 señales, PF 1,41, +16,6p), o sea que aquella corrida fue en off-hours.** Baseline corregido (params vivos, 4 sesiones): **186-227 señales · 2,1-2,5/mes (no 2,7) · +13,7 a +15,3p neto de comisión · +10,8 a +12,7p post-swap · PF 1,25-1,30.** **Positivo en las CUATRO sesiones** ⇒ el edge no dependía de la hora del reloj, que era el riesgo real de (b); el nivel sí baja ~10-15% y la frecuencia ~20%. El número quedó escrito en el docstring de `technical_d1.py` y lo imprime `score_d1_shadow.py` al final. *(La revisión del 13-ago devolvió 28 hallazgos; los 5 accionables se arreglaron en el 2do commit de v3.54.0, este era el 6to y último accionable. El resto son menores.)*


---

## Checkpoints de junio 2026 (obs 11-jun, checkpoints 12-jun, barrido 14-jun)

*(Bajado de CLAUDE.md el 26-ago-2026 por la regla de tamano — el archivo estaba 9 KB por encima de su propio limite de 100 KB y estos son exactamente los "checkpoints viejos" que la regla manda mover. Nada de esto es un hilo abierto: el cooldown ya se activo, el PM ya tiene veredicto, los candidatos a vigilar tienen sus propios medidores. Consultar con grep antes de re-proponer.)*

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


---

## Analisis 11 May 2026 — calibracion de confidence (tablas completas)

*(Bajado de CLAUDE.md el 26-ago-2026. Superado por v3.59.0, que consiguio el 1er PASA del gate de calibracion con 309 trades limpios. Se guarda porque las tablas son la evidencia de por que NO se sube el piso de confianza.)*

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


---

## Implementacion de los tracks B (M15) y C (H1), mayo 2026

*(Bajado de CLAUDE.md el 26-ago-2026 por la regla de tamano. Son las notas de implementacion originales: perfiles completos, filtros, elementos de UI, criterios de comparacion.)*

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


---

## Backtest H1+M15, 30 dias (27-mar a 8-may 2026)

*(Bajado de CLAUDE.md el 26-ago-2026 por la regla de tamano.)*

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

---

## ✅ CERRADO 28 Ago 2026 — VEREDICTO news v3.51.0: **NO PASO** ⇒ perilla girada a 15

Criterio pre-declarado el 7-ago (leer el ~28-ago, n>=15). Se leyo el 28-ago con **n=21**
(news creados desde el 7-ago, broker-truth):

| Condicion | Gate | Medido | |
|---|---|---|---|
| (a) los ganadores recorren mas del TP | **>=59%** (venian de 40%) | **43,2%** (mediana 34,9%) | ❌ |
| (b) los perdedores no se estiran | ~53% del SL | **53,1%** | = sin cambio |
| (c) PnL/trade | mejor que −$0,91 | **−$1,37** (WR 28,6%, −$28,70) | ❌ peor |

⇒ Se aplico lo pre-declarado: **`NEWS_MIN_EXPIRY_MIN=15`** en el `.env` + restart del exe
(sin rebuild; `Config` se lee al importar). El guard del codigo es `if _news_floor > 15`
(`AIdan_TodoEnUno.py:1884`) ⇒ 15 no aplica ningun override y news queda **exacto como en
v3.50.4**. Revertir = borrar la linea del `.env` (vuelve al default 45) y reiniciar.
Se hizo con 0 posiciones abiertas, asi que no quedo nada sin gestionar.

**Lo que la lectura dejo claro y no hay que volver a proponer:** el problema de news no es el
recorrido del ganador. Con **SL de ~4 pips** y comision ~1,3p el track necesita **53,9% de WR
para empatar** (ganador medio $2,53, perdedor −$2,96) y saca 28,6%. Alargar el expiry no mueve
esa cuenta — la mueve el TP capado (`tp_cap = max(ATR,2)*2`, hallazgo #1 del 15-jun, sigue abierto).

**Contexto de latencia (medido el mismo dia, no mezclar universos):** los 132 trades de news
de la muestra historica entraron TODOS >=29 min despues del dato. Con Forexlive (v3.61.0) la
cadena real medida sobre #942 fue **release → +18s publica la fuente → +3,7 min lo baja AIdan
→ +12s el LLM → +2s la orden = ~4 min** (antes 29,7). El titular de "+15 segundos" de v3.61.0
era **solo la culpa de la FUENTE**: en produccion el poll agrega **5,7 min de mediana**
(investinglive) y 7,8 min (Bloomberg). Descartados como causa: el collector si corre cada 60s
(gap minimo medido 62s), `MAX_PER_SOURCE=5` **nunca** se activo (0 lotes con 5+ items nuevos) y
el slippage es cero (TCA mediana +0,00p, n=28). **El retraso que queda es del RSS mismo** (el
item aparece en el XML minutos despues de su propio `published_at`) ⇒ con RSS no se arregla.

**Refutado el mismo dia (hipotesis propia, no del user):** "entra al revés porque vende contra
la tendencia". Es **al revés** — contra-HTF n=171 WR 41,5% −$0,52/trade vs a-favor n=358 WR
32,7% −$0,93/trade. Coincide con "todo alineado = PEOR" del 19-jun. Y la asimetria PUT/CALL
(PUT −0,79 pips vs CALL +1,40) esta **confundida**: EUR/USD subio 204,5 pips en la ventana.

---

## ✅ BAJADO 28 Ago 2026 — tres secciones vencidas de CLAUDE.md

Se bajaron por la regla de tamaño (CLAUDE.md habia pasado los 100 KB). Las tres estaban
superadas por hechos posteriores, se dejan por trazabilidad:

- **Opciones A-D para corregir confidence (11 May)**: A y B nunca se hicieron; C se **refuto**
  (ML a n=276, 4 modelos, AUC real 0,44-0,48); D quedo obsoleta. Lo que si paso es la
  **calibracion de Platt de v3.59.0** (m15, Brier 0,2214, fase registro).
- **Restriccion de frecuencia (11 May)**: el horizonte que planteaba (fin de mayo / mediados de
  junio para 200-300 trades) ya paso; hoy hay 309 limpios y el cuello es otro.
- **Checkpoint del 12 Jun**: ejecutado en su momento (cooldown activado, experimento del PM
  medido, calendar shadow revisado). El item 2b (edad desde el FILL) se resolvio en **v3.61.1**
  con `SIGNAL_MAX_AGE_MIN`.

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
