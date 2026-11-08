import logging
import secrets
from typing import Optional
from fastapi import Header, HTTPException, status

from core.config import get_settings, settings

logger = logging.getLogger("muscar_mail.security")


async def verify_mcp_api_key(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """Authenticates incoming requests using constant-time API key verification.

    Supports both 'Authorization: Bearer <key>' and 'X-API-Key: <key>'.
    Enforces Invariant INV-SEC-1: timing-attack immune string comparison.
    """
    provided_key: Optional[str] = None

    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_key = parts[1]
        elif len(parts) == 1:
            provided_key = parts[0]

    if not provided_key and x_api_key:
        provided_key = x_api_key.strip()

    current_settings = settings or get_settings()
    valid_keys = current_settings.MCP_API_KEYS

    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key in Authorization or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison across all configured keys to eliminate timing leakage
    matched = False
    for valid_key in valid_keys:
        if secrets.compare_digest(provided_key, valid_key):
            matched = True

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return provided_key
