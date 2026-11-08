from typing import Optional
import redis.asyncio as aioredis
from core.config import get_settings
from core.logging import get_logger

logger = get_logger("muscar_mail.redis")


class RedisClient:
    """Async Redis client wrapper with strict fail-open resilience.

    Enforces Invariant INV-RESIL-1: Redis unavailability, timeouts, or network partitions
    will never crash the application or prevent direct email verification.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    def _get_url(self) -> str:
        if self._redis_url:
            return self._redis_url
        settings = get_settings()
        return settings.REDIS_URL

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Lazily initializes and returns the async Redis client connection pool."""
        if self._client is None:
            try:
                url = self._get_url()
                self._client = aioredis.from_url(
                    url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=3.0,
                    socket_timeout=3.0,
                    max_connections=20,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to create Redis connection pool. Running in degraded fail-open mode.",
                    error=str(exc),
                )
                self._client = None
        return self._client

    async def ping(self) -> bool:
        """Pings Redis to verify connectivity. Returns False on failure (fail-open)."""
        try:
            client = await self.get_client()
            if client is None:
                return False
            return bool(await client.ping())
        except Exception as exc:
            logger.warning("Redis ping failed.", error=str(exc))
            return False

    async def get(self, key: str) -> Optional[str]:
        """Gets value by key. Returns None on cache miss or connection error."""
        try:
            client = await self.get_client()
            if client is None:
                return None
            return await client.get(key)
        except Exception as exc:
            logger.warning("Redis GET failed, falling open.", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Sets key-value pair with optional TTL in seconds. Returns False on error."""
        try:
            client = await self.get_client()
            if client is None:
                return False
            await client.set(key, value, ex=ex)
            return True
        except Exception as exc:
            logger.warning("Redis SET failed, falling open.", key=key, error=str(exc))
            return False

    async def incrby(self, key: str, amount: int = 1) -> Optional[int]:
        """Atomically increments a key counter. Returns None on error."""
        try:
            client = await self.get_client()
            if client is None:
                return None
            return await client.incrby(key, amount)
        except Exception as exc:
            logger.warning("Redis INCRBY failed, falling open.", key=key, amount=amount, error=str(exc))
            return None

    async def expire(self, key: str, time: int) -> bool:
        """Sets TTL in seconds on a key. Returns False on error."""
        try:
            client = await self.get_client()
            if client is None:
                return False
            return bool(await client.expire(key, time))
        except Exception as exc:
            logger.warning("Redis EXPIRE failed, falling open.", key=key, ttl=time, error=str(exc))
            return False

    async def ttl(self, key: str) -> int:
        """Returns remaining TTL of a key in seconds (-2 if not exists, -1 if no TTL, -3 on error)."""
        try:
            client = await self.get_client()
            if client is None:
                return -3
            return await client.ttl(key)
        except Exception as exc:
            logger.warning("Redis TTL failed, falling open.", key=key, error=str(exc))
            return -3

    async def close(self) -> None:
        """Closes the Redis connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning("Error closing Redis client.", error=str(exc))
            finally:
                self._client = None


# Global singleton instance
redis_client = RedisClient()
