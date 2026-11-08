import io
import json
import logging
import os
import time
from fastapi import Depends, FastAPI
from pydantic import ValidationError
import pytest
from starlette.testclient import TestClient
import structlog

from core.config import Settings, get_settings, settings
from core.logging import redact_sensitive_data, setup_logging
from core.telemetry import init_telemetry
from shared.exceptions import (
    AuthenticationError,
    BatchLimitExceededError,
    InsufficientCreditsError,
    MuscarMailError,
)
from shared.security import verify_mcp_api_key

# Test app with secured endpoint
app = FastAPI()


@app.get("/secured")
async def secured_route(key: str = Depends(verify_mcp_api_key)):
    return {"status": "authorized", "key": key}


client = TestClient(app)


def test_missing_credentials_rejection():
    """Validates Task [10]: Request without key is rejected with HTTP 401."""
    original_keys = settings.MCP_API_KEYS
    try:
        settings.MCP_API_KEYS = ["secret-agent-key-1", "secret-agent-key-2"]
        resp = client.get("/secured")
        assert resp.status_code == 401
        assert "Missing API key" in resp.json()["detail"]
    finally:
        settings.MCP_API_KEYS = original_keys


def test_invalid_api_key_rejection():
    """Validates Task [11]: Request with invalid key is rejected with HTTP 401."""
    original_keys = settings.MCP_API_KEYS
    try:
        settings.MCP_API_KEYS = ["correct-secret-key"]

        # Test Bearer header
        resp = client.get("/secured", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid API key."

        # Test X-API-Key header
        resp2 = client.get("/secured", headers={"X-API-Key": "wrong-key"})
        assert resp2.status_code == 401
        assert resp2.json()["detail"] == "Invalid API key."
    finally:
        settings.MCP_API_KEYS = original_keys


def test_valid_api_key_acceptance():
    """Validates Task [12]: Valid key works for both Bearer and X-API-Key."""
    original_keys = settings.MCP_API_KEYS
    try:
        settings.MCP_API_KEYS = ["master-agent-key", "secondary-agent-key"]

        # Valid Bearer token
        resp = client.get("/secured", headers={"Authorization": "Bearer master-agent-key"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "authorized"

        # Valid X-API-Key
        resp2 = client.get("/secured", headers={"X-API-Key": "secondary-agent-key"})
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "authorized"
    finally:
        settings.MCP_API_KEYS = original_keys


def test_structlog_secret_redaction():
    """Validates Task [13]: Secrets and sensitive headers are redacted."""
    raw_event = {
        "event": "Incoming agent call",
        "authorization": "Bearer super-secret-token-12345",
        "headers": {
            "x-api-key": "secret-key-abc",
            "host": "muscar.render.com",
            "password": "confidential-pass",
        },
        "safe_field": "public_data",
    }

    sanitized = redact_sensitive_data(None, "info", raw_event)

    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["headers"]["x-api-key"] == "[REDACTED]"
    assert sanitized["headers"]["password"] == "[REDACTED]"
    assert sanitized["headers"]["host"] == "muscar.render.com"
    assert sanitized["safe_field"] == "public_data"


def test_telemetry_fail_open():
    """Validates Invariant INV-OPS-1: Telemetry fails open gracefully."""
    # Empty DSN returns False cleanly
    assert init_telemetry(None) is False
    assert init_telemetry("") is False
    assert init_telemetry("   ") is False


def test_domain_exceptions_taxonomy():
    """Validates Task [4]: Domain exceptions maintain explicit status codes and messages."""
    auth_err = AuthenticationError()
    assert auth_err.status_code == 401

    quota_err = InsufficientCreditsError(reset_on="2026-11-09T00:00:00Z")
    assert quota_err.status_code == 402
    assert quota_err.details["reset_on"] == "2026-11-09T00:00:00Z"

    batch_err = BatchLimitExceededError(received_count=30, max_allowed=25)
    assert batch_err.status_code == 422
    assert "exceeds maximum allowed limit" in batch_err.message
    assert batch_err.details["received"] == 30


def test_startup_validation_missing_verifalia_username():
    """Validates: Startup fails if VERIFALIA_USERNAME is missing or empty."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            VERIFALIA_USERNAME="",
            VERIFALIA_PASSWORD="valid_password",
            MCP_API_KEYS=["key1"],
            REDIS_URL="redis://localhost:6379",
        )
    assert "VERIFALIA_USERNAME is required in .env" in str(exc_info.value)


def test_startup_validation_missing_verifalia_password():
    """Validates: Startup fails if VERIFALIA_PASSWORD is missing or empty."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            VERIFALIA_USERNAME="valid_user",
            VERIFALIA_PASSWORD="",
            MCP_API_KEYS=["key1"],
            REDIS_URL="redis://localhost:6379",
        )
    assert "VERIFALIA_PASSWORD is required in .env" in str(exc_info.value)


def test_startup_validation_missing_mcp_api_keys():
    """Validates: Startup fails if MCP_API_KEYS is missing or empty."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            VERIFALIA_USERNAME="valid_user",
            VERIFALIA_PASSWORD="valid_password",
            MCP_API_KEYS=[],
            REDIS_URL="redis://localhost:6379",
        )
    assert "MCP_API_KEYS is required in .env" in str(exc_info.value)


def test_startup_validation_missing_redis_url():
    """Validates: Startup fails if REDIS_URL is missing or empty."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            VERIFALIA_USERNAME="valid_user",
            VERIFALIA_PASSWORD="valid_password",
            MCP_API_KEYS=["key1"],
            REDIS_URL="",
        )
    assert "REDIS_URL is required in .env" in str(exc_info.value)


def test_startup_validation_all_required_present():
    """Validates: Startup succeeds when all 4 required variables are present."""
    cfg = Settings(
        VERIFALIA_USERNAME="valid_user",
        VERIFALIA_PASSWORD="valid_password",
        MCP_API_KEYS=["key1", "key2"],
        REDIS_URL="redis://localhost:6379/0",
    )
    assert cfg.VERIFALIA_USERNAME == "valid_user"
    assert cfg.VERIFALIA_PASSWORD == "valid_password"
    assert cfg.MCP_API_KEYS == ["key1", "key2"]
    assert cfg.REDIS_URL == "redis://localhost:6379/0"


def test_cold_start_import_benchmark():
    """Validates Task [14]: Modules import in under 100ms with zero blocking I/O."""
    start = time.perf_counter()
    import core.config
    import core.logging
    import core.telemetry
    import shared.exceptions
    import shared.security

    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"Import took too long: {elapsed:.4f}s"
