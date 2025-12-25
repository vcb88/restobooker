import os
import yaml

class Config:
    # Telegram API credentials
    API_ID = int(os.getenv("TG_API_ID", "1234567"))
    API_HASH = os.getenv("TG_API_HASH", "your_api_hash_here")
    SESSION_NAME = os.getenv("TG_SESSION_NAME", "iron_business_hostess")

    # LLM Settings
    LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-or-...") 
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "x-ai/grok-4.1-fast:free")

    # Timezone
    TIMEZONE = "Europe/Moscow"
    SLOT_DURATION_MINUTES = 30

    @classmethod
    def get_tables(cls):
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        yaml_path = os.path.join(base_path, "tables.yaml")
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data.get('tables', [])
        except Exception as e:
            print(f"Error loading tables.yaml: {e}")
            return []

    # Initialize TABLES at class level
    TABLES = [] 

# Note: In a real app we might want to load this once
Config.TABLES = Config.get_tables()