from typing import List, Optional, Union
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime Environment
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # Server Bind Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Required Verifalia Credentials
    VERIFALIA_USERNAME: str
    VERIFALIA_PASSWORD: str
    VERIFALIA_BASE_URL: str = "https://api.verifalia.com/v2.4"
    VERIFALIA_WAIT_TIME_MS: int = 30000

    # Quota Invariant: Maximum 25 emails per batch request
    MAX_BATCH_SIZE: int = 25

    # Required MCP Server API Authentication Keys (comma-separated or list)
    MCP_API_KEYS: Union[str, List[str]]

    # Required Redis Connection URL (Upstash, Render, or Redis Cloud)
    REDIS_URL: str

    # Optional Telemetry (Sentry)
    SENTRY_DSN: Optional[str] = None

    # Model Context Protocol Identity
    MCP_SERVER_NAME: str = "muscar-mail"
    MCP_SERVER_VERSION: str = "1.0.0"
    MCP_PROTOCOL_VERSION: str = "2024-11-05"

    @field_validator("VERIFALIA_USERNAME", "VERIFALIA_PASSWORD", "REDIS_URL")
    @classmethod
    def validate_non_empty(cls, v: str, info: ValidationInfo) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} is required in .env and cannot be empty.")
        return v.strip()

    @field_validator("MCP_API_KEYS")
    @classmethod
    def parse_api_keys(cls, v: Union[str, List[str]]) -> List[str]:
        keys = []
        if isinstance(v, str):
            keys = [k.strip() for k in v.split(",") if k.strip()]
        elif isinstance(v, list):
            keys = [str(k).strip() for k in v if str(k).strip()]

        if not keys:
            raise ValueError("MCP_API_KEYS is required in .env and must contain at least one valid key.")
        return keys

    @field_validator("VERIFALIA_BASE_URL")
    @classmethod
    def normalize_base_url(cls, v: str) -> str:
        return v.rstrip("/")


def get_settings() -> Settings:
    """Instantiates and validates application settings. Fails fast if required variables are missing."""
    return Settings()


# Instantiate default application settings
settings: Settings
try:
    settings = get_settings()
except Exception:
    # If required environment variables are missing during initial import, settings will be None
    # and get_settings() can be called when env is ready.
    settings = None  # type: ignore[assignment]
