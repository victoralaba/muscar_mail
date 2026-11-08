import asyncio
from typing import Any, Dict, List, Optional
import httpx2
from core.config import get_settings
from core.logging import get_logger
from domains.verification.schemas import (
    BatchVerificationResponse,
    CreditBalanceResponse,
    EmailVerificationResult,
)
from shared.exceptions import (
    AuthenticationError,
    BatchLimitExceededError,
    InsufficientCreditsError,
    MuscarMailError,
    UpstreamProviderError,
    UpstreamTimeoutError,
)

logger = get_logger("muscar_mail.verifalia")


class VerifaliaService:
    """Upstream Verifalia v2.4 API service adapter using httpx2 HTTP/2 client.

    Enforces Invariants:
    - INV-BATCH-1: Batch size <= 25 emails.
    - INV-TIMEOUT-1: Bounded execution (waitTime=30000, 3-cycle max polling ladder).
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        base_url: Optional[str] = None,
        client: Optional[httpx2.AsyncClient] = None,
    ):
        settings = get_settings()
        self._username = username or settings.VERIFALIA_USERNAME
        self._password = password or settings.VERIFALIA_PASSWORD
        self._base_url = (base_url or settings.VERIFALIA_BASE_URL).rstrip("/")
        self._client = client

    async def get_client(self) -> httpx2.AsyncClient:
        """Returns the shared httpx2 HTTP/2 client with Basic Auth and 45s timeout."""
        if self._client is None or self._client.is_closed:
            self._client = httpx2.AsyncClient(
                http2=True,
                auth=(self._username, self._password),
                timeout=httpx2.Timeout(45.0, connect=10.0),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "muscar-mail/1.0.0 (FastAPI/MCP)",
                },
            )
        return self._client

    async def verify_emails(
        self, emails: List[str], wait_time_ms: int = 30000
    ) -> BatchVerificationResponse:
        """Verifies a batch of 1 to 25 emails using Verifalia v2.4 API with synchronous wait.

        Leverages 'waitTime' parameter to resolve small batches synchronously in a single HTTP request.
        """
        if not emails:
            raise ValueError("Email list cannot be empty.")

        if len(emails) > 25:
            raise BatchLimitExceededError(received_count=len(emails), max_allowed=25)

        client = await self.get_client()

        payload = {
            "entries": [{"inputData": email} for email in emails],
            "quality": "Standard",
            "deduplication": "Safe",
        }

        url = f"{self._base_url}/email-validations?waitTime={wait_time_ms}"

        try:
            response = await client.post(url, json=payload)
        except httpx2.TimeoutException as exc:
            logger.warning("Verifalia request timed out on initial POST.", error=str(exc))
            raise UpstreamTimeoutError("Initial email verification request timed out.") from exc
        except httpx2.RequestError as exc:
            logger.error("Verifalia network error on initial POST.", error=str(exc))
            raise UpstreamProviderError(f"Network error connecting to verification provider: {exc}") from exc

        # Handle HTTP status codes
        if response.status_code == 200:
            data = response.json()
            return self._distill_batch_response(submitted_count=len(emails), raw_data=data)

        elif response.status_code == 202:
            data = response.json()
            job_id = data.get("overview", {}).get("id") or data.get("id")
            if not job_id:
                raise UpstreamProviderError("Verifalia returned 202 Accepted but omitted job ID.")

            logger.info("Job enqueued asynchronously, entering bounded polling ladder.", job_id=job_id)
            return await self._poll_job_until_complete(job_id=job_id, submitted_count=len(emails))

        elif response.status_code == 401:
            logger.error("Verifalia authentication failed. Check credentials.")
            raise AuthenticationError("Invalid Verifalia provider credentials.")

        elif response.status_code == 402:
            logger.warning("Verifalia daily/paid credit quota exhausted (HTTP 402).")
            raise InsufficientCreditsError("Daily verification credit quota exhausted (HTTP 402).")

        elif response.status_code == 429:
            logger.warning("Verifalia rate limit exceeded (HTTP 429).")
            raise MuscarMailError("Verifalia rate limit exceeded (HTTP 429).", status_code=503)

        else:
            logger.error(
                "Verifalia returned unexpected status code.",
                status_code=response.status_code,
                response_body=response.text[:200],
            )
            raise UpstreamProviderError(
                f"Verifalia API returned unexpected error status: {response.status_code}"
            )

    async def _poll_job_until_complete(
        self, job_id: str, submitted_count: int, max_attempts: int = 3, poll_wait_ms: int = 5000
    ) -> BatchVerificationResponse:
        """Bounded fallback polling ladder on HTTP 202 Accepted. Maximum 3 attempts."""
        client = await self.get_client()
        poll_url = f"{self._base_url}/email-validations/{job_id}?waitTime={poll_wait_ms}"

        for attempt in range(1, max_attempts + 1):
            logger.debug("Polling Verifalia job status.", job_id=job_id, attempt=attempt, max_attempts=max_attempts)
            await asyncio.sleep(1.0)

            try:
                poll_resp = await client.get(poll_url)
            except httpx2.TimeoutException:
                logger.warning("Poll attempt timed out.", job_id=job_id, attempt=attempt)
                continue
            except httpx2.RequestError as exc:
                logger.warning("Poll attempt connection error.", job_id=job_id, attempt=attempt, error=str(exc))
                continue

            if poll_resp.status_code == 200:
                raw_data = poll_resp.json()
                overview_status = raw_data.get("overview", {}).get("status")
                if overview_status == "Completed":
                    logger.info("Verifalia job completed during polling ladder.", job_id=job_id, attempt=attempt)
                    return self._distill_batch_response(submitted_count=submitted_count, raw_data=raw_data)

            elif poll_resp.status_code == 402:
                raise InsufficientCreditsError("Verifalia credit quota exhausted during job execution.")

        logger.warning("Polling ladder exhausted without job completion.", job_id=job_id, attempts=max_attempts)
        raise UpstreamTimeoutError(
            f"Email verification job {job_id} did not complete within the bounded polling window."
        )

    def _distill_batch_response(self, submitted_count: int, raw_data: Dict[str, Any]) -> BatchVerificationResponse:
        """Distills raw Verifalia JSON into compact, token-efficient 7-field summary records."""
        entries_container = raw_data.get("entries", [])
        if isinstance(entries_container, dict) and "data" in entries_container:
            raw_entries = entries_container["data"]
        elif isinstance(entries_container, list):
            raw_entries = entries_container
        else:
            raw_entries = []

        distilled_results: List[EmailVerificationResult] = []

        for entry in raw_entries:
            email = entry.get("inputData") or entry.get("emailAddress") or ""
            classification = entry.get("classification", "Unknown")
            status = entry.get("status", "Unknown")

            is_deliverable = classification == "Deliverable"
            is_disposable = bool(
                entry.get("isDisposableEmailAddress") or entry.get("isDisposable", False)
            )
            is_role_account = bool(entry.get("isRoleAccount", False))
            is_free_email = bool(
                entry.get("isFreeEmailAddress") or entry.get("isFreeEmail", False)
            )

            distilled_results.append(
                EmailVerificationResult(
                    email=email,
                    classification=classification,
                    status=status,
                    is_deliverable=is_deliverable,
                    is_disposable=is_disposable,
                    is_role_account=is_role_account,
                    is_free_email=is_free_email,
                )
            )

        return BatchVerificationResponse(
            submitted=submitted_count,
            completed=len(distilled_results),
            cached=False,
            results=distilled_results,
        )

    async def get_credit_balance(self) -> CreditBalanceResponse:
        """Retrieves current Verifalia credit balance and free credit reset schedule."""
        client = await self.get_client()
        url = f"{self._base_url}/credits/balance"

        try:
            response = await client.get(url)
        except httpx2.TimeoutException as exc:
            raise UpstreamTimeoutError("Timeout querying credit balance.") from exc
        except httpx2.RequestError as exc:
            raise UpstreamProviderError(f"Network error querying credit balance: {exc}") from exc

        if response.status_code == 200:
            data = response.json()
            return CreditBalanceResponse(
                credit_packs=float(data.get("creditPacks", 0.0)),
                free_credits=float(data.get("freeCredits", 0.0)),
                free_credits_reset_on=data.get("freeCreditsResetOn"),
            )
        elif response.status_code == 401:
            raise AuthenticationError("Invalid Verifalia provider credentials.")
        else:
            raise UpstreamProviderError(f"Verifalia credits check failed: HTTP {response.status_code}")

    async def aclose(self) -> None:
        """Closes the underlying httpx2 client connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()


# Global singleton instance
verifalia_service = VerifaliaService()
