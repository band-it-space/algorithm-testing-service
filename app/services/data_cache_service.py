"""
Data Cache Service

Redis-based caching layer for stock OHLCV data to eliminate redundant API calls.
"""

import json
import logging
import pickle
from dataclasses import dataclass, asdict
from typing import Any

from redis import Redis

from app.utils.performance_profiler import CacheCounter, timed

logger = logging.getLogger(__name__)


@dataclass
class OHLCV:
    """OHLCV data structure for compatibility with existing code."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    # Pre-parsed date cache (set during pre-processing)
    _parsed_date: Any = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'OHLCV':
        return cls(
            date=data["date"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"]
        )


class DataCacheService:
    """
    Redis-based caching service for stock OHLCV data.
    
    Provides caching for:
    - Individual stock data by code and date range
    - SPY reference data (code 2800)
    - Cache hit/miss metrics
    
    Args:
        redis_conn: Redis connection instance
        default_ttl: Default time-to-live in seconds (default: 3600 = 1 hour)
        key_prefix: Prefix for all cache keys (default: "stock_cache")
    """
    
    SPY_CODE = "2800"
    
    def __init__(
        self, 
        redis_conn: Redis, 
        default_ttl: int = 3600,
        key_prefix: str = "stock_cache"
    ):
        self.redis = redis_conn
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self.cache_counter = CacheCounter("stock_data")
        self._spy_warmed = False
    
    def _generate_key(self, code: str, date_range: str = "full") -> str:
        """Generate a cache key for stock data."""
        return f"{self.key_prefix}:{code}:{date_range}"
    
    def _serialize(self, data: list[OHLCV]) -> bytes:
        """Serialize OHLCV list to bytes."""
        dict_list = [bar.to_dict() for bar in data]
        return pickle.dumps(dict_list)
    
    def _deserialize(self, data: bytes) -> list[OHLCV]:
        """Deserialize bytes to OHLCV list."""
        dict_list = pickle.loads(data)
        return [OHLCV.from_dict(d) for d in dict_list]
    
    @timed("cache_get_stock_data")
    def get_stock_data(
        self, 
        code: str, 
        start_date: str | None = None,
        end_date: str | None = None
    ) -> list[OHLCV] | None:
        """
        Get cached stock data for a given code.
        
        Args:
            code: Stock code
            start_date: Optional start date filter (YYYY-MM-DD)
            end_date: Optional end date filter (YYYY-MM-DD)
        
        Returns:
            List of OHLCV objects if cached, None otherwise
        """
        key = self._generate_key(code)
        
        try:
            cached_data = self.redis.get(key)
            
            if cached_data is None:
                self.cache_counter.miss()
                logger.debug(f"Cache MISS for stock {code}")
                return None
            
            self.cache_counter.hit()
            logger.debug(f"Cache HIT for stock {code}")
            
            data = self._deserialize(cached_data)
            
            # Apply date filtering if specified
            if start_date or end_date:
                data = self._filter_by_date(data, start_date, end_date)
            
            return data
            
        except Exception as e:
            logger.error(f"Cache read error for {code}: {e}")
            self.cache_counter.miss()
            return None
    
    def _filter_by_date(
        self, 
        data: list[OHLCV], 
        start_date: str | None, 
        end_date: str | None
    ) -> list[OHLCV]:
        """Filter OHLCV data by date range."""
        result = data
        if start_date:
            result = [bar for bar in result if bar.date >= start_date]
        if end_date:
            result = [bar for bar in result if bar.date <= end_date]
        return result
    
    @timed("cache_set_stock_data")
    def set_stock_data(
        self, 
        code: str, 
        data: list[OHLCV],
        ttl: int | None = None
    ) -> bool:
        """
        Cache stock data for a given code.
        
        Args:
            code: Stock code
            data: List of OHLCV objects
            ttl: Time-to-live in seconds (uses default if not specified)
        
        Returns:
            True if cached successfully, False otherwise
        """
        key = self._generate_key(code)
        ttl = ttl or self.default_ttl
        
        try:
            serialized = self._serialize(data)
            self.redis.setex(key, ttl, serialized)
            logger.debug(f"Cached {len(data)} bars for stock {code} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache write error for {code}: {e}")
            return False
    
    def get_spy_data(
        self, 
        start_date: str | None = None,
        end_date: str | None = None
    ) -> list[OHLCV] | None:
        """
        Get cached SPY (2800) reference data.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
        
        Returns:
            List of OHLCV objects if cached, None otherwise
        """
        return self.get_stock_data(self.SPY_CODE, start_date, end_date)
    
    def set_spy_data(self, data: list[OHLCV], ttl: int | None = None) -> bool:
        """Cache SPY reference data with extended TTL."""
        # SPY data gets longer TTL since it's frequently accessed
        spy_ttl = ttl or (self.default_ttl * 4)  # 4 hours default
        return self.set_stock_data(self.SPY_CODE, data, spy_ttl)
    
    @timed("cache_warm_spy")
    def warm_spy_cache(self, fetch_func) -> bool:
        """
        Pre-warm SPY cache by fetching data if not already cached.
        
        Args:
            fetch_func: Callable that returns SPY OHLCV data
        
        Returns:
            True if cache is warm, False on error
        """
        if self._spy_warmed:
            return True
        
        existing = self.get_spy_data()
        if existing is not None:
            logger.info(f"SPY cache already warm with {len(existing)} bars")
            self._spy_warmed = True
            return True
        
        try:
            logger.info("Warming SPY cache...")
            data = fetch_func()
            if data:
                self.set_spy_data(data)
                self._spy_warmed = True
                logger.info(f"SPY cache warmed with {len(data)} bars")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to warm SPY cache: {e}")
            return False
    
    def invalidate(self, code: str) -> bool:
        """
        Invalidate cached data for a stock.
        
        Args:
            code: Stock code to invalidate
        
        Returns:
            True if invalidated, False otherwise
        """
        key = self._generate_key(code)
        try:
            result = self.redis.delete(key)
            if result:
                logger.info(f"Invalidated cache for stock {code}")
            return bool(result)
        except Exception as e:
            logger.error(f"Cache invalidation error for {code}: {e}")
            return False
    
    def invalidate_all(self) -> int:
        """
        Invalidate all cached stock data.
        
        Returns:
            Number of keys invalidated
        """
        pattern = f"{self.key_prefix}:*"
        try:
            keys = list(self.redis.scan_iter(pattern))
            if keys:
                count = self.redis.delete(*keys)
                logger.info(f"Invalidated {count} cache keys")
                return count
            return 0
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return 0
    
    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache metrics
        """
        stats = self.cache_counter.get_stats()
        
        # Add Redis-specific stats
        try:
            pattern = f"{self.key_prefix}:*"
            cached_keys = list(self.redis.scan_iter(pattern))
            stats["cached_stocks"] = len(cached_keys)
            
            # Get memory usage for cache keys
            total_memory = 0
            for key in cached_keys[:100]:  # Sample first 100
                memory = self.redis.memory_usage(key) or 0
                total_memory += memory
            
            if len(cached_keys) > 100:
                # Estimate total memory
                avg_memory = total_memory / 100
                total_memory = int(avg_memory * len(cached_keys))
            
            stats["estimated_memory_bytes"] = total_memory
            stats["estimated_memory_mb"] = round(total_memory / (1024 * 1024), 2)
            
        except Exception as e:
            logger.debug(f"Could not get Redis stats: {e}")
        
        return stats


def create_cache_service_from_config() -> DataCacheService | None:
    """
    Factory function to create DataCacheService from application config.
    
    Returns:
        DataCacheService instance or None if Redis unavailable
    """
    try:
        from app.services.queue_service import QueueService
        redis_conn = QueueService.get_redis_client()
        return DataCacheService(redis_conn)
    except ImportError:
        logger.warning("Could not import queue_config, cache service unavailable")
        return None
    except Exception as e:
        logger.error(f"Failed to create cache service: {e}")
        return None
