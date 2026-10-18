"""
Application configuration loaded from environment variables and .env file.

FLOW MAP:
  .env / env vars → Settings (get_settings) → all application modules

KEY DETAILS:
  - Pydantic BaseSettings with lru_cache singleton via get_settings()
  - Supports both PostgreSQL (asyncpg) and SQLite (aiosqlite) database URLs
  - All secrets and connection strings are centralized here
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for the Patient Registration System.

    Values are loaded from environment variables, falling back to the
    .env file in the project root. All fields have safe defaults for
    local development.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_env: str = "local"
    app_name: str = "Gerta AI — Clinical Voice Agent"
    app_version: str = "1.0.0"
    debug: bool = True

    # --- Database ---
    database_url: str = (
        "postgresql+asyncpg://patient_reg:patient_reg_secret"
        "@localhost:5432/patient_registration"
    )

    # --- Vapi Voice AI ---
    vapi_api_key: str = ""
    vapi_phone_number_id: str = ""
    vapi_assistant_id: str = ""

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- CORS ---
    cors_origins: str = (
        "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000"
    )

    # --- Public URL (ngrok or deployed origin for Vapi webhooks) ---
    public_base_url: str = "http://localhost:8000"

    # --- Portal Clinical Admin Credentials ---
    admin_username: str = "admin@gerta.ai"
    admin_password: str = "admin123gertai"


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of application settings."""
    return Settings()
