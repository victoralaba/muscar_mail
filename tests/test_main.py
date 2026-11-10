import json
import time
from unittest.mock import AsyncMock, patch
import pytest
from starlette.testclient import TestClient
from core.config import get_settings
from main import app, create_app, lifespan
from domains.verification.schemas import (
    BatchVerificationResponse,
    CreditBalanceResponse,
    EmailVerificationResult,
)
from shared.exceptions import InsufficientCreditsError

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer test_key_1"}


# -----------------------------------------------------------------------------
# 1. Zero-Network Health Check Tests (Invariant INV-HEALTH-ZERO-NET)
# -----------------------------------------------------------------------------

def test_health_check_instantaneous_zero_network():
    """Validates Invariant INV-HEALTH-ZERO-NET: GET /health responds in <50ms without network dispatch."""
    with patch("domains.verification.service.verifalia_service.verify_emails") as mock_verify, \
         patch("shared.redis.redis_client.get") as mock_redis:

        start_time = time.perf_counter()
        response = client.get("/health")
        duration = time.perf_counter() - start_time

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["app"] == "muscar-mail"
        assert data["version"] == get_settings().MCP_SERVER_VERSION
        assert data["protocol_version"] == "2026-07-28"

        # Performance guarantee: instantaneous response (<50ms in test environment)
        assert duration < 0.05

        # Strict isolation: zero network or storage calls
        assert not mock_verify.called
        assert not mock_redis.called


# -----------------------------------------------------------------------------
# 2. Application Lifespan & Teardown Tests (Invariant INV-CLEAN-LIFESPAN)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_lifespan_lifecycle_graceful_shutdown():
    """Validates Invariant INV-CLEAN-LIFESPAN: Teardown properly closes HTTP and Redis pools."""
    with patch("main.verifalia_service.close", new_callable=AsyncMock) as mock_service_close, \
         patch("main.redis_client.close", new_callable=AsyncMock) as mock_redis_close:

        test_app = create_app()
        async with lifespan(test_app):
            # Application is running
            pass

        # Verify teardown cleanly invoked on shutdown
        mock_service_close.assert_awaited_once()
        mock_redis_close.assert_awaited_once()


# -----------------------------------------------------------------------------
# 3. CORS Preflight & Security Headers Tests
# -----------------------------------------------------------------------------

def test_cors_preflight_headers():
    """Validates: CORSMiddleware allows cross-origin requests with uncredentialed wildcard policy."""
    headers = {
        "Origin": "https://agent-sandbox.anthropic.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    }
    # Preflight for REST route
    resp_rest = client.options("/api/v1/verify", headers=headers)
    assert resp_rest.status_code == 200
    assert resp_rest.headers.get("access-control-allow-origin") == "*"
    assert resp_rest.headers.get("access-control-allow-credentials") is None

    # Preflight for MCP route
    resp_mcp = client.options("/mcp/v1/", headers=headers)
    assert resp_mcp.status_code == 200
    assert resp_mcp.headers.get("access-control-allow-origin") == "*"
    assert resp_mcp.headers.get("access-control-allow-credentials") is None


# -----------------------------------------------------------------------------
# 4. End-to-End Route Integration on Unified Application
# -----------------------------------------------------------------------------

def test_end_to_end_rest_verify_route():
    """Validates: POST /api/v1/verify resolves cleanly through unified main app."""
    mock_batch = BatchVerificationResponse(
        submitted=1,
        completed=1,
        cached=False,
        results=[
            EmailVerificationResult(
                email="app_test@example.com",
                classification="Deliverable",
                status="Success",
                is_deliverable=True,
                is_disposable=False,
                is_role_account=False,
                is_free_email=False,
            )
        ],
    )

    with patch("domains.verification.routes.verification_cache.get_cached_batch", new_callable=AsyncMock) as mock_get_cache, \
         patch("domains.verification.routes.verification_cache.is_daily_quota_available", new_callable=AsyncMock) as mock_quota, \
         patch("domains.verification.routes.verification_cache.cache_batch", new_callable=AsyncMock) as mock_cache_batch, \
         patch("domains.verification.routes.verification_cache.increment_daily_quota", new_callable=AsyncMock) as mock_incr, \
         patch("domains.verification.routes.verifalia_service.verify_emails", new_callable=AsyncMock) as mock_verify:

        mock_get_cache.return_value = None
        mock_quota.return_value = True
        mock_cache_batch.return_value = True
        mock_incr.return_value = 1
        mock_verify.return_value = mock_batch

        resp = client.post(
            "/api/v1/verify",
            json={"emails": ["app_test@example.com"]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["submitted"] == 1
        assert data["results"][0]["email"] == "app_test@example.com"
        assert data["results"][0]["is_deliverable"] is True


def test_end_to_end_rest_credits_route():
    """Validates: GET /api/v1/credits resolves cleanly through unified main app."""
    mock_bal = CreditBalanceResponse(
        credit_packs=10.0,
        free_credits=25.0,
        free_credits_reset_on="2026-11-09T00:00:00Z",
    )

    with patch("domains.verification.routes.verifalia_service.get_credit_balance", new_callable=AsyncMock) as mock_credits:
        mock_credits.return_value = mock_bal

        resp = client.get("/api/v1/credits", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["credit_packs"] == 10.0
        assert data["free_credits"] == 25.0


def test_end_to_end_mcp_routes():
    """Validates: POST /mcp/v1/ and /mcp/v1 resolve cleanly through unified main app."""
    # Test trailing slash route
    payload = {"jsonrpc": "2.0", "id": "main_mcp_1", "method": "ping"}
    resp1 = client.post("/mcp/v1/", json=payload, headers=AUTH_HEADERS)
    assert resp1.status_code == 200
    assert resp1.json()["id"] == "main_mcp_1"
    assert resp1.json()["result"] == {}

    # Test no-slash alias route
    resp2 = client.post("/mcp/v1", json=payload, headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == "main_mcp_1"


# -----------------------------------------------------------------------------
# 5. Global Domain Exception Translation Tests (Invariant INV-EXCEPTION-TRAP)
# -----------------------------------------------------------------------------

def test_end_to_end_exception_handler_translation():
    """Validates Invariant INV-EXCEPTION-TRAP: MuscarMailError translates to JSON status codes."""
    with patch("domains.verification.routes.verification_cache.get_cached_batch", new_callable=AsyncMock) as mock_get_cache, \
         patch("domains.verification.routes.verification_cache.is_daily_quota_available", new_callable=AsyncMock) as mock_quota:

        mock_get_cache.return_value = None
        mock_quota.return_value = False

        resp = client.post(
            "/api/v1/verify",
            json={"emails": ["quota_fail@example.com"]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 402
        data = resp.json()
        assert "Daily free-tier verification quota reached" in data["error"]


# -----------------------------------------------------------------------------
# 6. Documentation & OpenAPI Catalog Tests
# -----------------------------------------------------------------------------

def test_openapi_catalog_endpoints():
    """Validates: OpenAPI schema catalogs both REST and MCP surfaces."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    openapi = resp.json()
    paths = openapi.get("paths", {})

    assert "/health" in paths
    assert "/api/v1/verify" in paths
    assert "/api/v1/credits" in paths
    assert "/mcp/v1/" in paths


def test_homepage_html_render():
    """Validates: GET / returns 200 HTML page with link to muscar.app and github repo."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Muscar Mail" in resp.text
    assert "https://muscar.app" in resp.text
    assert "https://github.com/victoralaba/muscar_mail" in resp.text
