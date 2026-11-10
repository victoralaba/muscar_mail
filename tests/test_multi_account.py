import json
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from core.config import AccountSettings, Settings, get_settings
from domains.mcp.handlers import MCPHandler
from domains.mcp.protocol import JSONRPCRequest
from domains.verification.cache import VerificationCache
from domains.verification.schemas import (
    BatchVerificationResponse,
    CreditBalanceResponse,
    EmailVerificationResult,
)
from domains.verification.service import VerifaliaService, VerifaliaServiceRegistry
from main import app
from shared.exceptions import InsufficientCreditsError
from shared.security import AuthenticatedAccount, verify_mcp_api_key

client = TestClient(app)


def test_config_multi_account_parsing():
    """Validates: VERIFALIA_ADDITIONAL_ACCOUNTS is correctly parsed into AccountSettings map."""
    accounts_json = json.dumps({
        "org2": {
            "username": "org2_user",
            "password": "org2_pass",
            "api_keys": ["org2_key_1", "org2_key_2"],
        },
        "org3": {
            "username": "org3_user",
            "password": "org3_pass",
            "api_keys": "org3_single_key",
        },
    })

    cfg = Settings(
        VERIFALIA_USERNAME="org1_user",
        VERIFALIA_PASSWORD="org1_pass",
        MCP_API_KEYS=["org1_key_1"],
        REDIS_URL="redis://localhost:6379",
        VERIFALIA_ADDITIONAL_ACCOUNTS=accounts_json,
    )

    all_accounts = cfg.get_all_accounts()
    assert len(all_accounts) == 3
    assert "default" in all_accounts
    assert "org2" in all_accounts
    assert "org3" in all_accounts

    assert all_accounts["default"].username == "org1_user"
    assert all_accounts["default"].api_keys == ["org1_key_1"]

    assert all_accounts["org2"].username == "org2_user"
    assert all_accounts["org2"].password == "org2_pass"
    assert all_accounts["org2"].api_keys == ["org2_key_1", "org2_key_2"]

    assert all_accounts["org3"].username == "org3_user"
    assert all_accounts["org3"].api_keys == ["org3_single_key"]


def test_config_multi_account_resilient_quoting():
    """Validates: VERIFALIA_ADDITIONAL_ACCOUNTS handles single-quoted, double-quoted, and escaped JSON."""
    raw_with_single_quotes = "'{\"org2\": {\"username\": \"user2\", \"password\": \"pass2\", \"api_keys\": [\"k2\"]}}'"
    cfg1 = Settings(
        VERIFALIA_USERNAME="user1",
        VERIFALIA_PASSWORD="pass1",
        MCP_API_KEYS=["k1"],
        REDIS_URL="redis://localhost:6379",
        VERIFALIA_ADDITIONAL_ACCOUNTS=raw_with_single_quotes,
    )
    accs1 = cfg1.get_all_accounts()
    assert "org2" in accs1
    assert accs1["org2"].username == "user2"

    # Flat single account dict without nested account ID key
    flat_dict_json = json.dumps({
        "username": "user_flat",
        "password": "pass_flat",
        "api_keys": ["k_flat"],
    })
    cfg2 = Settings(
        VERIFALIA_USERNAME="user1",
        VERIFALIA_PASSWORD="pass1",
        MCP_API_KEYS=["k1"],
        REDIS_URL="redis://localhost:6379",
        VERIFALIA_ADDITIONAL_ACCOUNTS=flat_dict_json,
    )
    accs2 = cfg2.get_all_accounts()
    assert "org2" in accs2
    assert accs2["org2"].username == "user_flat"
    assert accs2["org2"].api_keys == ["k_flat"]

    # Python dict string format
    dict_repr = "{'org3': {'username': 'user3', 'password': 'pass3', 'api_keys': ['k3']}}"
    cfg2 = Settings(
        VERIFALIA_USERNAME="user1",
        VERIFALIA_PASSWORD="pass1",
        MCP_API_KEYS=["k1"],
        REDIS_URL="redis://localhost:6379",
        VERIFALIA_ADDITIONAL_ACCOUNTS=dict_repr,
    )
    accs2 = cfg2.get_all_accounts()
    assert "org3" in accs2

    # Truncated JSON missing trailing closing brace
    truncated_json = '{"org2":{"username":"org2_u","password":"org2_p","api_keys":["org2_k"]}'
    cfg3 = Settings(
        VERIFALIA_USERNAME="user1",
        VERIFALIA_PASSWORD="pass1",
        MCP_API_KEYS=["k1"],
        REDIS_URL="redis://localhost:6379",
        VERIFALIA_ADDITIONAL_ACCOUNTS=truncated_json,
    )
    accs3 = cfg3.get_all_accounts()
    assert "org2" in accs3
    assert accs3["org2"].username == "org2_u"
    assert accs3["org2"].api_keys == ["org2_k"]
    assert accs2["org3"].username == "user3"


def test_authenticated_account_str_subclass():
    """Validates: AuthenticatedAccount is a string subclass retaining account metadata."""
    auth = AuthenticatedAccount(
        matched_key="secret-key",
        account_id="org2",
        username="user2",
        password="pass2",
    )

    assert isinstance(auth, str)
    assert auth == "secret-key"
    assert f"Bearer {auth}" == "Bearer secret-key"
    assert auth.account_id == "org2"
    assert auth.username == "user2"


@pytest.mark.anyio
async def test_auth_resolves_correct_account_identity():
    """Validates: verify_mcp_api_key matches against secondary account keys and resolves identity."""
    current_settings = get_settings()
    original_additional = current_settings.VERIFALIA_ADDITIONAL_ACCOUNTS
    original_keys = current_settings.MCP_API_KEYS

    try:
        current_settings.MCP_API_KEYS = ["key_org1"]
        current_settings.VERIFALIA_ADDITIONAL_ACCOUNTS = {
            "org2": {
                "username": "user_org2",
                "password": "pass_org2",
                "api_keys": ["key_org2_secret"],
            }
        }

        # 1. Primary key resolves default account
        auth_default = await verify_mcp_api_key(authorization="Bearer key_org1")
        assert auth_default.account_id == "default"
        assert auth_default == "key_org1"

        # 2. Org2 key resolves org2 account
        auth_org2 = await verify_mcp_api_key(authorization="Bearer key_org2_secret")
        assert auth_org2.account_id == "org2"
        assert auth_org2.username == "user_org2"
        assert auth_org2 == "key_org2_secret"

        # 3. Org2 key via X-API-Key header
        auth_org2_header = await verify_mcp_api_key(x_api_key="key_org2_secret")
        assert auth_org2_header.account_id == "org2"

        # 4. Invalid key raises 401
        with pytest.raises(Exception) as exc_info:
            await verify_mcp_api_key(authorization="Bearer non_existent_key")
        assert exc_info.value.status_code == 401

    finally:
        current_settings.MCP_API_KEYS = original_keys
        current_settings.VERIFALIA_ADDITIONAL_ACCOUNTS = original_additional


@pytest.mark.anyio
async def test_quota_isolation_between_accounts():
    """Validates Invariant INV-QUOTA-ISOLATION: Org 1 quota exhaustion does not lock out Org 2."""
    mock_redis = AsyncMock()
    cache = VerificationCache(client=mock_redis)

    # Simulate Org 1 has used 25 credits today, but Org 2 has used 0
    async def mock_get(key):
        if "default" in key or key.endswith(VerificationCache.get_today_quota_key("default")):
            return "25"
        elif "org2" in key:
            return "0"
        return None

    mock_redis.get.side_effect = mock_get

    # Org 1 should be blocked
    assert await cache.is_daily_quota_available(1, account_id="default") is False

    # Org 2 should have full quota available
    assert await cache.is_daily_quota_available(1, account_id="org2") is True
    assert await cache.is_daily_quota_available(25, account_id="org2") is True


@pytest.mark.anyio
async def test_cross_tenant_zero_credit_cache_sharing():
    """Validates: Both orgs share the global batch cache, saving credits for identical emails."""
    mock_redis = AsyncMock()
    cache = VerificationCache(client=mock_redis)

    emails = ["shared@example.com"]
    response = BatchVerificationResponse(
        submitted=1,
        completed=1,
        cached=False,
        results=[
            EmailVerificationResult(
                email="shared@example.com",
                classification="Deliverable",
                status="Success",
                is_deliverable=True,
                is_disposable=False,
                is_role_account=False,
                is_free_email=False,
            )
        ],
    )

    # 1. Org 1 caches the batch
    mock_redis.set.return_value = True
    await cache.cache_batch(emails=emails, response=response)
    cache_key = VerificationCache.get_batch_cache_key(emails)
    mock_redis.set.assert_called_once()
    assert mock_redis.set.call_args[0][0] == cache_key

    # 2. Org 2 requests the same batch
    mock_redis.get.return_value = response.model_dump_json()
    recovered = await cache.get_cached_batch(emails)

    assert recovered is not None
    assert recovered.cached is True
    assert recovered.results[0].email == "shared@example.com"


@pytest.mark.anyio
async def test_mcp_handler_dispatches_with_account_context():
    """Validates: MCPHandler routes tool calls using the authenticated account's credentials."""
    mock_service_default = AsyncMock()
    mock_service_org2 = AsyncMock()

    mock_cache = AsyncMock()
    mock_cache.get_cached_batch.return_value = None
    mock_cache.is_daily_quota_available.return_value = True
    mock_cache.cache_batch.return_value = True
    mock_cache.increment_daily_quota.return_value = 1

    handler = MCPHandler(service=mock_service_default, cache=mock_cache)

    account_org2 = AuthenticatedAccount(
        matched_key="key_org2",
        account_id="org2",
        username="user2",
        password="pass2",
    )

    request = JSONRPCRequest(
        id=1,
        jsonrpc="2.0",
        method="tools/call",
        params={
            "name": "verify_emails",
            "arguments": {"emails": ["test@example.com"]},
        },
    )

    with patch("domains.mcp.handlers.service_registry") as mock_registry:
        mock_registry.get_service.return_value = mock_service_org2
        mock_service_org2.verify_emails.return_value = BatchVerificationResponse(
            submitted=1,
            completed=1,
            cached=False,
            results=[
                EmailVerificationResult(
                    email="test@example.com",
                    classification="Deliverable",
                    status="Success",
                    is_deliverable=True,
                    is_disposable=False,
                    is_role_account=False,
                    is_free_email=False,
                )
            ],
        )

        resp = await handler.handle_request(request, account=account_org2)
        assert resp.error is None
        assert resp.result is not None
        assert "Deliverable" in resp.result["content"][0]["text"]

        # Assert org2 service was resolved and invoked
        mock_registry.get_service.assert_called_once_with(
            account_id="org2",
            username="user2",
            password="pass2",
            base_url="https://api.verifalia.com/v2.4",
        )
        mock_service_org2.verify_emails.assert_called_once_with(emails=["test@example.com"])
        # Assert default service was NOT called
        mock_service_default.verify_emails.assert_not_called()
        # Assert quota was tracked under org2
        mock_cache.increment_daily_quota.assert_called_once_with(amount=1, account_id="org2")


@pytest.mark.anyio
async def test_service_registry_lifecycle():
    """Validates: VerifaliaServiceRegistry caches instances and closes all pools cleanly on teardown."""
    registry = VerifaliaServiceRegistry()

    svc_default = registry.get_service("default", username="u1", password="p1")
    svc_org2 = registry.get_service("org2", username="u2", password="p2")

    # Re-querying should return same instances (pool reuse)
    assert registry.get_service("default") is svc_default
    assert registry.get_service("org2") is svc_org2
    assert svc_default is not svc_org2

    # Mock close methods and verify teardown
    svc_default.close = AsyncMock()
    svc_org2.close = AsyncMock()

    await registry.close_all()
    svc_default.close.assert_called_once()
    svc_org2.close.assert_called_once()
    assert len(registry._services) == 0


def test_client_mcp_and_rest_endpoints_with_org2_key():
    """Validates: End-to-end HTTP requests with Org 2 API key route through Org 2 credentials."""
    current_settings = get_settings()
    original_additional = current_settings.VERIFALIA_ADDITIONAL_ACCOUNTS
    original_keys = current_settings.MCP_API_KEYS

    try:
        current_settings.MCP_API_KEYS = ["key_org1"]
        current_settings.VERIFALIA_ADDITIONAL_ACCOUNTS = {
            "org2": {
                "username": "user_org2",
                "password": "pass_org2",
                "api_keys": ["key_org2_secret"],
            }
        }

        mock_response = BatchVerificationResponse(
            submitted=1,
            completed=1,
            cached=False,
            results=[
                EmailVerificationResult(
                    email="client@org2.com",
                    classification="Deliverable",
                    status="Success",
                    is_deliverable=True,
                    is_disposable=False,
                    is_role_account=False,
                    is_free_email=False,
                )
            ],
        )

        mock_svc_org2 = AsyncMock()
        mock_svc_org2.verify_emails.return_value = mock_response
        mock_svc_org2.get_credit_balance.return_value = CreditBalanceResponse(
            credit_packs=0.0,
            free_credits=25.0,
            free_credits_reset_on="2026-11-11T00:00:00Z",
        )

        with patch("domains.mcp.handlers.service_registry") as mock_mcp_registry, \
             patch("domains.verification.routes.service_registry") as mock_routes_registry, \
             patch("domains.mcp.handlers.verification_cache") as mock_mcp_cache, \
             patch("domains.verification.routes.verification_cache") as mock_routes_cache:

            mock_mcp_registry.get_service.return_value = mock_svc_org2
            mock_routes_registry.get_service.return_value = mock_svc_org2

            mock_mcp_cache.get_cached_batch = AsyncMock(return_value=None)
            mock_mcp_cache.is_daily_quota_available = AsyncMock(return_value=True)
            mock_mcp_cache.cache_batch = AsyncMock(return_value=True)
            mock_mcp_cache.increment_daily_quota = AsyncMock(return_value=1)

            mock_routes_cache.get_cached_batch = AsyncMock(return_value=None)
            mock_routes_cache.is_daily_quota_available = AsyncMock(return_value=True)
            mock_routes_cache.cache_batch = AsyncMock(return_value=True)
            mock_routes_cache.increment_daily_quota = AsyncMock(return_value=1)

            headers_org2 = {"Authorization": "Bearer key_org2_secret"}

            # 1. MCP tools/call verify_emails with org2 key
            mcp_payload = {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "tools/call",
                "params": {
                    "name": "verify_emails",
                    "arguments": {"emails": ["client@org2.com"]},
                },
            }
            resp_mcp = client.post("/mcp/v1/", json=mcp_payload, headers=headers_org2)
            assert resp_mcp.status_code == 200
            mcp_data = resp_mcp.json()
            assert mcp_data["id"] == 100
            assert "Deliverable" in mcp_data["result"]["content"][0]["text"]
            assert mock_mcp_cache.increment_daily_quota.call_args[1]["account_id"] == "org2"

            # 2. REST POST /api/v1/verify with org2 key
            resp_rest = client.post(
                "/api/v1/verify",
                json={"emails": ["client@org2.com"]},
                headers=headers_org2,
            )
            assert resp_rest.status_code == 200
            assert resp_rest.json()["submitted"] == 1
            assert mock_routes_cache.increment_daily_quota.call_args[1]["account_id"] == "org2"

            # 3. REST GET /api/v1/credits with org2 key
            resp_credits = client.get("/api/v1/credits", headers=headers_org2)
            assert resp_credits.status_code == 200
            assert resp_credits.json()["free_credits"] == 25.0

    finally:
        current_settings.MCP_API_KEYS = original_keys
        current_settings.VERIFALIA_ADDITIONAL_ACCOUNTS = original_additional
