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

APP_VERSION = "3.28.0"

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

    @staticmethod
    def get_sources():
        """Load news sources from config file"""
        config_path = "config/sources.yaml"
        if os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f).get("sources", [])
        return []
