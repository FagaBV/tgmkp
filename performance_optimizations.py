"""
Performance optimizations for the shop bot to reduce response times
"""
import functools
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Cache for frequently accessed data
_cache = {}
_cache_timestamps = {}
CACHE_TTL = 300  # 5 minutes

def cached(ttl: int = CACHE_TTL):
    """Cache decorator with TTL (Time To Live)"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            current_time = time.time()
            
            # Check if we have cached data that's still valid
            if (cache_key in _cache and 
                cache_key in _cache_timestamps and 
                current_time - _cache_timestamps[cache_key] < ttl):
                return _cache[cache_key]
            
            # Call the function and cache the result
            result = func(*args, **kwargs)
            _cache[cache_key] = result
            _cache_timestamps[cache_key] = current_time
            
            return result
        return wrapper
    return decorator

def clear_cache():
    """Clear all cached data"""
    global _cache, _cache_timestamps
    _cache.clear()
    _cache_timestamps.clear()
    logger.info("Performance cache cleared")

def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    current_time = time.time()
    expired_keys = [
        key for key, timestamp in _cache_timestamps.items()
        if current_time - timestamp >= CACHE_TTL
    ]
    
    return {
        'total_entries': len(_cache),
        'expired_entries': len(expired_keys),
        'active_entries': len(_cache) - len(expired_keys),
        'cache_hit_ratio': 'N/A'  # Would need request tracking to calculate
    }

class PerformanceMonitor:
    """Monitor performance of operations"""
    
    def __init__(self):
        self.operation_times = {}
        self.slow_operations = []
    
    def time_operation(self, operation_name: str):
        """Decorator to time operations"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    end_time = time.time()
                    duration = end_time - start_time
                    
                    # Track operation times
                    if operation_name not in self.operation_times:
                        self.operation_times[operation_name] = []
                    self.operation_times[operation_name].append(duration)
                    
                    # Log slow operations (> 2 seconds)
                    if duration > 2.0:
                        self.slow_operations.append({
                            'operation': operation_name,
                            'duration': duration,
                            'timestamp': time.time()
                        })
                        logger.warning(f"Slow operation detected: {operation_name} took {duration:.2f}s")
            return wrapper
        return decorator
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        stats = {}
        for operation, times in self.operation_times.items():
            if times:
                stats[operation] = {
                    'count': len(times),
                    'avg_time': sum(times) / len(times),
                    'max_time': max(times),
                    'min_time': min(times)
                }
        
        return {
            'operation_stats': stats,
            'slow_operations_count': len(self.slow_operations),
            'recent_slow_operations': self.slow_operations[-10:]  # Last 10 slow operations
        }

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

# Decorators for common operations
database_operation = performance_monitor.time_operation('database')
api_operation = performance_monitor.time_operation('api_call')
handler_operation = performance_monitor.time_operation('handler')
