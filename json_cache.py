"""
High-performance JSON file caching system to eliminate disk I/O bottlenecks
"""
import json
import os
import time
import logging
import threading
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class JSONCache:
    """Thread-safe JSON file cache with automatic reloading"""
    
    def __init__(self, cache_ttl: int = 300):  # 5 minutes default TTL
        self.cache = {}
        self.file_timestamps = {}
        self.cache_timestamps = {}
        self.cache_ttl = cache_ttl
        self.lock = threading.RLock()
        
        logger.info("JSON Cache initialized")
    
    def get(self, file_path: str, force_reload: bool = False) -> Optional[Dict[str, Any]]:
        """Get JSON data from cache or file"""
        start_time = time.time()
        file_path = str(Path(file_path).resolve())
        
        with self.lock:
            lock_acquired_time = time.time()
            current_time = time.time()
            
            # Check if file exists
            file_exists_check_time = time.time()
            if not os.path.exists(file_path):
                total_time = time.time() - start_time
                logger.warning(f"🔍 DEBUG: JSON file not found: {file_path}, check took {total_time:.3f}s")
                return None
            file_exists_duration = time.time() - file_exists_check_time
            
            # Get file modification time
            mtime_check_time = time.time()
            file_mtime = os.path.getmtime(file_path)
            mtime_duration = time.time() - mtime_check_time
            
            # Check if we need to reload
            reload_check_time = time.time()
            need_reload = (
                force_reload or
                file_path not in self.cache or
                file_path not in self.file_timestamps or
                file_path not in self.cache_timestamps or
                file_mtime > self.file_timestamps[file_path] or
                current_time - self.cache_timestamps[file_path] > self.cache_ttl
            )
            reload_check_duration = time.time() - reload_check_time
            
            if need_reload:
                try:
                    file_read_time = time.time()
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    file_read_duration = time.time() - file_read_time
                    
                    self.cache[file_path] = data
                    self.file_timestamps[file_path] = file_mtime
                    self.cache_timestamps[file_path] = current_time
                    
                    total_time = time.time() - start_time
                    filename = os.path.basename(file_path)
                    logger.info(f"🔍 DEBUG: JSON cache RELOAD {filename}: {total_time:.3f}s (lock: {lock_acquired_time-start_time:.3f}s, exists: {file_exists_duration:.3f}s, mtime: {mtime_duration:.3f}s, reload_check: {reload_check_duration:.3f}s, file_read: {file_read_duration:.3f}s)")
                    return data
                    
                except Exception as e:
                    total_time = time.time() - start_time
                    logger.error(f"🔍 DEBUG: Error loading JSON file {file_path}: {e}, took {total_time:.3f}s")
                    return None
            else:
                # Return cached data
                total_time = time.time() - start_time
                if total_time > 0.001:  # Log if > 1ms
                    filename = os.path.basename(file_path)
                    logger.info(f"🔍 DEBUG: JSON cache HIT {filename}: {total_time:.3f}s (lock: {lock_acquired_time-start_time:.3f}s, exists: {file_exists_duration:.3f}s, mtime: {mtime_duration:.3f}s, reload_check: {reload_check_duration:.3f}s)")
                return self.cache[file_path]
    
    def invalidate(self, file_path: str = None):
        """Invalidate cache for specific file or all files"""
        with self.lock:
            if file_path:
                file_path = str(Path(file_path).resolve())
                self.cache.pop(file_path, None)
                self.file_timestamps.pop(file_path, None)
                self.cache_timestamps.pop(file_path, None)
                logger.info(f"Cache invalidated for: {file_path}")
            else:
                self.cache.clear()
                self.file_timestamps.clear()
                self.cache_timestamps.clear()
                logger.info("All cache invalidated")
    
    def preload(self, file_paths: list):
        """Preload multiple JSON files into cache"""
        for file_path in file_paths:
            self.get(file_path)
        logger.info(f"Preloaded {len(file_paths)} JSON files")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            current_time = time.time()
            expired_count = sum(
                1 for timestamp in self.cache_timestamps.values()
                if current_time - timestamp > self.cache_ttl
            )
            
            return {
                'cached_files': len(self.cache),
                'expired_entries': expired_count,
                'active_entries': len(self.cache) - expired_count,
                'memory_usage_mb': self._estimate_memory_usage()
            }
    
    def _estimate_memory_usage(self) -> float:
        """Estimate cache memory usage in MB"""
        try:
            total_size = 0
            for data in self.cache.values():
                total_size += len(json.dumps(data, ensure_ascii=False))
            return total_size / (1024 * 1024)  # Convert to MB
        except:
            return 0.0

# Global cache instance
json_cache = JSONCache()

def load_json(file_path: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """Convenience function to load JSON with caching"""
    if use_cache:
        return json_cache.get(file_path)
    else:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON file {file_path}: {e}")
            return None

def preload_common_files():
    """Preload commonly used JSON files"""
    common_files = [
        'language.json',
        'config.json', 
        'products.json',
        'categories.json',
        'currencies.json'
    ]
    
    existing_files = [f for f in common_files if os.path.exists(f)]
    json_cache.preload(existing_files)
    logger.info(f"Preloaded {len(existing_files)} common JSON files")
