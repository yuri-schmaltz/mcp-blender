"""Asset caching system for BlenderMCP (MP-05)."""

import os
import time
import shutil
from .constants import CACHE_DIR, CACHE_TTL_DAYS


class AssetCache:
    """Persistent cache for downloaded assets (MP-05)."""
    
    def __init__(self, cache_dir=CACHE_DIR, ttl_days=CACHE_TTL_DAYS):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_days * 24 * 3600
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, asset_id: str, asset_type: str, resolution: str = "") -> str:
        """Generate cache file path from asset identifiers."""
        import hashlib
        cache_key = f"{asset_id}_{asset_type}_{resolution}"
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{cache_hash}.cache")
    
    def get(self, asset_id: str, asset_type: str, resolution: str = "") -> str | None:
        """Retrieve cached asset path if valid, None otherwise."""
        cache_path = self._get_cache_path(asset_id, asset_type, resolution)
        
        if not os.path.exists(cache_path):
            return None
        
        # Check if cache is expired
        file_age = time.time() - os.path.getmtime(cache_path)
        if file_age > self.ttl_seconds:
            try:
                os.remove(cache_path)
            except:
                pass
            return None
        
        return cache_path
    
    def put(self, asset_id: str, asset_type: str, source_path: str, resolution: str = "") -> str:
        """Store asset in cache and return cache path."""
        cache_path = self._get_cache_path(asset_id, asset_type, resolution)
        
        try:
            shutil.copy2(source_path, cache_path)
            return cache_path
        except Exception as e:
            print(f"Failed to cache asset: {e}")
            return source_path
    
    def clear(self) -> int:
        """Clear all cached assets. Returns number of files deleted."""
        deleted = 0
        try:
            for filename in os.listdir(self.cache_dir):
                filepath = os.path.join(self.cache_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted += 1
        except Exception as e:
            print(f"Error clearing cache: {e}")
        return deleted
    
    def get_cache_size(self) -> tuple[int, int]:
        """Get cache size in bytes and number of files."""
        total_size = 0
        file_count = 0
        try:
            for filename in os.listdir(self.cache_dir):
                filepath = os.path.join(self.cache_dir, filename)
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)
                    file_count += 1
        except:
            pass
        return total_size, file_count


# Global cache instance
def get_asset_cache() -> AssetCache:
    """Get or create global asset cache instance."""
    global _asset_cache
    if '_asset_cache' not in globals():
        _asset_cache = AssetCache()
    return _asset_cache
