import os
import sys
from dotenv import load_dotenv
import json

# For PyInstaller exe: find .env relative to the executable or script location
_base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
# Walk up from src/common/ to project root (or from dist/ to project root)
_env_candidates = [
    os.path.join(_base_dir, '.env'),
    os.path.join(_base_dir, '..', '.env'),
    os.path.join(_base_dir, '..', '..', '.env'),
    os.path.join(os.getcwd(), '.env'),
]
for _env_path in _env_candidates:
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)
        break
else:
    load_dotenv()  # fallback: default search

APP_VERSION = "3.65.1"

class Config:
    VERSION = APP_VERSION
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    COLLECTOR_INTERVAL = int(os.getenv("COLLECTOR_INTERVAL", "60"))   # 1 min
    ANALYZER_INTERVAL = int(os.getenv("ANALYZER_INTERVAL", "10"))     # 10 sec
    DATA_RETENTION_HOURS = int(os.getenv("DATA_RETENTION_HOURS", "72"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "46f407e058674f159a2a176e023ab536")
    GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "config/google_creds.json")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
    GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "AIdan - Trading Report")
    GROQ_API_KEYS = [
        "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",
        "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",
        "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",
    ]
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", GROQ_API_KEYS[0])
    # v3.56.0 - llama-3.3-70b-versatile y llama-3.1-8b-instant fueron DADOS DE
    # BAJA por Groq el 16-ago-2026. Verificado contra GET /openai/v1/models: ya no
    # estan. Desde el 17-ago el log muestra 404 model_not_found y todo cae a Ollama.
    # Reemplazos elegidos MIDIENDO contra el prompt real de news, no por catalogo:
    #   gpt-oss-120b  1,6s, parsea OK  <- elegido analitico (news, pre-planner)
    #   gpt-oss-20b   1,1s, parsea OK  <- elegido chat (dashboard, exit advisor)
    #   qwen3.6-27b   7,2s, 10x tokens <- descartado
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    # Faster, smaller Groq model for dashboard chat — non-critical, latency-sensitive.
    GROQ_MODEL_CHAT = os.getenv("GROQ_MODEL_CHAT", "openai/gpt-oss-20b")
    # Los gpt-oss son modelos de RAZONAMIENTO: emiten tokens de pensamiento antes de
    # la respuesta. Sin esta perilla en low gastaban 498 de 500 tokens pensando y
    # devolvian content VACIO con HTTP 200 (fallo silencioso). Con low: ~87 tokens.
    GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
    # Local model for non-blocking tasks (audit, post-trade, news pre-filter).
    # qwen2.5:7b chosen after benchmarking vs gemma4: ~3x faster (7s vs 20s),
    # same filter quality (neither adds significant signal). See bench_audit_*.csv.
    GEMMA_MODEL = os.getenv("GEMMA_MODEL", "qwen2.5:7b")
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # v3.25.0 — LLM_MODELS centralized: modelo apropiado por tarea.
    # Cada modulo lee Config.LLM_MODELS['task_name'] en lugar de Config.GEMMA_MODEL.
    # Backward compat: si LLM_MODELS_<TASK> env var setteada, override.
    # Si modelo no existe en Ollama -> graceful fallback a GEMMA_MODEL.
    LLM_MODELS = {
        # News pre-filter: tarea binaria YES/NO.
        # Probamos qwen3:1.7b pero su "thinking mode" rompe responses cortas
        # (devuelve vacio con num_predict bajo). qwen2.5:7b estable y rapido (~2s warm).
        'news_prefilter': os.getenv("LLM_MODEL_NEWS_PREFILTER", "qwen2.5:7b"),
        # Signal auditor: JSON breve, tarea de validacion. Modelo medio.
        'signal_audit': os.getenv("LLM_MODEL_SIGNAL_AUDIT", "qwen2.5:7b"),
        # Pre-planner: estrategia diaria, decision compleja. Razonador.
        'pre_planner': os.getenv("LLM_MODEL_PRE_PLANNER", "deepseek-r1:7b"),
        # Post-trade analyzer: feedback loop critico. Razonador para sl_tp_advice.
        'post_trade': os.getenv("LLM_MODEL_POST_TRADE", "qwen2.5:7b"),
        # Pretrade audit strict: cuando se hookee, razonador maximo. Offline.
        'pretrade_strict': os.getenv("LLM_MODEL_PRETRADE_STRICT", "deepseek-r1:14b"),
        # News analysis (Ollama fallback): si Groq cae, modelo medio capaz.
        'news_analysis_ollama': os.getenv("LLM_MODEL_NEWS_OLLAMA", "qwen2.5:7b"),
    }

    @staticmethod
    def get_llm_model(task_name):
        """Get model name for a task with graceful fallback to GEMMA_MODEL."""
        return Config.LLM_MODELS.get(task_name, Config.GEMMA_MODEL)
    GOOGLE_SHEETS_WEBHOOK = os.getenv("GOOGLE_SHEETS_WEBHOOK", "https://script.google.com/macros/s/AKfycbzZqRaz_37eSjky1I4F1-2bnQQtRPC15_wDGA5ohxUvzTPq38ez74mbc7oYoNb4NvfyFw/exec")

    # MT5 Broker Integration
    MT5_ENABLED = os.getenv("MT5_ENABLED", "false").lower() == "true"
    MT5_ACCOUNT = int(os.getenv("MT5_ACCOUNT", "0"))
    MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER = os.getenv("MT5_SERVER", "ICMarketsSC-Demo")
    MT5_SYMBOL = os.getenv("MT5_SYMBOL", "EURUSD")

    # v3.28.0 — Daily loss limit auto-pause
    # Si daily_pnl <= -DAILY_LOSS_LIMIT_USD, auto-pausa hasta dia siguiente.
    # Default $30 (3% del capital base $1000). Set 0 para desactivar.
    DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "30"))

    # v3.28.0 — Multi-TF consensus boost
    # Si N tracks coinciden en direction dentro de CONSENSUS_WINDOW_SEC, ultimo trade
    # entra con lote multiplicado. Detecta convergencia M5+M15+H1.
    CONSENSUS_WINDOW_SEC = int(os.getenv("CONSENSUS_WINDOW_SEC", "300"))  # 5 min
    CONSENSUS_BOOST_MULTIPLIER = float(os.getenv("CONSENSUS_BOOST_MULTIPLIER", "2.0"))  # 2x lot

    # v3.28.0 — Spread guardian
    # Bloquea entries si spread actual > MAX_SPREAD_PIPS
    MAX_SPREAD_PIPS = float(os.getenv("MAX_SPREAD_PIPS", "2.5"))

    # v3.32.1 — User awake window: no abrir trades nuevos cerca del horario
    # en que el user duerme. Asume horario AR (UTC-3, sin DST).
    # Track-aware: H1 con expiry 180min necesita cutoff mas temprano.
    # Override por env var en .env si querés horarios distintos.
    TRADING_START_HOUR_AR = int(os.getenv("TRADING_START_HOUR_AR", "6"))   # 06:00 AR
    TRADING_END_HOUR_AR = int(os.getenv("TRADING_END_HOUR_AR", "22"))     # 22:00 AR (default M5)
    H1_LAST_OPEN_AR = int(os.getenv("H1_LAST_OPEN_AR", "19"))             # H1: 19:00 AR (expiry 180min)
    M15_LAST_OPEN_AR = int(os.getenv("M15_LAST_OPEN_AR", "22"))           # M15: 22:00 AR

    # v3.35.0 — Feature flag: usar modelo ML para confidence en triggers
    # con modelo dedicado (news, m15_structure). Default FALSE por safety.
    # Cuando true: news y m15_structure usan model dedicado en lugar de heuristica.
    # Otros triggers siguen usando heuristica vieja como fallback.
    USE_ML_CONFIDENCE = os.getenv("USE_ML_CONFIDENCE", "false").lower() in ('true', '1', 'yes')

    # v3.36.0 — Live Position Manager (Fase 1: reglas, sin LLM).
    # Gestor en vivo que decide HOLD/CLOSE sobre posiciones abiertas en lugar del
    # expiry ciego + force-close por mechas re-analizadas (bug del 538).
    # MODE:
    #   'off'    — gestor desactivado (comportamiento legacy completo)
    #   'log'    — gestor evalua y LOGUEA decisiones pero NO ejecuta; el force-close
    #              viejo sigue activo. Para shadow validation sin cambiar live. (DEFAULT)
    #   'active' — gestor ejecuta cierres; se desactiva el force-close por mechas.
    #              MT5 SL/TP + gestor + MAX_HOLD gobiernan el ciclo de vida.
    POSITION_MANAGER_MODE = os.getenv("POSITION_MANAGER_MODE", "log").lower()
    # Cadencia del thread del gestor (segundos). El trailing sigue en 1s aparte.
    POSITION_MANAGER_INTERVAL = int(os.getenv("POSITION_MANAGER_INTERVAL", "15"))
    # MAX_HOLD por track (minutos): backstop final de cierre. Reemplaza el expiry fijo
    # como red de seguridad de tiempo. Generosos vs expiry para dejar desarrollar el move.
    MAX_HOLD_MIN_M5 = int(os.getenv("MAX_HOLD_MIN_M5", "90"))
    MAX_HOLD_MIN_M15 = int(os.getenv("MAX_HOLD_MIN_M15", "120"))
    MAX_HOLD_MIN_H1 = int(os.getenv("MAX_HOLD_MIN_H1", "240"))
    # R1 Profit-lock: arma cuando HWM >= ARM*tp_distance; cierra si progress cae a <= KEEP*HWM.
    PM_PROFIT_LOCK_ARM = float(os.getenv("PM_PROFIT_LOCK_ARM", "0.60"))   # llego a 60% del TP
    PM_PROFIT_LOCK_KEEP = float(os.getenv("PM_PROFIT_LOCK_KEEP", "0.60"))  # cierra si retrocede 40% del pico

    # v3.53.4 — Intento de orden LIMITE antes de ir a mercado. APAGADO por default.
    # Medido en los logs: 36 intentos, 36 rechazados con retcode 10022 "Invalid
    # expiration", 36 fallbacks a market order, 0 fallos => el mecanismo NUNCA opero y
    # TODO el track record de AIdan se hizo con ordenes a mercado. Encenderlo no seria un
    # bugfix: seria estrenar una forma de entrar que nunca se midio.
    # Y hay razon para pensar que es ADVERSA: pedir 1,5p mejor que el mercado no entra
    # cuando el precio se va a favor de una (te perdes el ganador) y si entra cuando
    # retrocede (te llena en los perdedores) = seleccion adversa por construccion, el
    # mismo mecanismo del catch-the-falling-knife. Caso empirico: #625 espero 27min
    # pendiente, se lleno dentro de un spike y fue la peor perdida de ese dia (-$13,48).
    # Ademas el sospechoso C midio que el 94% de los fills ya son inmediatos al precio
    # planeado y pierden al baseline => el precio de entrada no es el problema.
    # Apagarlo NO cambia el comportamiento efectivo (ya iba siempre a mercado): saca 36
    # llamadas inutiles al broker y 72 lineas de ruido del log.
    # Para encenderlo algun dia: (1) diagnosticar el 10022 con MT5 real —hay 3 hipotesis:
    # timestamp en zona horaria equivocada, 90s por debajo del minimo del broker, o el
    # simbolo no soporta ORDER_TIME_SPECIFIED—, (2) medirlo en shadow comparando
    # fill-vs-no-fill, (3) decidir con datos.
    LIMIT_ORDER_ENABLED = os.getenv("LIMIT_ORDER_ENABLED", "false").lower() == "true"

    # v3.52.0 — Cap del umbral de break-even en pips absolutos, por track.
    # El BE (50% del TP), el trailing (80%) y el profit-lock del PM (60%) estan anclados a
    # un % del TP. En h1 el TP es ~54p => el BE arma a +27p, y el HWM MAXIMO de toda la
    # historia de h1 es 26.3p => h1 NUNCA armo una proteccion de ganancia en 67 trades.
    # Medido (34 h1 con log de PM): los que llegaron a >=4p a favor conservan -6% al cerrar
    # (suben +10p y vuelven a negativo). Los 6 perdedores que tocaron >=5p cerraron entre
    # -0.5p y -5.6p => todos pasaron por +1p en la bajada. Los 8 ganadores que tocaron >=5p
    # conservan 67% del pico y ninguno bajo de +3.9p => el BE no habria cortado a ninguno.
    # El min() lo hace MONOTONICO: arma antes, nunca despues. 0 = apagado (sin rebuild).
    BE_TRIGGER_MAX_PIPS = float(os.getenv("BE_TRIGGER_MAX_PIPS", "5.0"))
    # Solo los tracks listados. m15 (el motor, +$32.64) y M5 quedan intactos a proposito:
    # su BE ya arma dentro del rango que el precio alcanza (m15 TP 18p => BE a 9p).
    BE_TRIGGER_MAX_TRACKS = os.getenv("BE_TRIGGER_MAX_TRACKS", "h1_structure")

    # v3.51.1 — trade_archive solo acepta trades que LLEGARON AL BROKER (ticket o P&L).
    # Una estrategia skipeada (cooldown / market closing / spread gate / sin fill) no es un
    # trade: archivarla mete un win/loss de papel con los pips teoricos del TP/SL nominal.
    # Medido: 22 de 600 filas, ~2 por semana desde abril. false = comportamiento previo.
    ARCHIVE_REQUIRE_EXECUTION = os.getenv("ARCHIVE_REQUIRE_EXECUTION", "true").lower() != "false"

    # v3.51.0 — news: recorrido para los GANADORES, defensa igual para los perdedores.
    # Medido sobre los 12 news post-fix v3.47.0 (P&L real): WR 42% y -2.7p brutos, pero
    # -8.4p de comision => la comision es el 76% de la perdida. 9 de 12 se cortan a mitad
    # de camino y la asimetria esta AL REVES: los ganadores recorren 40% del TP y los
    # perdedores 53% del SL.
    #
    # Causa de codigo (no estadistica): el TP y el expiry de news se retroalimentan hacia
    # abajo. El tp_cap usa cap_mult = 2.0 + profile['expiry_minutes']/60 con el 15 del
    # profile -> TP chico (6.8p); despues AIdan_TodoEnUno calcula el expiry DE ese TP
    # (tp_pips/atr*5) -> cae al piso de 15min. Se clava en el trade mas chico posible.
    #
    # PERILLA 1 — piso de expiry para news: rompe el lazo. cap_mult 2.25 -> 2.75, el TP
    # pasa de 6.8p a 7.7p y el ganador tiene 45min en vez de 15 para llegar.
    NEWS_MIN_EXPIRY_MIN = int(os.getenv("NEWS_MIN_EXPIRY_MIN", "45"))   # 0/15 = apagado
    # PERILLA 2 — el soft-expiry del Position Manager para news queda ANCLADO donde esta
    # hoy. Sin esto la perilla 1 se da vuelta: CLOSE_PROTECT dispara en
    # time_in_trade >= base_expiry_min (position_manager.py:97), asi que con expiry 45 los
    # perdedores tendrian 30min mas para llegar al stop; si pasan de 53% a 100% del SL el
    # EV cae a -0.86p = PEOR que hoy. Anclado en 15 la defensa sigue igual que hoy.
    # 0 = seguir al expiry de la estrategia (comportamiento previo a v3.51.0).
    NEWS_PM_BASE_EXPIRY_MIN = int(os.getenv("NEWS_PM_BASE_EXPIRY_MIN", "15"))

    # v3.38.1 — Entry Quality Gates (v3.34.0) ahora config-driven y DESACTIVADOS por default.
    # Sweep de significancia (29 May, tools/sweep_entry_gates.py): los 30 combos de
    # vel x body dan blocked-set = RUIDO (CI cruza baseline 37.4% en todos). Los gates
    # NO separaban ganadores de perdedores en ningun threshold — solo reducian frecuencia.
    # Default OFF restaura el comportamiento pre-v3.34.0. Reactivar con tuning si en 300+
    # trades aparece un threshold que pase significancia: ENTRY_GATES_ENABLED=true.
    ENTRY_GATES_ENABLED = os.getenv("ENTRY_GATES_ENABLED", "false").lower() in ('true', '1', 'yes')
    ENTRY_GATE_VEL_MAX = float(os.getenv("ENTRY_GATE_VEL_MAX", "6.0"))        # vel_5c_aligned > X -> block
    ENTRY_GATE_BODY_ATR_MAX = float(os.getenv("ENTRY_GATE_BODY_ATR_MAX", "1.3"))  # body/atr > X -> block

    # v3.39.0 — Skip bounce-entry: no entrar sobre una vela que va EN CONTRA de la
    # direccion del trade (PUT entrando sobre vela verde, CALL sobre vela roja).
    # Validado sobre 306 trades + velas MT5 (tools/backtest_entry_timing.py):
    # bounce-entries WR 22% vs 45% normales, p=0.000, sostenido en todas las epocas,
    # sin subgrupo salvable. Es ~la mitad de los trades de AIdan (los que sangran).
    # MODE: off | shadow (registra "habria saltado" sin actuar, DEFAULT) | active (saltea).
    SKIP_BOUNCE_ENTRY = (os.getenv("SKIP_BOUNCE_ENTRY", "shadow") or "shadow").lower()

    # v3.40.15 — Cooldown post-perdida (DECISION checkpoint 12 Jun 2026). Re-entradas
    # <=5min tras una perdida: 24% WR vs 37% baseline (n=76, p=0.009, -$170 = 34% de toda
    # la perdida historica en 12% de los trades; unico hallazgo que paso el gate adversarial;
    # frontera nitida: 5-10min ya rinde 43%). Las senales generadas dentro del cooldown se
    # SKIPEAN (no se delayean: una senal de la vela de panico no mejora por esperar).
    # 0 = off.
    COOLDOWN_AFTER_LOSS_MIN = float(os.getenv("COOLDOWN_AFTER_LOSS_MIN", "5"))

    # v3.61.1 — Guard de EDAD de la senal en la ejecucion (cierra la clase #625).
    # El retry de ejecucion podia mandar a MERCADO una senal de hasta 180 min
    # (el expiry de h1) sin ningun chequeo de edad: #625 espero 27 min y el retry
    # la ejecuto en el primer minuto de un spike (-$13,48, la peor del dia).
    # Broker-truth (522 trades): 98% de los fills son instantaneos; los 11
    # tardios (>2 min) fueron 1W/10L a -$2,41/trade. El argumento del guard no
    # es la muestra (n=11): es de CONSTRUCCION — el SL/TP y el lote se calculan
    # al precio de la senal, ejecutarla vieja rompe el modelo de riesgo.
    # Exentos: pre_planned y calendar (esperan su event_time POR DISENO).
    # 0 = apagado. El umbral 10 min NO es nuevo: es el mismo que el event-window
    # usa desde v3.40.14 para etiquetar "senal VIEJA".
    SIGNAL_MAX_AGE_MIN = float(os.getenv("SIGNAL_MAX_AGE_MIN", "10"))

    # v3.40.14 — Event window (conciencia de eventos en la ejecucion). off | shadow
    # (DEFAULT: etiqueta cada ejecucion con proximidad al evento + loguea que bloquearia,
    # SIN bloquear) | active (bloquea senales ciegas/viejas dentro de la ventana del evento
    # — NO activar sin data del shadow). Ventanas: HIGH 15min antes/30 despues; MED 5/15.
    EVENT_WINDOW_MODE = (os.getenv("EVENT_WINDOW_MODE", "shadow") or "shadow").lower()

    # v3.62.0 — Guard PRE-EVENTO para news (clase #969: CALL sobre una nota PREVIA al NFP,
    # 12,8 min antes del dato, SL 4p, spike de 34p => -$29,40 = 5,5% de la cuenta). news esta
    # exento del event-window porque se asume jugada POST-dato; esto cubre el caso PRE-dato:
    # una senal de news NO se ejecuta si hay un evento HIGH dentro de los proximos N minutos.
    # Post-dato sigue exento. Es vinculante SIEMPRE (independiente de EVENT_WINDOW_MODE, que
    # sigue en shadow). El 15 NO es un numero nuevo: es WIN_BEFORE['High'] del event-window
    # desde v3.40.14. 0 = apagado. Fail-open si el calendario no responde.
    NEWS_PRE_EVENT_GUARD_MIN = float(os.getenv("NEWS_PRE_EVENT_GUARD_MIN", "15"))

    # v3.40.20 — Pullback-QUALITY entry (experimento). El "pullback puro" ya existe
    # (trend_continuation) y PIERDE (n=103, 28% WR, -$153) por disparar sobre niveles de
    # RUIDO. La data dice que el edge real es la CALIDAD DEL NIVEL (por eso SMC es +EV).
    # Este detector exige nivel VALIDADO (>=2 toques, como SMC) + vela de rechazo, en
    # downtrend (vender el rally) / uptrend (comprar el dip). off / shadow / active:
    #   shadow (DEFAULT) = loguea a pullback_shadow_log con candle snapshot, NO opera,
    #     M5 vivo 100% intacto (no appendea a signals). Se mide FORWARD (sin re-sim SL/TP).
    #   active = opera (SOLO tras validacion forward + gate de significancia). NO usar a ciegas.
    PULLBACK_ENTRY_MODE = (os.getenv("PULLBACK_ENTRY_MODE", "shadow") or "shadow").lower()

    # v3.45.0 — FADE-EN-CHOP (experimento SHADOW). Hallazgo del checkpoint 3-Jul (data limpia
    # n=123): AIdan es breakout/momentum -> tiene edge REAL en expansion (ATR>8p: 46-54% WR, +EV)
    # y muere en el CHOP (ATR 3-8p: 16% WR, -$124, p=0.0002, el 57% de los SL-hit). El breakout
    # es FALSO en chop (serrucha, toca el stop). La logica correcta en chop es la INVERSA: fadear
    # los extremos de un nivel VALIDADO (>=2 toques) con vela de rechazo -> PUT en resistencia,
    # CALL en soporte, en AMBAS direcciones sin exigir htf (es rango, no tendencia). En vez de
    # SACAR los ~58 trades de chop, convertirlos en trades de reversion. off / shadow / active:
    #   shadow (DEFAULT) = loguea a fade_chop_shadow_log con candle snapshot, NO opera (vivo
    #     100% intacto). Se mide FORWARD (fav Y adverso, sin re-sim SL/TP).
    #   active = opera (SOLO tras validacion forward + gate de significancia). NO usar a ciegas.
    FADE_CHOP_MODE = (os.getenv("FADE_CHOP_MODE", "off") or "off").lower()
    # Banda de ATR (pips) que define el "chop" donde el breakout no tiene edge (medido 3-Jul).
    FADE_CHOP_ATR_MIN = float(os.getenv("FADE_CHOP_ATR_MIN", "3.0"))
    FADE_CHOP_ATR_MAX = float(os.getenv("FADE_CHOP_ATR_MAX", "8.0"))

    # v3.54.0 — TRACK D = swing DIARIO (D1) en SHADOW. Medido con tools/backtest_h4_d1.py
    # sobre 242 señales / 7,3 años de velas D1 del broker (2019 -> 2026):
    #   PF neto 1,40 · +16,3 pips/trade · 7 de 8 años positivos ·
    #   sin los 10 mejores trades sigue +6,8/trade ·
    #   19 de 19 combinaciones de (R:R, hold, SL) positivas => NO es overfit.
    # H4 se midio en el mismo barrido y se REFUTO (-0,98 pips/trade, 451 señales).
    # Arranca en SHADOW y no en active por 2 razones medidas, no por prudencia generica:
    #   1) el SWAP (-0,82 pips/noche comprado, hold medio 8 dias) se come 864 de los
    #      3.956 pips y deja el bootstrap en CI95 [-0,53, +26,9] => CRUZA CERO.
    #   2) SL medio 82p => lote = riesgo$/(SL*10) = 0,0078 < lote minimo 0,01 => el piso
    #      obliga a arriesgar 1,29% en vez de 1% (hasta 3,41%). El sizing no da con $639.
    #   off    = ni siquiera escanea.
    #   shadow = escanea y loguea a d1_shadow_log SIN crear estrategia ni mandar orden
    #            (los otros 3 tracks quedan 100% intactos). Se mide FORWARD con
    #            tools/score_d1_shadow.py (excursion favorable Y adversa, sin re-sim SL/TP).
    #   active = opera. NO usar sin resolver (1) y (2) de arriba.
    D1_TRACK_MODE = (os.getenv("D1_TRACK_MODE", "shadow") or "shadow").lower()
    # Cada cuanto mira si aparecio una vela D1 nueva. La vela cambia 1 vez por dia;
    # 15 min es holgado y barato (el scan real solo corre cuando cambio la vela).
    D1_SCAN_INTERVAL_SEC = int(os.getenv("D1_SCAN_INTERVAL_SEC", "900"))

    # v3.60.0 — SHADOW TRADER LLM (Groq gpt-oss-120b): un "operador" en PAPEL.
    # Ve numeros del mercado + posiciones abiertas y decide (open: CALL/PUT/NONE;
    # manage: CLOSE/HOLD) — todo se registra en shadow_trader_log, NADA se opera
    # ni se puede operar (el modulo no tiene path de ejecucion, hay test de eso).
    # Contexto: cada LLM medido decidiendo direccion aca PERDIO (news anti-skill
    # 53% vs drift 63%); esto existe para refutar o confirmar CON registro limpio.
    # Gate en tools/score_shadow_trader.py; a n>=40 sin separar => off.
    #   off    = no corre.
    #   shadow = decide y registra. NO existe 'active' a proposito.
    SHADOW_TRADER_MODE = (os.getenv("SHADOW_TRADER_MODE", "shadow") or "shadow").lower()
    # Ciclo del manage (por posicion abierta) y throttle del open-scan.
    # Quota Groq: ~96 open-scans/dia + manage solo con posicion abierta.
    SHADOW_TRADER_CYCLE_SEC = int(os.getenv("SHADOW_TRADER_CYCLE_SEC", "300"))
    SHADOW_TRADER_SCAN_SEC = int(os.getenv("SHADOW_TRADER_SCAN_SEC", "900"))

    # v3.63.0 — CALENDAR PLAY (shadow): mide la ruta del precio alrededor de cada release
    # HIGH USD/EUR del calendario (tick ~1s los primeros 3 min, hasta +15 min) para responder
    # con data propia si "operar el DATO" paga neto de spread real + comision. NO opera y no
    # existe modo 'active' a proposito. Gate en tools/score_calendar_play.py (n>=25 con
    # sorpresa; a n>=40 sin pasar => off).
    #   off | shadow
    CALENDAR_PLAY_MODE = (os.getenv("CALENDAR_PLAY_MODE", "shadow") or "shadow").lower()

    # v3.50.3 — get_setup_win_rates() tambien mira trade_archive (el cable que faltaba).
    # Auditado en runtime el 5-ago: la funcion devolvia SOLO 'news' porque lee de
    # signal_results (430 filas, todas news) y strategy_results (6 filas, 0 con setup_type)
    # e IGNORABA trade_archive, que es la tabla buena. Por eso el feedback historico estaba
    # MUERTO para structure/m15/h1/smc.
    # POR QUE NO SE ENCIENDE DE UNA: esta funcion no alimenta solo el paso 6 de dynamic_conf
    # (+-15); tambien la consume auto_tuner._update_blocked_setups(), que BLOQUEA un
    # setup_type con WR<35% y n>=5. Cablear a lo bruto = block en vivo con muestra de 5 =
    # exactamente el error que la metodologia prohibe (hour gate, late breakout 3p).
    #   log (DEFAULT) = calcula lo que el archivo aportaria y lo loguea, SIN devolverlo.
    #                   Vivo identico. Sirve para ver la tabla antes de confiar en ella.
    #   on  = lo devuelve (enciende paso 6 + impact_score + el block del tuner).
    #   off = ni lo calcula.
    # MIN_TRADES es el piso de muestra POR setup_type para que un setup entre siquiera a la
    # cuenta: 25 = el mismo n del gate de significancia de la casa. Hoy ningun setup del
    # archivo llega (33 filas repartidas en ~10 setups) => aun en 'on' seria no-op por ahora.
    SETUP_WR_SOURCE_ARCHIVE = (os.getenv("SETUP_WR_SOURCE_ARCHIVE", "log") or "log").lower()
    SETUP_WR_MIN_TRADES = int(os.getenv("SETUP_WR_MIN_TRADES", "25"))

    # v3.50.0 — Castigo de confianza por NIVEL FLOJO (pocos toques). Medido con P&L REAL
    # (level_quality_log JOIN trade_archive, m15 n=83, 5-ago): <=10 toques = n=10, 20% WR,
    # -$29.70 (9 de 10 pierden) vs >10 toques = n=73, 47% WR, +$61.70. Prevalencia 12%
    # (mediana 20 toques) => filtra poco volumen. NO es un block: RESTA confianza, asi que
    # con el piso min_conf 60 se caen los que entraban con conf<75 y sobreviven los muy
    # fuertes. Los 10 flojos medidos entraban con conf ALTA (90,90,83,81,78,75,73,73,68,60)
    # => el castigo es lo que los separa.
    # CAVEATS asumidos a proposito (n=10 NO pasa el gate formal, p=0.21; por prevalencia
    # quizas nunca lo pase => se decide con juicio calibrado, como se acordo el 31-jul):
    #   - `level_touches` usa tolerancia max(2, ATR*0.5) => correlaciona con volatilidad,
    #     no es calidad de nivel pura.
    #   - Arranca SOLO en M15 (donde se midio). M5 esta con la frecuencia ya golpeada por el
    #     tighten v3.46.0 (3 trades en 10 dias) y su muestra joinable es n=22 => sumarle un
    #     filtro no medido ahi seria apilar recortes a ciegas. H1 n=20, misma razon.
    # PENALTY=0 apaga todo (reversa por env, sin rebuild). Medir forward ~2 sem: cayo la
    # frecuencia de m15 mas de lo estimado (~12%)? mejoro el WR del resto?
    # CALIBRACION DEL NUMERO (probado contra los 10 flojos reales): con 15 se bloquean
    # 4/10 (los de conf<75) y se evitan ~$11.3 de los -$29.7 => se le ESCAPAN los dos
    # peores, que entraban con conf 90 y 83 (#683 -4.69, #834 -6.40). Con 25 se bloquean
    # 8/10 (~$25.2) pero eso ya es casi un block de la familia flojo, y a n=10 no hay
    # evidencia para tanto. Se eligio 15 = la version conservadora ("mejorar, no sacar"):
    # castiga a todos, deja pasar solo a los muy fuertes. Subir a 25 es 1 env var si el
    # forward confirma que los flojos de conf alta siguen perdiendo.
    LEVEL_QUALITY_PENALTY = int(os.getenv("LEVEL_QUALITY_PENALTY", "15"))
    LEVEL_QUALITY_MAX_TOUCHES = int(os.getenv("LEVEL_QUALITY_MAX_TOUCHES", "10"))
    LEVEL_QUALITY_TRACKS = [
        _t.strip().upper() for _t in
        (os.getenv("LEVEL_QUALITY_TRACKS", "M15") or "").split(",") if _t.strip()
    ]

    # v3.55.0 — PISO DE ATR DE M15, ahora perilla (antes 5.0 hardcodeado en el loop).
    #
    # QUE MIDE: el ATR de la vela M15 al momento de la señal (tech_m15.get_market_state()),
    # registrado en trade_archive.avg_range_pips EN EL MOMENTO, no reconstruido.
    #
    # POR QUE 8 Y NO 5 (medido 16-ago sobre la data limpia, 11-jun -> 14-ago, n=121):
    #     ATR <= 8p : n=90  WR 27.8%  -$75.59
    #     ATR >  8p : n=31  WR 51.6%  +$18.80
    # m15 necesita ~40.5% de WR para empatar (ganador medio +7.8p, perdedor -5.3p).
    # En chop saca 28%, en expansion 52%. Gate: p=0.0042, CI95 [33.1%, 69.8%] no cruza
    # el 27.8% del comparador, y los dos buckets cubren el MISMO periodo.
    #
    # LO QUE NO DICE (revision adversarial del propio hallazgo): el lado bueno es FRAGIL —
    # de los +$18.80, unos +$19.49 salen de 2 dias; sin esos dias queda en -$0.69. Lo que
    # si aguanta es el lado malo: <=8p pierde en las DOS mitades del periodo (28.9% y 26.7%).
    # Por eso esto NO es "m15 gana en expansion" sino "m15 sangra en chop de forma
    # confiable". Expectativa honesta: m15 deja de sangrar, no pasa a rentable.
    #
    # COSTO: se lleva el 74% de la frecuencia de m15 (3.27 -> 0.84 trades/dia).
    # El umbral NO se afina sobre esta muestra: 8 es el corte que ya estaba pre-declarado
    # en NOTAS desde el 17-jul; moverlo buscando el mejor numero seria overfit.
    M15_ATR_FLOOR = float(os.getenv("M15_ATR_FLOOR", "5.0"))

    # v3.49.0 — Feedback de learning_insights -> ajustes vivos (confianza + SL/TP).
    # Contexto: get_learning_adjustments crasheaba en CADA ciclo (TypeError por colision de
    # tipos entre la rama 'sl_tp' -string- y la rama 'post_trade' -dict-, db.py) desde hace
    # meses; el try envolvia el for entero => abortaba TODA la agregacion de insights. O sea:
    # el mecanismo nunca corrio completo, y lo poco que colaba dependia del orden de las filas.
    # Arreglar el crash NO es neutro: ENCIENDE un lazo que nunca se valido (mueve confianza
    # +-15 y el SL/TP vivo en los 5 tracks). Por eso arranca en 'log'. off / log / active:
    #   log (DEFAULT) = calcula TODO y lo persiste en learning_adjustments_log, pero NO lo
    #     aplica: lo que se devuelve al vivo sale solo del bloque EV sobre trade_archive
    #     (que nunca crasheo y ya era la parte viva). Comportamiento en vivo = el de hoy.
    #   active = ademas lo aplica (SOLO tras revisar una semana de log y decidir con datos).
    #   off = ni siquiera calcula (no loguea).
    # El bloque EV sobre trade_archive NO lo toca este flag: sigue vivo en los 3 modos.
    LEARNING_ADJ_MODE = (os.getenv("LEARNING_ADJ_MODE", "log") or "log").lower()

    # v3.46.0 — Tighten de entrada relativo-a-ATR (breakout/breakdown). El tope de distancia
    # precio<->nivel deja de ser 7p fijo y pasa a ser min(breakout_dist_max, ATR*MULT). Medido
    # con P&L REAL (level_quality_log JOIN trade_archive, 24-jul): la entrada PEGADA (<=0.5 ATR)
    # rinde 58% WR (n=26, p=0.028, CI [39-74%] no cruza baseline) y la cola >1 ATR pierde (-$11.9).
    # El cap a 1 ATR corta la cola perdedora dejando la zona que gana (<=1 ATR = +$42.5). Es
    # MONOTONICO: nunca afloja vs hoy (min()), solo aprieta -> M5 (ATR chico) se aprieta a su ATR,
    # m15/h1 (ATR grande) quedan en 7 (el motor no se toca). MULT=0 => apagado (comportamiento viejo).
    BREAKOUT_DIST_ATR_MULT = float(os.getenv("BREAKOUT_DIST_ATR_MULT", "1.0"))
    # Piso de la ventana (pips) para no colapsarla en ATR muy bajo (el ATR-gate ya bloquea <1.5p).
    BREAKOUT_DIST_ATR_FLOOR = float(os.getenv("BREAKOUT_DIST_ATR_FLOOR", "2.0"))

    # v3.40.4 — Calendar (straddle pre-news) mode. El trigger 'calendar' nunca opero (0/325):
    # el feed FF se auto-baneo (hammering -> 429) y ademas el straddle esta roto (anti-
    # contradiccion bloquea la 2da pata -> solo CALL). off | shadow (loguea el straddle SIN
    # operar, DEFAULT) | active (opera — requiere fix del straddle de ambas patas antes de usar).
    CALENDAR_MODE = (os.getenv("CALENDAR_MODE", "shadow") or "shadow").lower()

    # v3.36.0 Fase 2 — LLM Exit Advisor. Sub-flag del Position Manager.
    # Cuando true Y el manager esta en zona ambigua (soft-expiry HOLD), consulta a
    # Gemma local (fallback Groq) HOLD/CLOSE/TIGHTEN. CLOSE se respeta; HOLD queda
    # capeado por MAX_HOLD. Default FALSE: arranca solo cuando Fase 1 (reglas) valide.
    POSITION_MANAGER_LLM = os.getenv("POSITION_MANAGER_LLM", "false").lower() in ('true', '1', 'yes')
    # Rate-limit: minimo de minutos entre consultas LLM por posicion (evita spam/costo).
    PM_LLM_COOLDOWN_MIN = float(os.getenv("PM_LLM_COOLDOWN_MIN", "5"))

    # v3.61.0 - Perilla de las fuentes de noticias EXTRA (config/sources.yaml ->
    # `extra_sources`). Default FALSE a proposito: las 4 fuentes candidatas estan
    # vivas y medidas, pero enchufarlas multiplica el volumen de news x15-166
    # (Bloomberg publica 1,1 items/hora) y news pierde $0,91/trade sobre n=132
    # broker-truth => activarlas sin medir antes multiplicaria la perdida.
    # Cual merece entrar lo decide tools/measure_feed_race.py (quien reporta los
    # datos del calendario PRIMERO, no quien publica mas).
    NEWS_EXTRA_SOURCES = os.getenv("NEWS_EXTRA_SOURCES", "false").lower() in ('true', '1', 'yes')

    # v3.65.0 - Canal RAPIDO de noticias (src/collector/home_fast.py): la home de
    # investinglive se cachea 30 s contra 300 s (+ hasta 1 h stale) del RSS. Default
    # FALSE: apagado, el collector es identico a v3.64.0. Se gira por env sin rebuild
    # si la carrera home-vs-RSS (measure_feed_race.py --home-race) pasa su criterio.
    NEWS_HOME_FAST = os.getenv("NEWS_HOME_FAST", "false").lower() in ('true', '1', 'yes')
    NEWS_HOME_FAST_SEC = int(os.getenv("NEWS_HOME_FAST_SEC", "20"))

    @staticmethod
    def get_sources():
        """Load news sources from config file.

        Devuelve `sources` siempre, y le suma `extra_sources` solo si
        NEWS_EXTRA_SOURCES esta en true (env, sin rebuild).
        """
        config_path = "config/sources.yaml"
        if not os.path.exists(config_path):
            return []
        import yaml
        # encoding EXPLICITO: en Windows open() default es cp1252 y cualquier
        # caracter no-ASCII en un comentario del yaml tiraba UnicodeDecodeError
        # -> get_sources() explotaba y el collector quedaba sin fuentes.
        with open(config_path, encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        srcs = list(data.get("sources") or [])
        if Config.NEWS_EXTRA_SOURCES:
            srcs += list(data.get("extra_sources") or [])
        return srcs
