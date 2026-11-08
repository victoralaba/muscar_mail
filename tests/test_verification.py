import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
import httpx2
from pydantic import ValidationError
import pytest
from starlette.testclient import TestClient

from core.config import settings
from domains.verification.cache import VerificationCache
from domains.verification.routes import router as verification_router
from domains.verification.schemas import (
    BatchVerificationResponse,
    CreditBalanceResponse,
    EmailVerificationResult,
    EmailVerifyRequest,
)
from domains.verification.service import VerifaliaService
from shared.exceptions import (
    AuthenticationError,
    BatchLimitExceededError,
    InsufficientCreditsError,
    MuscarMailError,
    UpstreamProviderError,
    UpstreamTimeoutError,
)
from shared.redis import RedisClient

# Build test application mounting verification router
app = FastAPI()
app.include_router(verification_router)
client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer test_key_1"}


# -----------------------------------------------------------------------------
# 1. Schema Boundary & Invariant Tests (Task [8])
# -----------------------------------------------------------------------------

def test_schema_valid_batch():
    """Validates that a batch between 1 and 25 valid emails passes validation."""
    req = EmailVerifyRequest(emails=["  test@example.com ", "OTHER@test.com"])
    assert req.emails == ["test@example.com", "OTHER@test.com"]


def test_schema_empty_batch_rejected():
    """Validates that an empty list is rejected."""
    with pytest.raises(ValidationError):
        EmailVerifyRequest(emails=[])


def test_schema_exceeding_25_emails_rejected():
    """Validates Invariant INV-BATCH-1: Batch > 25 is rejected at schema boundary."""
    oversized = [f"user{i}@example.com" for i in range(26)]
    with pytest.raises(ValidationError) as exc_info:
        EmailVerifyRequest(emails=oversized)
    assert "exceeds maximum allowed limit of 25 emails" in str(exc_info.value)


@pytest.mark.anyio
async def test_service_exceeding_25_emails_raises_domain_error():
    """Validates Invariant INV-BATCH-1: Direct service call with > 25 emails raises BatchLimitExceededError."""
    service = VerifaliaService()
    oversized = [f"user{i}@example.com" for i in range(26)]
    with pytest.raises(BatchLimitExceededError) as exc_info:
        await service.verify_emails(oversized)
    assert exc_info.value.status_code == 422
    assert exc_info.value.details["received"] == 26
    assert exc_info.value.details["max_allowed"] == 25


def test_schema_whitespace_email_rejected():
    """Validates that empty/whitespace strings within a batch are rejected."""
    with pytest.raises(ValidationError):
        EmailVerifyRequest(emails=["valid@example.com", "   "])


# -----------------------------------------------------------------------------
# 2. Upstream Verifalia Adapter Tests (Task [9])
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_verify_emails_sync_200():
    """Validates Task [9]: Synchronous 200 OK response distillation."""
    mock_response_payload = {
        "overview": {
            "id": "job-12345",
            "status": "Completed",
            "noOfEntries": 2,
        },
        "entries": {
            "data": [
                {
                    "inputData": "valid@gmail.com",
                    "classification": "Deliverable",
                    "status": "Success",
                    "isDisposableEmailAddress": False,
                    "isRoleAccount": False,
                    "isFreeEmailAddress": True,
                },
                {
                    "inputData": "support@disposable.org",
                    "classification": "Undeliverable",
                    "status": "MailboxDoesNotExist",
                    "isDisposableEmailAddress": True,
                    "isRoleAccount": True,
                    "isFreeEmailAddress": False,
                },
            ]
        },
    }

    mock_client = AsyncMock(spec=httpx2.AsyncClient)
    mock_client.is_closed = False
    mock_response = MagicMock(spec=httpx2.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_payload
    mock_client.post.return_value = mock_response

    service = VerifaliaService(client=mock_client)
    res = await service.verify_emails(["valid@gmail.com", "support@disposable.org"])

    assert res.submitted == 2
    assert res.completed == 2
    assert res.cached is False
    assert len(res.results) == 2

    # Check 1st distilled result
    r1 = res.results[0]
    assert r1.email == "valid@gmail.com"
    assert r1.classification == "Deliverable"
    assert r1.status == "Success"
    assert r1.is_deliverable is True
    assert r1.is_disposable is False
    assert r1.is_role_account is False
    assert r1.is_free_email is True

    # Check 2nd distilled result
    r2 = res.results[1]
    assert r2.email == "support@disposable.org"
    assert r2.classification == "Undeliverable"
    assert r2.is_deliverable is False
    assert r2.is_disposable is True
    assert r2.is_role_account is True


@pytest.mark.anyio
async def test_verify_emails_polling_ladder_202():
    """Validates Task [9]: HTTP 202 Accepted triggers bounded fallback polling."""
    mock_202_payload = {
        "overview": {"id": "async-job-999", "status": "InProgress"},
    }
    mock_200_completed = {
        "overview": {"id": "async-job-999", "status": "Completed"},
        "entries": [
            {
                "inputData": "polled@example.com",
                "classification": "Deliverable",
                "status": "Success",
            }
        ],
    }

    mock_client = AsyncMock(spec=httpx2.AsyncClient)
    mock_client.is_closed = False

    # POST returns 202
    post_resp = MagicMock(spec=httpx2.Response)
    post_resp.status_code = 202
    post_resp.json.return_value = mock_202_payload
    mock_client.post.return_value = post_resp

    # GET poll returns 200 with Completed
    poll_resp = MagicMock(spec=httpx2.Response)
    poll_resp.status_code = 200
    poll_resp.json.return_value = mock_200_completed
    mock_client.get.return_value = poll_resp

    service = VerifaliaService(client=mock_client)
    res = await service.verify_emails(["polled@example.com"])

    assert res.completed == 1
    assert res.results[0].email == "polled@example.com"
    assert res.results[0].is_deliverable is True
    assert mock_client.get.called


@pytest.mark.anyio
async def test_verify_emails_exhausted_402():
    """Validates Task [9]: HTTP 402 maps to InsufficientCreditsError."""
    mock_client = AsyncMock(spec=httpx2.AsyncClient)
    mock_client.is_closed = False
    mock_resp = MagicMock(spec=httpx2.Response)
    mock_resp.status_code = 402
    mock_client.post.return_value = mock_resp

    service = VerifaliaService(client=mock_client)
    with pytest.raises(InsufficientCreditsError):
        await service.verify_emails(["test@example.com"])


@pytest.mark.anyio
async def test_verify_emails_auth_failure_401():
    """Validates: HTTP 401 from Verifalia maps to AuthenticationError."""
    mock_client = AsyncMock(spec=httpx2.AsyncClient)
    mock_client.is_closed = False
    mock_resp = MagicMock(spec=httpx2.Response)
    mock_resp.status_code = 401
    mock_client.post.return_value = mock_resp

    service = VerifaliaService(client=mock_client)
    with pytest.raises(AuthenticationError):
        await service.verify_emails(["test@example.com"])


@pytest.mark.anyio
async def test_get_credit_balance():
    """Validates: Credit balance retrieval maps correctly."""
    mock_client = AsyncMock(spec=httpx2.AsyncClient)
    mock_client.is_closed = False
    mock_resp = MagicMock(spec=httpx2.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "creditPacks": 10.5,
        "freeCredits": 25.0,
        "freeCreditsResetOn": "2026-11-09T00:00:00Z",
    }
    mock_client.get.return_value = mock_resp

    service = VerifaliaService(client=mock_client)
    bal = await service.get_credit_balance()

    assert bal.credit_packs == 10.5
    assert bal.free_credits == 25.0
    assert bal.free_credits_reset_on == "2026-11-09T00:00:00Z"


# -----------------------------------------------------------------------------
# 3. Redis Cache & Quota Tracking Tests (Task [7], [10])
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cached_batch_zero_credit_recovery():
    """Validates Task [10]: Canonical batch recovery serves results from cache at 0 cost."""
    mock_redis = AsyncMock(spec=RedisClient)

    # First simulate cache miss
    mock_redis.get.return_value = None
    cache = VerificationCache(client=mock_redis)

    emails = ["alice@example.com", "bob@example.com"]
    assert await cache.get_cached_batch(emails) is None

    # Simulate cache population
    cached_payload = json.dumps({
        "submitted": 2,
        "completed": 2,
        "results": [
            {
                "email": "alice@example.com",
                "classification": "Deliverable",
                "status": "Success",
                "is_deliverable": True,
                "is_disposable": False,
                "is_role_account": False,
                "is_free_email": False,
            },
            {
                "email": "bob@example.com",
                "classification": "Deliverable",
                "status": "Success",
                "is_deliverable": True,
                "is_disposable": False,
                "is_role_account": False,
                "is_free_email": False,
            },
        ],
    })
    mock_redis.get.return_value = cached_payload

    # Now verify cache hit returns same results with cached=True
    # Test order independence and case insensitivity
    recovered = await cache.get_cached_batch(["BOB@example.com", " alice@example.com "])
    assert recovered is not None
    assert recovered.cached is True
    assert recovered.completed == 2
    assert recovered.results[0].email == "alice@example.com"


@pytest.mark.anyio
async def test_redis_fail_open_resilience():
    """Validates Task [7] & Invariant INV-RESIL-1: Redis connection errors fail open."""
    # Create RedisClient that raises exceptions
    broken_redis = RedisClient(redis_url="redis://invalid-host:9999")
    cache = VerificationCache(client=broken_redis)

    # get should fail open and return None without raising
    assert await cache.get_cached_batch(["test@example.com"]) is None

    # quota check should fail open and allow execution
    assert await cache.is_daily_quota_available(10) is True


def test_dynamic_midnight_utc_ttl_calculation():
    """Validates dynamic TTL calculation against Verifalia reset timestamp."""
    # Valid ISO string in future
    ttl = VerificationCache.calculate_midnight_utc_ttl("2099-01-01T00:00:00Z")
    assert ttl == 86400

    # None falls back to host next midnight
    fallback_ttl = VerificationCache.calculate_midnight_utc_ttl(None)
    assert 0 < fallback_ttl <= 86400


# -----------------------------------------------------------------------------
# 4. REST Router Integration Tests (Task [11])
# -----------------------------------------------------------------------------

def test_rest_verify_unauthorized():
    """Validates: POST /api/v1/verify rejects missing API key with 401."""
    resp = client.post("/api/v1/verify", json={"emails": ["test@example.com"]})
    assert resp.status_code == 401


def test_rest_credits_unauthorized():
    """Validates: GET /api/v1/credits rejects missing API key with 401."""
    resp = client.get("/api/v1/credits")
    assert resp.status_code == 401


def test_rest_verify_oversized_batch_422():
    """Validates: POST /api/v1/verify rejects batch > 25 with 422."""
    oversized = [f"user{i}@example.com" for i in range(26)]
    resp = client.post("/api/v1/verify", json={"emails": oversized}, headers=AUTH_HEADERS)
    assert resp.status_code == 422
    assert "exceeds maximum allowed limit" in resp.text
