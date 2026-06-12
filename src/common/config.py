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

APP_VERSION = "3.40.15"

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
