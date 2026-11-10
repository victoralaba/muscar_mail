import ast
import json
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logging import get_logger

logger = get_logger("muscar_mail.config")


class AccountSettings(BaseModel):
    """Configuration for an upstream Verifalia account and its authorized MCP API keys."""

    account_id: str
    username: str
    password: str
    base_url: str = "https://api.verifalia.com/v2.4"
    wait_time_ms: int = 30000
    api_keys: List[str]

    model_config = ConfigDict(extra="ignore")


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

    # Optional Additional Verifalia Accounts for Multi-Tenant / Multi-Org Support
    # Accepts JSON string, dict, or list of account definitions
    VERIFALIA_ADDITIONAL_ACCOUNTS: Optional[Union[str, Dict[str, Any], List[Dict[str, Any]]]] = None

    # Model Context Protocol Identity
    MCP_SERVER_NAME: str = "muscar-mail"
    MCP_SERVER_VERSION: str = "1.1.4"
    MCP_PROTOCOL_VERSION: str = "2026-07-28"
    SUPPORTED_MCP_PROTOCOL_VERSIONS: List[str] = ["2026-07-28", "2025-11-25", "2024-11-05"]

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

    def get_all_accounts(self) -> Dict[str, AccountSettings]:
        """Returns map of all configured accounts (default primary account + any additional org accounts)."""
        accounts: Dict[str, AccountSettings] = {}

        # 1. Primary/default account from root settings (always present)
        keys = (
            self.MCP_API_KEYS
            if isinstance(self.MCP_API_KEYS, list)
            else [k.strip() for k in str(self.MCP_API_KEYS).split(",") if k.strip()]
        )
        accounts["default"] = AccountSettings(
            account_id="default",
            username=self.VERIFALIA_USERNAME,
            password=self.VERIFALIA_PASSWORD,
            base_url=self.VERIFALIA_BASE_URL,
            wait_time_ms=self.VERIFALIA_WAIT_TIME_MS,
            api_keys=keys,
        )

        # 2. Additional org accounts if configured
        if self.VERIFALIA_ADDITIONAL_ACCOUNTS:
            raw = self.VERIFALIA_ADDITIONAL_ACCOUNTS
            parsed: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None

            if isinstance(raw, str) and raw.strip():
                cleaned = raw.strip()
                # Strip wrapping single/double quotes added by deployment UIs or env files
                while (cleaned.startswith("'") and cleaned.endswith("'")) or (cleaned.startswith('"') and cleaned.endswith('"')):
                    cleaned = cleaned[1:-1].strip()

                try:
                    parsed = json.loads(cleaned)
                except Exception:
                    try:
                        parsed = ast.literal_eval(cleaned)
                    except Exception:
                        try:
                            # Handle escaped JSON string if passed as \"{...}\"
                            parsed = json.loads(f'"{cleaned}"')
                            if isinstance(parsed, str):
                                parsed = json.loads(parsed)
                        except Exception as exc:
                            logger.error(
                                "Failed to parse VERIFALIA_ADDITIONAL_ACCOUNTS; skipping additional accounts.",
                                error=str(exc),
                            )
                            parsed = None

                if isinstance(parsed, str):
                    try:
                        parsed = json.loads(parsed)
                    except Exception:
                        pass
            elif isinstance(raw, (dict, list)):
                parsed = raw

            def _extract_keys(data: Dict[str, Any]) -> List[str]:
                raw = data.get("api_keys") or data.get("api_key") or data.get("MCP_API_KEYS") or data.get("key") or []
                if isinstance(raw, str):
                    raw = raw.split(",")
                if not isinstance(raw, (list, tuple)):
                    return []
                cleaned = []
                for item in raw:
                    k = str(item).strip()
                    while (k.startswith("'") and k.endswith("'")) or (k.startswith('"') and k.endswith('"')):
                        k = k[1:-1].strip()
                    if k:
                        cleaned.append(k)
                return cleaned

            if isinstance(parsed, dict):
                # Handle single account dict without nested account ID key (e.g. {"username": "...", "api_keys": [...]})
                if any(k in parsed for k in ("username", "VERIFALIA_USERNAME", "password", "VERIFALIA_PASSWORD", "api_keys", "api_key")):
                    acc_id = str(parsed.get("account_id") or "org2")
                    accounts[acc_id] = AccountSettings(
                        account_id=acc_id,
                        username=parsed.get("username") or parsed.get("VERIFALIA_USERNAME") or parsed.get("user") or "",
                        password=parsed.get("password") or parsed.get("VERIFALIA_PASSWORD") or parsed.get("pass") or "",
                        base_url=(parsed.get("base_url") or parsed.get("VERIFALIA_BASE_URL", self.VERIFALIA_BASE_URL)).rstrip("/"),
                        wait_time_ms=int(parsed.get("wait_time_ms") or parsed.get("VERIFALIA_WAIT_TIME_MS", self.VERIFALIA_WAIT_TIME_MS)),
                        api_keys=_extract_keys(parsed),
                    )
                else:
                    for acc_id, acc_data in parsed.items():
                        if isinstance(acc_data, dict):
                            accounts[acc_id] = AccountSettings(
                                account_id=acc_id,
                                username=acc_data.get("username") or acc_data.get("VERIFALIA_USERNAME") or acc_data.get("user") or "",
                                password=acc_data.get("password") or acc_data.get("VERIFALIA_PASSWORD") or acc_data.get("pass") or "",
                                base_url=(acc_data.get("base_url") or acc_data.get("VERIFALIA_BASE_URL", self.VERIFALIA_BASE_URL)).rstrip("/"),
                                wait_time_ms=int(acc_data.get("wait_time_ms") or acc_data.get("VERIFALIA_WAIT_TIME_MS", self.VERIFALIA_WAIT_TIME_MS)),
                                api_keys=_extract_keys(acc_data),
                            )
            elif isinstance(parsed, list):
                for idx, acc_data in enumerate(parsed):
                    if isinstance(acc_data, dict):
                        acc_id = acc_data.get("account_id") or f"org_{idx + 2}"
                        accounts[acc_id] = AccountSettings(
                            account_id=acc_id,
                            username=acc_data.get("username") or acc_data.get("VERIFALIA_USERNAME") or acc_data.get("user") or "",
                            password=acc_data.get("password") or acc_data.get("VERIFALIA_PASSWORD") or acc_data.get("pass") or "",
                            base_url=(acc_data.get("base_url") or acc_data.get("VERIFALIA_BASE_URL", self.VERIFALIA_BASE_URL)).rstrip("/"),
                            wait_time_ms=int(acc_data.get("wait_time_ms") or acc_data.get("VERIFALIA_WAIT_TIME_MS", self.VERIFALIA_WAIT_TIME_MS)),
                            api_keys=_extract_keys(acc_data),
                        )

        return accounts

    def get_account(self, account_id: str) -> Optional[AccountSettings]:
        """Returns specific account configuration by ID if defined."""
        return self.get_all_accounts().get(account_id)


@lru_cache()
def get_settings() -> Settings:
    """Instantiates and validates cached application settings. Fails fast if required variables are missing."""
    return Settings()


def reset_settings_cache() -> None:
    """Clears cached settings singleton (primarily for testing and environment reloads)."""
    get_settings.cache_clear()


def __getattr__(name: str) -> object:
    """Provides module-level lazy access to settings while ensuring explicit fail-fast validation."""
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
