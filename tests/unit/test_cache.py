"""Tests for query caching module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from retail_insights.engine.cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    QueryCache,
    generate_cache_key,
    get_query_cache,
    reset_query_cache,
)


class TestGenerateCacheKey:
    """Tests for cache key generation."""

    def test_generates_consistent_key(self) -> None:
        """Same SQL should generate same key."""
        sql = "SELECT * FROM sales LIMIT 10"
        key1 = generate_cache_key(sql)
        key2 = generate_cache_key(sql)
        assert key1 == key2

    def test_different_sql_different_key(self) -> None:
        """Different SQL should generate different keys."""
        key1 = generate_cache_key("SELECT * FROM sales")
        key2 = generate_cache_key("SELECT * FROM products")
        assert key1 != key2

    def test_normalizes_whitespace(self) -> None:
        """Whitespace differences should not affect key."""
        key1 = generate_cache_key("SELECT * FROM sales")
        key2 = generate_cache_key("SELECT  *  FROM  sales")
        assert key1 == key2

    def test_case_insensitive(self) -> None:
        """SQL case should not affect key."""
        key1 = generate_cache_key("SELECT * FROM sales")
        key2 = generate_cache_key("select * from SALES")
        assert key1 == key2

    def test_includes_params_in_key(self) -> None:
        """Different params should generate different keys."""
        sql = "SELECT * FROM sales WHERE id = ?"
        key1 = generate_cache_key(sql, {"id": 1})
        key2 = generate_cache_key(sql, {"id": 2})
        assert key1 != key2

    def test_same_params_same_key(self) -> None:
        """Same params should generate same key."""
        sql = "SELECT * FROM sales WHERE id = ?"
        key1 = generate_cache_key(sql, {"id": 1})
        key2 = generate_cache_key(sql, {"id": 1})
        assert key1 == key2

    def test_key_is_16_chars(self) -> None:
        """Key should be truncated SHA256."""
        key = generate_cache_key("SELECT 1")
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_create_entry(self) -> None:
        """Should create cache entry with data."""
        entry = CacheEntry(
            data=[{"id": 1, "name": "test"}],
            columns=["id", "name"],
            row_count=1,
            sql="SELECT * FROM test",
        )
        assert entry.row_count == 1
        assert entry.columns == ["id", "name"]
        assert entry.cached_at is not None

    def test_to_dict(self) -> None:
        """Should serialize to dictionary."""
        entry = CacheEntry(
            data=[{"id": 1}],
            columns=["id"],
            row_count=1,
            sql="SELECT 1",
        )
        d = entry.to_dict()
        assert "data" in d
        assert "columns" in d
        assert "row_count" in d
        assert "sql" in d
        assert "cached_at" in d

    def test_from_dict(self) -> None:
        """Should deserialize from dictionary."""
        d = {
            "data": [{"id": 1}],
            "columns": ["id"],
            "row_count": 1,
            "sql": "SELECT 1",
            "cached_at": "2026-01-01T00:00:00",
        }
        entry = CacheEntry.from_dict(d)
        assert entry.row_count == 1
        assert entry.sql == "SELECT 1"

    def test_roundtrip(self) -> None:
        """Should serialize and deserialize correctly."""
        original = CacheEntry(
            data=[{"id": 1, "value": "test"}],
            columns=["id", "value"],
            row_count=1,
            sql="SELECT id, value FROM test",
        )
        restored = CacheEntry.from_dict(original.to_dict())
        assert restored.data == original.data
        assert restored.columns == original.columns
        assert restored.row_count == original.row_count
        assert restored.sql == original.sql


class TestCacheStats:
    """Tests for CacheStats tracking."""

    def test_initial_stats(self) -> None:
        """Stats should start at zero."""
        stats = CacheStats()
        assert stats.l1_hits == 0
        assert stats.l1_misses == 0
        assert stats.l2_hits == 0
        assert stats.l2_misses == 0

    def test_total_hits(self) -> None:
        """Should sum L1 and L2 hits."""
        stats = CacheStats()
        stats.l1_hits = 5
        stats.l2_hits = 3
        assert stats.total_hits == 8

    def test_hit_rate_zero_requests(self) -> None:
        """Hit rate should be 0 with no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self) -> None:
        """Should calculate hit rate correctly."""
        stats = CacheStats()
        stats.l1_hits = 7
        stats.l1_misses = 3
        assert stats.hit_rate == 0.7

    def test_to_dict(self) -> None:
        """Should export stats as dictionary."""
        stats = CacheStats()
        stats.l1_hits = 10
        d = stats.to_dict()
        assert d["l1_hits"] == 10
        assert "hit_rate" in d


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_default_config(self) -> None:
        """Should use default values without settings."""
        config = CacheConfig()
        assert config.enabled is True
        assert config.ttl_seconds == 300
        assert config.l1_ttl_seconds == 60
        assert config.l1_max_size == 100

    def test_config_from_settings(self) -> None:
        """Should load from Settings instance."""
        settings = MagicMock()
        settings.CACHE_ENABLED = True
        settings.REDIS_URL = "redis://localhost:6379"
        settings.CACHE_TTL_SECONDS = 600
        settings.CACHE_L1_TTL_SECONDS = 120
        settings.CACHE_L1_MAX_SIZE = 200

        config = CacheConfig(settings)
        assert config.enabled is True
        assert config.redis_url == "redis://localhost:6379"
        assert config.ttl_seconds == 600


class TestQueryCache:
    """Tests for QueryCache operations."""

    @pytest.fixture
    def cache(self) -> QueryCache:
        """Create cache with default config."""
        config = CacheConfig()
        config.enabled = True
        return QueryCache(config)

    @pytest.fixture
    def sample_entry(self) -> CacheEntry:
        """Create sample cache entry."""
        return CacheEntry(
            data=[{"id": 1, "name": "Product A"}],
            columns=["id", "name"],
            row_count=1,
            sql="SELECT * FROM products LIMIT 1",
        )

    @pytest.mark.asyncio
    async def test_l1_cache_set_get(self, cache: QueryCache, sample_entry: CacheEntry) -> None:
        """Should store and retrieve from L1 cache."""
        sql = "SELECT * FROM products"
        await cache.set(sql, sample_entry)

        result = await cache.get(sql)
        assert result is not None
        assert result.row_count == 1
        assert cache.get_stats()["l1_hits"] == 1

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache: QueryCache) -> None:
        """Should return None on cache miss."""
        result = await cache.get("SELECT * FROM nonexistent")
        assert result is None
        assert cache.get_stats()["l1_misses"] == 1

    @pytest.mark.asyncio
    async def test_cache_disabled(self, sample_entry: CacheEntry) -> None:
        """Should bypass cache when disabled."""
        config = CacheConfig()
        config.enabled = False
        cache = QueryCache(config)

        sql = "SELECT 1"
        await cache.set(sql, sample_entry)
        result = await cache.get(sql)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(
        self, cache: QueryCache, sample_entry: CacheEntry
    ) -> None:
        """Should clear all entries on invalidate."""
        await cache.set("SELECT 1", sample_entry)
        await cache.set("SELECT 2", sample_entry)

        await cache.invalidate()

        result = await cache.get("SELECT 1")
        assert result is None

    @pytest.mark.asyncio
    async def test_stats_reset(self, cache: QueryCache, sample_entry: CacheEntry) -> None:
        """Should reset statistics."""
        await cache.set("SELECT 1", sample_entry)
        await cache.get("SELECT 1")

        cache.reset_stats()
        stats = cache.get_stats()
        assert stats["total_hits"] == 0

    @pytest.mark.asyncio
    async def test_connect_redis_no_url(self, cache: QueryCache) -> None:
        """Should return False when no Redis URL configured."""
        result = await cache.connect_redis()
        assert result is False

    @pytest.mark.asyncio
    async def test_close_without_redis(self, cache: QueryCache) -> None:
        """Should handle close gracefully without Redis."""
        await cache.close()
        assert cache._redis is None


class TestQueryCacheSingleton:
    """Tests for cache singleton management."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_query_cache()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_query_cache()

    def test_get_query_cache_returns_same_instance(self) -> None:
        """Should return same instance on multiple calls."""
        settings = MagicMock()
        settings.CACHE_ENABLED = True
        settings.REDIS_URL = None
        settings.CACHE_TTL_SECONDS = 300
        settings.CACHE_L1_TTL_SECONDS = 60
        settings.CACHE_L1_MAX_SIZE = 100

        cache1 = get_query_cache(settings)
        cache2 = get_query_cache(settings)
        assert cache1 is cache2

    def test_reset_creates_new_instance(self) -> None:
        """Should create new instance after reset."""
        settings = MagicMock()
        settings.CACHE_ENABLED = True
        settings.REDIS_URL = None
        settings.CACHE_TTL_SECONDS = 300
        settings.CACHE_L1_TTL_SECONDS = 60
        settings.CACHE_L1_MAX_SIZE = 100

        cache1 = get_query_cache(settings)
        reset_query_cache()
        cache2 = get_query_cache(settings)
        assert cache1 is not cache2
