import os
from dotenv import load_dotenv
import json

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    COLLECTOR_INTERVAL = int(os.getenv("COLLECTOR_INTERVAL", "600"))  # 10 min
    ANALYZER_INTERVAL = int(os.getenv("ANALYZER_INTERVAL", "120"))    # 2 min
    DATA_RETENTION_HOURS = int(os.getenv("DATA_RETENTION_HOURS", "72"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
    GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "config/google_creds.json")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
    GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "AIdan - Trading Report")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    @staticmethod
    def get_sources():
        """Load news sources from config file"""
        config_path = "config/sources.yaml"
        if os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f).get("sources", [])
        return []
