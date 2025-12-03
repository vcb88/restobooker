import os

class Config:
    # Telegram API credentials (mock values)
    API_ID = int(os.getenv("TG_API_ID", "1234567"))  # Replace with your actual API ID
    API_HASH = os.getenv("TG_API_HASH", "your_api_hash_hash_here")  # Replace with your actual API Hash
    SESSION_NAME = "iron_business_hostess"

    # LLM API credentials
    # Supports OpenAI, OpenRouter, Ollama, LMStudio, etc.
    LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-or-...") 
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1") 
    LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-3.5-turbo") # e.g., "meta-llama/llama-3.1-8b-instruct" or "llama3" for Ollama

    # Timezone for reservations
    TIMEZONE = "Europe/Moscow" # GMT+3

    # Restaurant capacity
    TABLE_CAPACITY = 1 # For simplicity, one table
    SLOT_DURATION_MINUTES = 30 # Each reservation blocks for 30 minutes
