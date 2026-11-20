"""
Smart cache manager that automatically invalidates cache when JSON files are modified
"""
import os
import json
import logging
from json_cache import json_cache

logger = logging.getLogger(__name__)

class SmartCacheManager:
    """Manages JSON cache with automatic invalidation"""
    
    def __init__(self):
        self.critical_files = {
            'products.json': 'products',
            'categories.json': 'categories', 
            'language.json': 'language',
            'config.json': 'config',
            'currencies.json': 'currencies'
        }
    
    def save_json_with_cache_invalidation(self, file_path: str, data: dict):
        """Save JSON file and automatically invalidate cache"""
        try:
            # Save the JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            # Immediately invalidate cache for this file
            json_cache.invalidate(file_path)
            
            # If it's a critical file, also invalidate related caches
            filename = os.path.basename(file_path)
            if filename in self.critical_files:
                cache_type = self.critical_files[filename]
                logger.info(f"Updated {cache_type} file, cache invalidated: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving JSON with cache invalidation: {e}")
            return False
    
    def get_json_with_smart_cache(self, file_path: str):
        """Get JSON with smart caching (checks file modification time)"""
        return json_cache.get(file_path)
    
    def force_reload_all_critical_files(self):
        """Force reload all critical JSON files"""
        reloaded = []
        for file_path in self.critical_files.keys():
            if os.path.exists(file_path):
                json_cache.invalidate(file_path)
                json_cache.get(file_path, force_reload=True)
                reloaded.append(file_path)
        
        logger.info(f"Force reloaded {len(reloaded)} critical files: {reloaded}")
        return reloaded

# Global instance
cache_manager = SmartCacheManager()

def save_json_safely(file_path: str, data: dict) -> bool:
    """Helper function to save JSON with automatic cache invalidation"""
    return cache_manager.save_json_with_cache_invalidation(file_path, data)

def get_json_cached(file_path: str):
    """Helper function to get JSON with smart caching"""
    import time
    start_time = time.time()
    
    result = cache_manager.get_json_with_smart_cache(file_path)
    
    cache_time = time.time() - start_time
    if cache_time > 0.001:  # Log if > 1ms
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 DEBUG: get_json_cached('{file_path}') took {cache_time:.3f}s")
    
    return result
