"""Query caching layer with Redis support and in-memory fallback.

Provides a multi-tier cache for SQL query results with:
- L1: In-memory cache (fast, per-instance)
- L2: Redis cache (distributed, optional)
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache

from retail_insights.core.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

    from retail_insights.core.config import Settings

logger = get_logger(__name__)

DEFAULT_TTL_SECONDS = 300
DEFAULT_L1_TTL_SECONDS = 60
DEFAULT_L1_MAX_SIZE = 100
CACHE_KEY_PREFIX = "ri:qc"


class CacheConfig:
    """Cache configuration from Settings or defaults."""

    def __init__(self, settings: Settings | None = None) -> None:
        if settings:
            self.enabled = settings.CACHE_ENABLED
            self.redis_url = settings.REDIS_URL or ""
            self.ttl_seconds = settings.CACHE_TTL_SECONDS
            self.l1_ttl_seconds = settings.CACHE_L1_TTL_SECONDS
            self.l1_max_size = settings.CACHE_L1_MAX_SIZE
        else:
            self.enabled = True
            self.redis_url = ""
            self.ttl_seconds = DEFAULT_TTL_SECONDS
            self.l1_ttl_seconds = DEFAULT_L1_TTL_SECONDS
            self.l1_max_size = DEFAULT_L1_MAX_SIZE
        self.key_prefix = CACHE_KEY_PREFIX


def generate_cache_key(sql: str, params: dict[str, Any] | None = None) -> str:
    """Generate a deterministic cache key from SQL and parameters.

    Args:
        sql: The SQL query string.
        params: Optional query parameters.

    Returns:
        A hashed cache key string.
    """
    normalized_sql = " ".join(sql.lower().split())

    key_parts = [normalized_sql]
    if params:
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        key_parts.append(sorted_params)

    key_data = "|".join(key_parts)
    hash_value = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    return hash_value


class CacheEntry:
    """Represents a cached query result."""

    def __init__(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        row_count: int,
        sql: str,
        cached_at: datetime | None = None,
    ) -> None:
        self.data = data
        self.columns = columns
        self.row_count = row_count
        self.sql = sql
        self.cached_at = cached_at or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "columns": self.columns,
            "row_count": self.row_count,
            "sql": self.sql,
            "cached_at": self.cached_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CacheEntry:
        return cls(
            data=d["data"],
            columns=d["columns"],
            row_count=d["row_count"],
            sql=d["sql"],
            cached_at=datetime.fromisoformat(d["cached_at"]),
        )


class QueryCache:
    """Multi-tier query cache with L1 (memory) and L2 (Redis) layers."""

    def __init__(self, config: CacheConfig | None = None) -> None:
        self.config = config or CacheConfig()
        self._l1_cache: TTLCache[str, CacheEntry] = TTLCache(
            maxsize=self.config.l1_max_size,
            ttl=self.config.l1_ttl_seconds,
        )
        self._redis: AsyncRedis | None = None
        self._redis_available = False
        self._stats = CacheStats()

    async def connect_redis(self) -> bool:
        """Initialize Redis connection if configured.

        Returns:
            True if Redis connected successfully.
        """
        if not self.config.redis_url:
            logger.debug("cache_redis_disabled", reason="no_url")
            return False

        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self.config.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            await self._redis.ping()  # type: ignore[misc]
            self._redis_available = True
            logger.info("cache_redis_connected", url=self.config.redis_url[:20] + "...")
            return True
        except ImportError:
            logger.warning("cache_redis_unavailable", reason="redis_not_installed")
            return False
        except Exception as e:
            logger.warning("cache_redis_connection_failed", error=str(e))
            self._redis_available = False
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            self._redis_available = False

    def _make_key(self, key_hash: str) -> str:
        return f"{self.config.key_prefix}:{key_hash}"

    async def get(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> CacheEntry | None:
        """Get cached query result.

        Args:
            sql: The SQL query.
            params: Query parameters.

        Returns:
            CacheEntry if found, None otherwise.
        """
        from retail_insights.core.metrics import record_cache_access

        if not self.config.enabled:
            return None

        key_hash = generate_cache_key(sql, params)

        entry = self._l1_cache.get(key_hash)
        if entry is not None:
            self._stats.l1_hits += 1
            record_cache_access("l1", hit=True)
            logger.debug("cache_hit", layer="l1", key=key_hash[:8])
            return entry

        self._stats.l1_misses += 1
        record_cache_access("l1", hit=False)

        if self._redis_available and self._redis:
            try:
                redis_key = self._make_key(key_hash)
                cached_json = await self._redis.get(redis_key)
                if cached_json:
                    entry = CacheEntry.from_dict(json.loads(cached_json))
                    self._l1_cache[key_hash] = entry
                    self._stats.l2_hits += 1
                    record_cache_access("l2", hit=True)
                    logger.debug("cache_hit", layer="l2", key=key_hash[:8])
                    return entry
                self._stats.l2_misses += 1
                record_cache_access("l2", hit=False)
            except Exception as e:
                logger.warning("cache_redis_get_error", error=str(e))

        return None

    async def set(
        self,
        sql: str,
        entry: CacheEntry,
        params: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Cache a query result.

        Args:
            sql: The SQL query.
            entry: The cache entry to store.
            params: Query parameters.
            ttl: Optional TTL override in seconds.
        """
        if not self.config.enabled:
            return

        key_hash = generate_cache_key(sql, params)
        ttl = ttl or self.config.ttl_seconds

        self._l1_cache[key_hash] = entry

        if self._redis_available and self._redis:
            try:
                redis_key = self._make_key(key_hash)
                await self._redis.setex(
                    redis_key,
                    ttl,
                    json.dumps(entry.to_dict()),
                )
                logger.debug("cache_set", key=key_hash[:8], ttl=ttl)
            except Exception as e:
                logger.warning("cache_redis_set_error", error=str(e))

    async def invalidate(self, pattern: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            pattern: Optional pattern to match (glob-style).
                    If None, clears all entries.

        Returns:
            Number of entries invalidated.
        """
        count = 0

        l1_count = len(self._l1_cache)
        self._l1_cache.clear()
        count += l1_count

        if self._redis_available and self._redis:
            try:
                if pattern:
                    redis_pattern = f"{self.config.key_prefix}:{pattern}"
                else:
                    redis_pattern = f"{self.config.key_prefix}:*"

                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor=cursor,
                        match=redis_pattern,
                        count=100,
                    )
                    if keys:
                        await self._redis.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break

                logger.info("cache_invalidated", pattern=pattern, count=count)
            except Exception as e:
                logger.warning("cache_redis_invalidate_error", error=str(e))

        return count

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats = CacheStats()


class CacheStats:
    """Cache hit/miss statistics."""

    def __init__(self) -> None:
        self.l1_hits = 0
        self.l1_misses = 0
        self.l2_hits = 0
        self.l2_misses = 0

    @property
    def total_hits(self) -> int:
        return self.l1_hits + self.l2_hits

    @property
    def total_misses(self) -> int:
        return self.l1_misses + self.l2_misses

    @property
    def hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "l1_hits": self.l1_hits,
            "l1_misses": self.l1_misses,
            "l2_hits": self.l2_hits,
            "l2_misses": self.l2_misses,
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_rate": round(self.hit_rate, 4),
        }


_cache_instance: QueryCache | None = None


def get_query_cache(settings: Settings | None = None) -> QueryCache:
    """Get the global QueryCache singleton.

    Args:
        settings: Optional Settings instance. Uses get_settings() if not provided.

    Returns:
        QueryCache singleton instance.
    """
    global _cache_instance
    if _cache_instance is None:
        if settings is None:
            from retail_insights.core.config import get_settings

            settings = get_settings()
        _cache_instance = QueryCache(CacheConfig(settings))
    return _cache_instance


def reset_query_cache() -> None:
    """Reset the global QueryCache singleton (for testing)."""
    global _cache_instance
    _cache_instance = None


@asynccontextmanager
async def cache_context(settings: Settings | None = None):
    """Context manager for cache lifecycle in FastAPI lifespan.

    Args:
        settings: Optional Settings instance.

    Yields:
        QueryCache instance.
    """
    cache = get_query_cache(settings)
    await cache.connect_redis()
    try:
        yield cache
    finally:
        await cache.close()
