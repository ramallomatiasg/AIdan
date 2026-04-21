# AIdan v3.6.3 - Asistente de Scalping EUR/USD con IA + Auto-Optimizacion

Sistema de trading asistido que monitorea noticias financieras en tiempo real, analiza estructura de mercado en multiples temporalidades (D1, H4, H1, M15, M5), genera senales de trading para EUR/USD usando inteligencia artificial, y **optimiza sus propios parametros automaticamente** aprendiendo de resultados pasados.

**Un solo ejecutable de ~25MB - Portable, gratis y privado.**

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
