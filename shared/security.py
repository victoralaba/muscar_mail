import secrets
from typing import Optional
from fastapi import Header, HTTPException, status

from core.config import AccountSettings, get_settings
from core.logging import get_logger

logger = get_logger("muscar_mail.security")


class AuthenticatedAccount(str):
    """String subclass representing an authenticated API key bound to an account identity.

    Subclasses str so it functions as a drop-in replacement for raw key strings, while
    exposing account_id, username, password, base_url, and wait_time_ms.
    """

    account_id: str
    username: str
    password: str
    base_url: str
    wait_time_ms: int
    matched_key: str

    def __new__(
        cls,
        matched_key: str,
        account_id: str,
        username: str,
        password: str,
        base_url: str = "https://api.verifalia.com/v2.4",
        wait_time_ms: int = 30000,
    ) -> "AuthenticatedAccount":
        instance = super().__new__(cls, matched_key)
        instance.matched_key = matched_key
        instance.account_id = account_id
        instance.username = username
        instance.password = password
        instance.base_url = base_url
        instance.wait_time_ms = wait_time_ms
        return instance


async def verify_mcp_api_key(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> AuthenticatedAccount:
    """Authenticates incoming requests using constant-time API key verification across all accounts.

    Supports both 'Authorization: Bearer <key>' and 'X-API-Key: <key>'.
    Enforces Invariant INV-SEC-1 (timing-attack immune comparison) and resolves the matching AccountContext.
    """
    provided_key: Optional[str] = None

    if authorization and isinstance(authorization, str):
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_key = parts[1]
        elif len(parts) == 1 and parts[0].lower() != "bearer":
            provided_key = parts[0]

    if not provided_key and x_api_key and isinstance(x_api_key, str):
        provided_key = x_api_key.strip()

    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key in Authorization or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_settings = get_settings()
    accounts = current_settings.get_all_accounts()

    # Constant-time comparison across all configured keys to eliminate timing leakage
    matched_account: Optional[AccountSettings] = None
    matched_key_val: Optional[str] = None

    for account in accounts.values():
        keys_list = account.api_keys if isinstance(account.api_keys, list) else [str(account.api_keys)]
        for valid_key in keys_list:
            if isinstance(valid_key, str) and secrets.compare_digest(provided_key, valid_key):
                matched_account = account
                matched_key_val = valid_key

    if not matched_account or not matched_key_val:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedAccount(
        matched_key=matched_key_val,
        account_id=matched_account.account_id,
        username=matched_account.username,
        password=matched_account.password,
        base_url=matched_account.base_url,
        wait_time_ms=matched_account.wait_time_ms,
    )
