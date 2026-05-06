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

APP_VERSION = "3.18.0"

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
    GOOGLE_SHEETS_WEBHOOK = os.getenv("GOOGLE_SHEETS_WEBHOOK", "https://script.google.com/macros/s/AKfycbzZqRaz_37eSjky1I4F1-2bnQQtRPC15_wDGA5ohxUvzTPq38ez74mbc7oYoNb4NvfyFw/exec")

    # MT5 Broker Integration
    MT5_ENABLED = os.getenv("MT5_ENABLED", "false").lower() == "true"
    MT5_ACCOUNT = int(os.getenv("MT5_ACCOUNT", "0"))
    MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER = os.getenv("MT5_SERVER", "ICMarketsSC-Demo")
    MT5_SYMBOL = os.getenv("MT5_SYMBOL", "EURUSD")

    @staticmethod
    def get_sources():
        """Load news sources from config file"""
        config_path = "config/sources.yaml"
        if os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f).get("sources", [])
        return []
