from datetime import datetime, timezone
import hashlib
import json
from typing import List, Optional
from core.logging import get_logger
from domains.verification.schemas import (
    BatchVerificationResponse,
    EmailVerificationResult,
)
from shared.redis import RedisClient, redis_client

logger = get_logger("muscar_mail.cache")


class VerificationCache:
    """Manages batch result caching and midnight-UTC quota tracking.

    Enforces Invariants:
    - INV-CREDIT-1: Zero credit loss on client drop; retries served from cache at 0 cost.
    - INV-QUOTA-1: Free-tier daily quota limit guarded before upstream calls.
    - INV-RESIL-1: Fail-open resilience (Redis drops fail open without crashing).
    """

    def __init__(self, client: Optional[RedisClient] = None):
        self._redis = client or redis_client

    @staticmethod
    def get_canonical_emails(emails: List[str]) -> List[str]:
        """Canonicalizes email list: stripped, lowercased, deduplicated, and sorted."""
        return sorted({email.strip().lower() for email in emails if email and email.strip()})

    @classmethod
    def get_batch_hash(cls, emails: List[str]) -> str:
        """Computes deterministic SHA-256 hash of canonicalized email list."""
        canonical = cls.get_canonical_emails(emails)
        canonical_str = ",".join(canonical)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def get_batch_cache_key(cls, emails: List[str]) -> str:
        """Returns Redis key for cached batch result."""
        batch_hash = cls.get_batch_hash(emails)
        return f"cache:batch:{batch_hash}"

    @staticmethod
    def get_today_quota_key() -> str:
        """Returns Redis daily quota key formatted as quota:daily:YYYY-MM-DD in UTC."""
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"quota:daily:{today_utc}"

    @staticmethod
    def calculate_midnight_utc_ttl(reset_on: Optional[str] = None) -> int:
        """Computes seconds until next midnight 00:00:00 UTC.

        If Verifalia's 'freeCreditsResetOn' ISO 8601 string is provided, synchronizes exact TTL to it.
        """
        now = datetime.now(timezone.utc)

        if reset_on:
            try:
                # Handle ISO 8601 UTC timestamp
                reset_dt = datetime.fromisoformat(reset_on.replace("Z", "+00:00"))
                delta_seconds = int((reset_dt - now).total_seconds())
                if delta_seconds > 0:
                    return min(delta_seconds, 86400)
            except Exception as exc:
                logger.warning("Failed to parse freeCreditsResetOn timestamp. Falling back to host midnight.", error=str(exc))

        # Fallback: compute seconds until next 00:00:00 UTC
        next_midnight = datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=timezone.utc,
        )
        if next_midnight <= now:
            # Advance to tomorrow's midnight
            from datetime import timedelta
            next_midnight += timedelta(days=1)

        delta = int((next_midnight - now).total_seconds())
        return max(delta, 60)

    async def get_cached_batch(self, emails: List[str]) -> Optional[BatchVerificationResponse]:
        """Attempts to recover previously verified batch results from cache.

        Returns:
            BatchVerificationResponse with cached=True if found, None otherwise.
        """
        key = self.get_batch_cache_key(emails)
        raw_json = await self._redis.get(key)
        if not raw_json:
            return None

        try:
            data = json.loads(raw_json)
            results = [
                EmailVerificationResult.model_validate(item)
                for item in data.get("results", [])
            ]
            logger.info("Serving batch verification from cache (0 credits consumed).", key=key)
            return BatchVerificationResponse(
                submitted=len(emails),
                completed=data.get("completed", len(results)),
                cached=True,
                results=results,
            )
        except Exception as exc:
            logger.warning("Failed to deserialize cached batch JSON. Treating as cache miss.", key=key, error=str(exc))
            return None

    async def cache_batch(
        self,
        emails: List[str],
        response: BatchVerificationResponse,
        ttl_seconds: int = 86400,
    ) -> bool:
        """Persists completed verification results to Redis cache with 24h TTL."""
        key = self.get_batch_cache_key(emails)
        payload = response.model_dump_json()
        return await self._redis.set(key, payload, ex=ttl_seconds)

    async def is_daily_quota_available(self, requested_count: int) -> bool:
        """Checks if current daily usage plus requested batch count does not exceed 25."""
        quota_key = self.get_today_quota_key()
        raw_val = await self._redis.get(quota_key)
        if raw_val is None:
            # Key does not exist yet, quota is available
            return True

        try:
            current_count = int(raw_val)
            return (current_count + requested_count) <= 25
        except (ValueError, TypeError):
            return True

    async def increment_daily_quota(
        self, amount: int, reset_on: Optional[str] = None
    ) -> Optional[int]:
        """Atomically increments daily quota counter and sets dynamic midnight-UTC TTL."""
        quota_key = self.get_today_quota_key()
        new_val = await self._redis.incrby(quota_key, amount)
        if new_val is not None:
            ttl = self.calculate_midnight_utc_ttl(reset_on)
            # Only set TTL if key does not have one
            current_ttl = await self._redis.ttl(quota_key)
            if current_ttl < 0:
                await self._redis.expire(quota_key, ttl)
        return new_val


# Global singleton instance
verification_cache = VerificationCache()
