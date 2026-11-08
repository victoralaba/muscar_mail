import json
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
import pytest
from starlette.testclient import TestClient

from domains.mcp.protocol import (
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
)
from domains.mcp.routes import router as mcp_router
from domains.verification.schemas import (
    BatchVerificationResponse,
    CreditBalanceResponse,
    EmailVerificationResult,
)
from shared.exceptions import register_exception_handlers

# Setup FastAPI test application mounting MCP router
app = FastAPI()
register_exception_handlers(app)
app.include_router(mcp_router)
client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer test_key_1"}


# -----------------------------------------------------------------------------
# 1. Transport & Authentication Guard Tests (Invariant INV-MCP-AUTH)
# -----------------------------------------------------------------------------

def test_mcp_unauthenticated_rejected():
    """Validates Invariant INV-MCP-AUTH: Unauthenticated requests return HTTP 401."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    # Without auth headers
    resp = client.post("/mcp/v1/", json=payload)
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers

    # Missing trailing slash route also protected
    resp_no_slash = client.post("/mcp/v1", json=payload)
    assert resp_no_slash.status_code == 401

    # Invalid API key
    resp_bad = client.post("/mcp/v1/", json=payload, headers={"Authorization": "Bearer invalid_key"})
    assert resp_bad.status_code == 401


# -----------------------------------------------------------------------------
# 2. JSON-RPC 2.0 Protocol Compliance Tests (Invariant INV-MCP-ERR)
# -----------------------------------------------------------------------------

def test_mcp_parse_error():
    """Validates: Malformed JSON syntax returns -32700 Parse error."""
    resp = client.post(
        "/mcp/v1/",
        content=b"{ invalid json syntax ",
        headers={"Content-Type": "application/json", **AUTH_HEADERS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] is None
    assert data["error"]["code"] == JSONRPCErrorCode.PARSE_ERROR
    assert "Parse error" in data["error"]["message"]


def test_mcp_invalid_request():
    """Validates: Non-conformant JSON-RPC request returns -32600 Invalid Request."""
    # Top-level is not an object or list
    resp1 = client.post("/mcp/v1/", content=b"12345", headers={"Content-Type": "application/json", **AUTH_HEADERS})
    assert resp1.status_code == 200
    assert resp1.json()["error"]["code"] == JSONRPCErrorCode.INVALID_REQUEST

    # Missing method
    resp2 = client.post("/mcp/v1/", json={"jsonrpc": "2.0", "id": 1}, headers=AUTH_HEADERS)
    assert resp2.status_code == 200
    assert resp2.json()["error"]["code"] == JSONRPCErrorCode.INVALID_REQUEST

    # Wrong jsonrpc version
    resp3 = client.post("/mcp/v1/", json={"jsonrpc": "1.0", "id": 1, "method": "ping"}, headers=AUTH_HEADERS)
    assert resp3.status_code == 200
    assert resp3.json()["error"]["code"] == JSONRPCErrorCode.INVALID_REQUEST


def test_mcp_method_not_found():
    """Validates: Unrecognized method returns -32601 Method not found."""
    resp = client.post(
        "/mcp/v1/",
        json={"jsonrpc": "2.0", "id": "m1", "method": "unknown_test_method"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "m1"
    assert data["error"]["code"] == JSONRPCErrorCode.METHOD_NOT_FOUND
    assert "unknown_test_method" in data["error"]["message"]


def test_mcp_batch_request_handling():
    """Validates: Batch JSON-RPC array request processes each item and returns response array."""
    batch_payload = [
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
    ]
    resp = client.post("/mcp/v1/", json=batch_payload, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[0]["result"] == {}
    assert data[1]["id"] == 2
    assert data[1]["result"] == {}


# -----------------------------------------------------------------------------
# 3. Lifecycle Handlers: initialize, notifications, ping
# -----------------------------------------------------------------------------

def test_mcp_initialize():
    """Validates: initialize returns protocolVersion '2024-11-05' and server capabilities."""
    req = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 100
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "muscar-mail"


def test_mcp_notifications_initialized():
    """Validates: notifications/initialized is acknowledged cleanly without error."""
    req = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["result"] == {}


def test_mcp_ping():
    """Validates: ping returns empty result."""
    req = {"jsonrpc": "2.0", "id": "test-ping", "method": "ping"}
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-ping"
    assert data["result"] == {}


# -----------------------------------------------------------------------------
# 4. Tool Registry & Discovery: tools/list
# -----------------------------------------------------------------------------

def test_mcp_tools_list():
    """Validates: tools/list exposes all 3 verification tools with JSON schemas."""
    req = {"jsonrpc": "2.0", "id": 200, "method": "tools/list"}
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    assert "verify_emails" in tool_names
    assert "get_cached_verification" in tool_names
    assert "get_credit_balance" in tool_names

    # Inspect verify_emails schema boundary
    verify_tool = next(t for t in tools if t["name"] == "verify_emails")
    assert verify_tool["inputSchema"]["type"] == "object"
    assert "emails" in verify_tool["inputSchema"]["required"]
    assert verify_tool["inputSchema"]["properties"]["emails"]["maxItems"] == 25


# -----------------------------------------------------------------------------
# 5. Tool Execution: tools/call
# -----------------------------------------------------------------------------

def test_mcp_tools_call_unknown_tool():
    """Validates: Calling an unregistered tool returns isError=True."""
    req = {
        "jsonrpc": "2.0",
        "id": 300,
        "method": "tools/call",
        "params": {"name": "unregistered_tool", "arguments": {}},
    }
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is True
    assert "Unknown tool" in result["content"][0]["text"]


def test_mcp_tools_call_verify_emails_oversized_batch():
    """Validates Invariant INV-MCP-BATCH: Batch > 25 is rejected before network dispatch."""
    oversized = [f"user{i}@example.com" for i in range(26)]
    req = {
        "jsonrpc": "2.0",
        "id": 301,
        "method": "tools/call",
        "params": {
            "name": "verify_emails",
            "arguments": {"emails": oversized},
        },
    }
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is True
    assert "exceeds maximum allowed limit of 25 emails" in result["content"][0]["text"]


def test_mcp_tools_call_verify_emails_empty_batch():
    """Validates: Empty emails array is rejected."""
    req = {
        "jsonrpc": "2.0",
        "id": 302,
        "method": "tools/call",
        "params": {
            "name": "verify_emails",
            "arguments": {"emails": []},
        },
    }
    resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is True
    assert "cannot be empty" in result["content"][0]["text"]


def test_mcp_tools_call_verify_emails_success():
    """Validates: Successful email verification distilled into compact MCP TextContent."""
    mock_batch = BatchVerificationResponse(
        submitted=1,
        completed=1,
        cached=False,
        results=[
            EmailVerificationResult(
                email="mcp_test@example.com",
                classification="Deliverable",
                status="Success",
                is_deliverable=True,
                is_disposable=False,
                is_role_account=False,
                is_free_email=False,
            )
        ],
    )

    with patch("domains.mcp.handlers.verification_cache") as mock_cache, \
         patch("domains.mcp.handlers.verifalia_service") as mock_service:
        mock_cache.get_cached_batch = AsyncMock(return_value=None)
        mock_cache.is_daily_quota_available = AsyncMock(return_value=True)
        mock_cache.cache_batch = AsyncMock(return_value=True)
        mock_cache.increment_daily_quota = AsyncMock(return_value=1)
        mock_service.verify_emails = AsyncMock(return_value=mock_batch)

        req = {
            "jsonrpc": "2.0",
            "id": 303,
            "method": "tools/call",
            "params": {
                "name": "verify_emails",
                "arguments": {"emails": ["mcp_test@example.com"]},
            },
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        parsed_text = json.loads(result["content"][0]["text"])
        assert parsed_text["submitted"] == 1
        assert parsed_text["results"][0]["email"] == "mcp_test@example.com"
        assert parsed_text["results"][0]["is_deliverable"] is True


def test_mcp_tools_call_verify_emails_cache_hit():
    """Validates Invariant INV-CREDIT-1: MCP tool recovers cached batch at zero credit cost."""
    cached_batch = BatchVerificationResponse(
        submitted=1,
        completed=1,
        cached=True,
        results=[
            EmailVerificationResult(
                email="cached_mcp@example.com",
                classification="Deliverable",
                status="Success",
                is_deliverable=True,
                is_disposable=False,
                is_role_account=False,
                is_free_email=False,
            )
        ],
    )

    with patch("domains.mcp.handlers.verification_cache") as mock_cache, \
         patch("domains.mcp.handlers.verifalia_service") as mock_service:
        mock_cache.get_cached_batch = AsyncMock(return_value=cached_batch)

        req = {
            "jsonrpc": "2.0",
            "id": 304,
            "method": "tools/call",
            "params": {
                "name": "verify_emails",
                "arguments": {"emails": ["cached_mcp@example.com"]},
            },
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        parsed_text = json.loads(result["content"][0]["text"])
        assert parsed_text["cached"] is True
        assert not mock_service.verify_emails.called


def test_mcp_tools_call_verify_emails_quota_depleted():
    """Validates Invariant INV-QUOTA-1: Depleted quota returns isError=True with reset message."""
    with patch("domains.mcp.handlers.verification_cache") as mock_cache:
        mock_cache.get_cached_batch = AsyncMock(return_value=None)
        mock_cache.is_daily_quota_available = AsyncMock(return_value=False)

        req = {
            "jsonrpc": "2.0",
            "id": 305,
            "method": "tools/call",
            "params": {
                "name": "verify_emails",
                "arguments": {"emails": ["quota_test@example.com"]},
            },
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "Daily verification quota reached" in result["content"][0]["text"]


def test_mcp_tools_call_get_cached_verification():
    """Validates: get_cached_verification returns cached batch or null."""
    with patch("domains.mcp.handlers.verification_cache") as mock_cache:
        # Cache miss returns null
        mock_cache.get_cached_batch = AsyncMock(return_value=None)
        req = {
            "jsonrpc": "2.0",
            "id": 306,
            "method": "tools/call",
            "params": {
                "name": "get_cached_verification",
                "arguments": {"emails": ["unknown@example.com"]},
            },
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        assert result["content"][0]["text"] == "null"


def test_mcp_tools_call_get_credit_balance():
    """Validates: get_credit_balance tool returns account balance in TextContent."""
    mock_bal = CreditBalanceResponse(
        credit_packs=5.0,
        free_credits=25.0,
        free_credits_reset_on="2026-11-09T00:00:00Z",
    )

    with patch("domains.mcp.handlers.verifalia_service") as mock_service:
        mock_service.get_credit_balance = AsyncMock(return_value=mock_bal)

        req = {
            "jsonrpc": "2.0",
            "id": 307,
            "method": "tools/call",
            "params": {"name": "get_credit_balance", "arguments": {}},
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        parsed_bal = json.loads(result["content"][0]["text"])
        assert parsed_bal["credit_packs"] == 5.0
        assert parsed_bal["free_credits"] == 25.0


def test_mcp_invalid_id_type():
    """Validates: Non-scalar JSON-RPC IDs (list, dict, float, bool) are sanitized to null without HTTP 500."""
    invalid_ids = [[1, 2], {"foo": "bar"}, 12.34, True]
    for bad_id in invalid_ids:
        req = {
            "jsonrpc": "2.0",
            "id": bad_id,
            "method": "ping",
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] is None
        assert data["error"]["code"] == JSONRPCErrorCode.INVALID_REQUEST


def test_mcp_null_arguments():
    """Validates: Tools called with arguments: null normalize gracefully to empty dict."""
    mock_bal = CreditBalanceResponse(
        credit_packs=0.0,
        free_credits=25.0,
        free_credits_reset_on="2026-11-09T00:00:00Z",
    )
    with patch("domains.mcp.handlers.verifalia_service") as mock_service:
        mock_service.get_credit_balance = AsyncMock(return_value=mock_bal)
        req = {
            "jsonrpc": "2.0",
            "id": 308,
            "method": "tools/call",
            "params": {"name": "get_credit_balance", "arguments": None},
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False


def test_mcp_cached_verification_boundaries():
    """Validates: get_cached_verification enforces 1..25 items and rejects non-strings / whitespace."""
    # Oversized batch (>25)
    req_oversized = {
        "jsonrpc": "2.0",
        "id": 309,
        "method": "tools/call",
        "params": {
            "name": "get_cached_verification",
            "arguments": {"emails": [f"user{i}@example.com" for i in range(26)]},
        },
    }
    resp = client.post("/mcp/v1/", json=req_oversized, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    res = resp.json()["result"]
    assert res["isError"] is True
    assert "exceeds maximum allowed limit of 25 emails" in res["content"][0]["text"]

    # Empty batch
    req_empty = {
        "jsonrpc": "2.0",
        "id": 310,
        "method": "tools/call",
        "params": {
            "name": "get_cached_verification",
            "arguments": {"emails": []},
        },
    }
    resp_empty = client.post("/mcp/v1/", json=req_empty, headers=AUTH_HEADERS)
    assert resp_empty.json()["result"]["isError"] is True

    # Non-string / whitespace element
    req_bad_elem = {
        "jsonrpc": "2.0",
        "id": 311,
        "method": "tools/call",
        "params": {
            "name": "get_cached_verification",
            "arguments": {"emails": ["   "]},
        },
    }
    resp_bad = client.post("/mcp/v1/", json=req_bad_elem, headers=AUTH_HEADERS)
    assert resp_bad.json()["result"]["isError"] is True
    assert "must be a non-empty string" in resp_bad.json()["result"]["content"][0]["text"]


def test_mcp_tools_call_verify_emails_upstream_auth_failure():
    """Validates: Upstream AuthenticationError returns clean isError=True message."""
    from shared.exceptions import AuthenticationError

    with patch("domains.mcp.handlers.verification_cache") as mock_cache, \
         patch("domains.mcp.handlers.verifalia_service") as mock_service:
        mock_cache.get_cached_batch = AsyncMock(return_value=None)
        mock_cache.is_daily_quota_available = AsyncMock(return_value=True)
        mock_service.verify_emails = AsyncMock(
            side_effect=AuthenticationError("Invalid Verifalia credentials.")
        )

        req = {
            "jsonrpc": "2.0",
            "id": 312,
            "method": "tools/call",
            "params": {
                "name": "verify_emails",
                "arguments": {"emails": ["auth_fail@example.com"]},
            },
        }
        resp = client.post("/mcp/v1/", json=req, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "Upstream authentication failed" in result["content"][0]["text"]


def test_mcp_get_mcp_handler_dependency_override():
    """Validates: get_mcp_handler dependency can be overridden cleanly via app.dependency_overrides."""
    from domains.mcp.routes import get_mcp_handler
    from domains.mcp.handlers import MCPHandler

    mock_h = MCPHandler()
    app.dependency_overrides[get_mcp_handler] = lambda: mock_h
    try:
        resp = client.post(
            "/mcp/v1/",
            json={"jsonrpc": "2.0", "id": "override_test", "method": "ping"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == "override_test"
    finally:
        app.dependency_overrides.pop(get_mcp_handler, None)
