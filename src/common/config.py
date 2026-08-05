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

APP_VERSION = "3.50.0"

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
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    # Faster, smaller Groq model for dashboard chat — non-critical, latency-sensitive.
    GROQ_MODEL_CHAT = os.getenv("GROQ_MODEL_CHAT", "llama-3.1-8b-instant")
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

    # v3.40.14 — Event window (conciencia de eventos en la ejecucion). off | shadow
    # (DEFAULT: etiqueta cada ejecucion con proximidad al evento + loguea que bloquearia,
    # SIN bloquear) | active (bloquea senales ciegas/viejas dentro de la ventana del evento
    # — NO activar sin data del shadow). Ventanas: HIGH 15min antes/30 despues; MED 5/15.
    EVENT_WINDOW_MODE = (os.getenv("EVENT_WINDOW_MODE", "shadow") or "shadow").lower()

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

    @staticmethod
    def get_sources():
        """Load news sources from config file"""
        config_path = "config/sources.yaml"
        if os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f).get("sources", [])
        return []
