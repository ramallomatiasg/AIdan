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
    
    @staticmethod
    def get_sources():
        """Load news sources from config file"""
        config_path = "config/sources.yaml"
        if os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f).get("sources", [])
        return []
