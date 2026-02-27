"""
Performance Profiler Utility

Provides decorators and context managers for measuring execution time
and collecting performance metrics.
"""

import asyncio
import functools
import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class TimingMetrics:
    """Container for timing statistics."""
    count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    
    @property
    def avg_time(self) -> float:
        return self.total_time / self.count if self.count > 0 else 0.0
    
    def add_measurement(self, duration: float) -> None:
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
    
    def to_dict(self) -> dict[str, float]:
        return {
            "count": self.count,
            "total_time": self.total_time,
            "min_time": self.min_time if self.min_time != float('inf') else 0.0,
            "max_time": self.max_time,
            "avg_time": self.avg_time
        }


@dataclass
class CacheMetrics:
    """Container for cache hit/miss statistics."""
    hits: int = 0
    misses: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def record_hit(self) -> None:
        self.hits += 1
    
    def record_miss(self) -> None:
        self.misses += 1
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate
        }


class PerformanceProfiler:
    """
    Centralized performance metrics collector.
    
    Thread-safe singleton for collecting timing and cache metrics
    across the application.
    """
    
    _instance: 'PerformanceProfiler | None' = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'PerformanceProfiler':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._timing_metrics: dict[str, TimingMetrics] = defaultdict(TimingMetrics)
        self._cache_metrics: dict[str, CacheMetrics] = defaultdict(CacheMetrics)
        self._metrics_lock = threading.Lock()
        self._initialized = True
    
    def record_timing(self, name: str, duration: float) -> None:
        """Record a timing measurement for a named operation."""
        with self._metrics_lock:
            self._timing_metrics[name].add_measurement(duration)
        logger.debug(f"[TIMING] {name}: {duration:.4f}s")
    
    def record_cache_hit(self, cache_name: str) -> None:
        """Record a cache hit."""
        with self._metrics_lock:
            self._cache_metrics[cache_name].record_hit()
    
    def record_cache_miss(self, cache_name: str) -> None:
        """Record a cache miss."""
        with self._metrics_lock:
            self._cache_metrics[cache_name].record_miss()
    
    def get_timing_metrics(self, name: str | None = None) -> dict[str, Any]:
        """Get timing metrics for a specific operation or all operations."""
        with self._metrics_lock:
            if name:
                return self._timing_metrics[name].to_dict()
            return {k: v.to_dict() for k, v in self._timing_metrics.items()}
    
    def get_cache_metrics(self, cache_name: str | None = None) -> dict[str, Any]:
        """Get cache metrics for a specific cache or all caches."""
        with self._metrics_lock:
            if cache_name:
                return self._cache_metrics[cache_name].to_dict()
            return {k: v.to_dict() for k, v in self._cache_metrics.items()}
    
    def get_all_metrics(self) -> dict[str, Any]:
        """Get all collected metrics."""
        return {
            "timing": self.get_timing_metrics(),
            "cache": self.get_cache_metrics()
        }
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._metrics_lock:
            self._timing_metrics.clear()
            self._cache_metrics.clear()
    
    def log_summary(self) -> None:
        """Log a summary of all metrics."""
        metrics = self.get_all_metrics()
        
        logger.info("=" * 60)
        logger.info("PERFORMANCE METRICS SUMMARY")
        logger.info("=" * 60)
        
        if metrics["timing"]:
            logger.info("\nTIMING METRICS:")
            for name, data in sorted(metrics["timing"].items()):
                logger.info(
                    f"  {name}: count={data['count']}, "
                    f"avg={data['avg_time']:.4f}s, "
                    f"min={data['min_time']:.4f}s, "
                    f"max={data['max_time']:.4f}s, "
                    f"total={data['total_time']:.2f}s"
                )
        
        if metrics["cache"]:
            logger.info("\nCACHE METRICS:")
            for name, data in sorted(metrics["cache"].items()):
                logger.info(
                    f"  {name}: hits={data['hits']}, "
                    f"misses={data['misses']}, "
                    f"hit_rate={data['hit_rate']:.2%}"
                )
        
        logger.info("=" * 60)


# Global profiler instance
profiler = PerformanceProfiler()


def timed(name: str | None = None, log_args: bool = False):
    """
    Decorator for measuring function execution time.
    
    Args:
        name: Custom name for the metric (defaults to function name)
        log_args: Whether to include function arguments in the log
    
    Example:
        @timed("database_query")
        def fetch_data(stock_code):
            ...
    """
    def decorator(func: Callable) -> Callable:
        metric_name = name or func.__qualname__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                profiler.record_timing(metric_name, duration)
                if log_args:
                    logger.debug(f"[TIMING] {metric_name}({args}, {kwargs}): {duration:.4f}s")
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                profiler.record_timing(metric_name, duration)
                if log_args:
                    logger.debug(f"[TIMING] {metric_name}({args}, {kwargs}): {duration:.4f}s")
        
        # Return appropriate wrapper based on function type
        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


def asyncio_iscoroutinefunction(func: Callable) -> bool:
    """Check if function is an async coroutine."""
    return asyncio.iscoroutinefunction(func)


@contextmanager
def TimingContext(name: str, log_on_exit: bool = True):
    """
    Context manager for measuring block execution time.
    
    Args:
        name: Name for the timing metric
        log_on_exit: Whether to log the duration when exiting
    
    Example:
        with TimingContext("data_processing"):
            process_data()
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        profiler.record_timing(name, duration)
        if log_on_exit:
            logger.info(f"[TIMING] {name}: {duration:.4f}s")


class CacheCounter:
    """
    Utility for tracking cache hits and misses.
    
    Example:
        cache_counter = CacheCounter("stock_data")
        
        if data in cache:
            cache_counter.hit()
            return cache[data]
        else:
            cache_counter.miss()
            result = fetch_data()
            cache[data] = result
            return result
    """
    
    def __init__(self, cache_name: str):
        self.cache_name = cache_name
    
    def hit(self) -> None:
        """Record a cache hit."""
        profiler.record_cache_hit(self.cache_name)
    
    def miss(self) -> None:
        """Record a cache miss."""
        profiler.record_cache_miss(self.cache_name)
    
    def get_stats(self) -> dict[str, Any]:
        """Get current cache statistics."""
        return profiler.get_cache_metrics(self.cache_name)


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return profiler
