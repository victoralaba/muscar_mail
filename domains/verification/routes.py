from fastapi import APIRouter, Depends, status
from domains.verification.cache import VerificationCache, verification_cache
from domains.verification.schemas import (
    BatchVerificationResponse,
    CreditBalanceResponse,
    EmailVerifyRequest,
)
from domains.verification.service import (
    VerifaliaService,
    service_registry,
    verifalia_service,
)
from shared.exceptions import InsufficientCreditsError
from shared.security import AuthenticatedAccount, verify_mcp_api_key

router = APIRouter(prefix="/api/v1", tags=["verification"])


@router.post(
    "/verify",
    response_model=BatchVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify email batch",
    description="Synchronously validates up to 25 emails. Checks zero-credit cache first before invoking Verifalia API.",
)
async def verify_emails_endpoint(
    payload: EmailVerifyRequest,
    api_key: AuthenticatedAccount = Depends(verify_mcp_api_key),
    service: VerifaliaService = Depends(lambda: verifalia_service),
    cache: VerificationCache = Depends(lambda: verification_cache),
) -> BatchVerificationResponse:
    """Verifies a batch of 1 to 25 emails with zero-credit recovery and fail-open resilience."""
    emails = payload.emails
    account_id = getattr(api_key, "account_id", "default")

    # Resolve target service: default account uses injected service (honoring test mocks),
    # while secondary orgs resolve their dedicated service from the registry.
    target_service = (
        service
        if account_id == "default"
        else service_registry.get_service(
            account_id=account_id,
            username=getattr(api_key, "username", None),
            password=getattr(api_key, "password", None),
            base_url=getattr(api_key, "base_url", None),
        )
    )

    # 1. Zero-credit cache recovery check
    cached_result = await cache.get_cached_batch(emails)
    if cached_result is not None:
        return cached_result

    # 2. Daily quota boundary check (Invariant INV-QUOTA-ISOLATION)
    # Deduplicate canonical addresses under Safe deduplication so repeated emails cost 1 credit
    canonical_count = len(VerificationCache.get_canonical_emails(emails))
    quota_available = (
        await cache.is_daily_quota_available(canonical_count)
        if account_id == "default"
        else await cache.is_daily_quota_available(canonical_count, account_id=account_id)
    )
    if not quota_available:
        raise InsufficientCreditsError(
            message=f"Daily free-tier verification quota reached for account '{account_id}' (max 25 credits/day). Resets at 00:00:00 UTC."
        )

    # 3. Synchronous upstream verification call (Invariant INV-TIMEOUT-1)
    result = await target_service.verify_emails(emails=emails)

    # 4. Fail-open persistence to Redis cache (Invariant INV-CREDIT-1)
    await cache.cache_batch(emails=emails, response=result)

    # 5. Atomically track daily usage against midnight-UTC reset for this account
    if account_id == "default":
        await cache.increment_daily_quota(amount=canonical_count)
    else:
        await cache.increment_daily_quota(amount=canonical_count, account_id=account_id)

    return result


@router.get(
    "/credits",
    response_model=CreditBalanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Query credit balance",
    description="Retrieves current Verifalia credit balance and daily free credit reset schedule.",
)
async def get_credits_endpoint(
    api_key: AuthenticatedAccount = Depends(verify_mcp_api_key),
    service: VerifaliaService = Depends(lambda: verifalia_service),
) -> CreditBalanceResponse:
    """Returns available free and paid credit packs for authenticated account."""
    account_id = getattr(api_key, "account_id", "default")
    target_service = (
        service
        if account_id == "default"
        else service_registry.get_service(
            account_id=account_id,
            username=getattr(api_key, "username", None),
            password=getattr(api_key, "password", None),
            base_url=getattr(api_key, "base_url", None),
        )
    )
    return await target_service.get_credit_balance()
