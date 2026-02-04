# app/core/settings.py
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Centralized configuration management using Pydantic.
    Reads from .env file and environment variables.
    """
    # --- Sensitive Data ---
    ONEOFFICE_TOKEN: SecretStr
    ONEOFFICE_PERSONNEL_TOKEN: SecretStr = SecretStr("")  # Token for personnel API (birthday)
    GOOGLE_API_KEY: SecretStr

    # --- Zalo / Reminder Config ---
    MY_ZALO_ID: str = "" 
    FRONTEND_SERVICE_URL: str = "http://frontend:3000"
    
    # --- Google Apps Script Config ---
    GOOGLE_APPS_SCRIPT_URL: str = ""

    # --- 1Office Default Config ---
    DEFAULT_ASSIGNEE: str = Field("Tạ Hoàng Nam", alias='DEFAULT_ASSIGNEE_NAME')
    DEFAULT_ASSIGNEE_ID: str = "0" # Default, should be set in .env
    ONEOFFICE_LINK: str = "https://innojsc.1office.vn" # Added missing attribute

    # --- Application Settings ---
    LOG_LEVEL: str = "INFO"
    SESSION_TIMEOUT_SECONDS: int = 7200

    # --- MCP Agent Settings ---
    USE_MCP_AGENT: bool = True  # Set to True to use new MCP agent, False for legacy

    # Pydantic V2 Config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

# Create a singleton instance
try:
    settings = Settings()
except Exception as e:
    print(f"CRITICAL: Error loading configuration. Check your .env file. Error: {e}")
    # We might not want to exit here in a larger app, but for now it's safer
    import sys
    sys.exit(1)
