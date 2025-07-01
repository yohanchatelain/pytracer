"""
Improved cache module for pytracer.

This module provides a clean, thread-safe cache implementation with proper
lifecycle management, type safety, and monitoring capabilities.
"""

import threading
import types
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Set, Optional, List, Callable, TypeVar, Generic
from collections import defaultdict
from contextlib import contextmanager

from pytracer.core.errors import Result, Success, Failure, PytracerError

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


class CacheError(PytracerError):
    """Raised when cache operations fail."""
    pass


@dataclass
class CacheStats:
    """Statistics about cache usage."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'size': self.size,
            'hit_rate': self.hit_rate
        }


class ThreadSafeCache(Generic[K, V]):
    """
    Thread-safe cache implementation with size limits and statistics.
    
    Provides a safe caching mechanism with proper concurrency control
    and optional size limitations.
    """
    
    def __init__(self, max_size: Optional[int] = None, name: str = "cache"):
        """
        Initialize thread-safe cache.
        
        Args:
            max_size: Maximum number of items in cache (None for unlimited)
            name: Name for debugging and logging
        """
        self.max_size = max_size
        self.name = name
        self._cache: Dict[K, V] = {}
        self._access_order: List[K] = []  # For LRU eviction
        self._lock = threading.RLock()
        self._stats = CacheStats()
    
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            default: Default value if key not found
            
        Returns:
            Cached value or default
        """
        with self._lock:
            if key in self._cache:
                self._stats.hits += 1
                # Move to end for LRU
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
                return self._cache[key]
            else:
                self._stats.misses += 1
                return default
    
    def set(self, key: K, value: V) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            # Check if we need to evict
            if (self.max_size is not None and 
                key not in self._cache and 
                len(self._cache) >= self.max_size):
                self._evict_lru()
            
            # Add/update item
            if key not in self._cache:
                self._stats.size += 1
            
            self._cache[key] = value
            
            # Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
    
    def remove(self, key: K) -> bool:
        """
        Remove item from cache.
        
        Args:
            key: Cache key to remove
            
        Returns:
            True if item was removed, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                self._stats.size -= 1
                return True
            return False
    
    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            evicted_count = len(self._cache)
            self._cache.clear()
            self._access_order.clear()
            self._stats.evictions += evicted_count
            self._stats.size = 0
    
    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if self._access_order:
            lru_key = self._access_order[0]
            del self._cache[lru_key]
            self._access_order.remove(lru_key)
            self._stats.evictions += 1
            self._stats.size -= 1
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            stats_copy = CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                size=len(self._cache)
            )
            return stats_copy
    
    def contains(self, key: K) -> bool:
        """Check if key exists in cache."""
        with self._lock:
            return key in self._cache
    
    def keys(self) -> List[K]:
        """Get all keys in cache."""
        with self._lock:
            return list(self._cache.keys())
    
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


class ObjectMappingCache:
    """
    Cache for object mappings using weak references.
    
    Maintains mappings between original and wrapped objects
    while allowing for proper garbage collection.
    """
    
    def __init__(self, name: str = "object_mapping"):
        """Initialize object mapping cache."""
        self.name = name
        self._id_to_wrapped: Dict[int, Any] = {}
        self._wrapped_to_original = weakref.WeakValueDictionary()
        self._lock = threading.RLock()
        self._stats = CacheStats()
    
    def add_mapping(self, original: Any, wrapped: Any) -> None:
        """
        Add mapping between original and wrapped object.
        
        Args:
            original: Original object
            wrapped: Wrapped object
        """
        with self._lock:
            original_id = id(original)
            self._id_to_wrapped[original_id] = wrapped
            
            # Use weak reference for reverse mapping
            try:
                self._wrapped_to_original[id(wrapped)] = original
            except TypeError:
                # Some objects can't be weakly referenced
                pass
            
            self._stats.size += 1
    
    def get_wrapped(self, original: Any) -> Optional[Any]:
        """
        Get wrapped object for original.
        
        Args:
            original: Original object
            
        Returns:
            Wrapped object if found, None otherwise
        """
        with self._lock:
            original_id = id(original)
            if original_id in self._id_to_wrapped:
                self._stats.hits += 1
                return self._id_to_wrapped[original_id]
            else:
                self._stats.misses += 1
                return None
    
    def get_original(self, wrapped: Any) -> Optional[Any]:
        """
        Get original object for wrapped.
        
        Args:
            wrapped: Wrapped object
            
        Returns:
            Original object if found, None otherwise
        """
        with self._lock:
            wrapped_id = id(wrapped)
            original = self._wrapped_to_original.get(wrapped_id)
            if original is not None:
                self._stats.hits += 1
                return original
            else:
                self._stats.misses += 1
                return None
    
    def has_mapping(self, original: Any) -> bool:
        """Check if original object has a mapping."""
        with self._lock:
            return id(original) in self._id_to_wrapped
    
    def remove_mapping(self, original: Any) -> bool:
        """
        Remove mapping for original object.
        
        Args:
            original: Original object
            
        Returns:
            True if mapping was removed, False if not found
        """
        with self._lock:
            original_id = id(original)
            if original_id in self._id_to_wrapped:
                wrapped = self._id_to_wrapped[original_id]
                del self._id_to_wrapped[original_id]
                
                # Remove reverse mapping if it exists
                wrapped_id = id(wrapped)
                if wrapped_id in self._wrapped_to_original:
                    del self._wrapped_to_original[wrapped_id]
                
                self._stats.size -= 1
                return True
            return False
    
    def clear(self) -> None:
        """Clear all mappings."""
        with self._lock:
            self._id_to_wrapped.clear()
            self._wrapped_to_original.clear()
            self._stats.size = 0
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                size=len(self._id_to_wrapped)
            )


class TypeCache:
    """
    Cache for object type information.
    
    Stores original types of objects for proper type handling
    in the pytracer system.
    """
    
    def __init__(self, max_size: int = 10000):
        """Initialize type cache."""
        self._cache: ThreadSafeCache[tuple, type] = ThreadSafeCache(max_size, "type_cache")
    
    def add_type(self, obj: Any, obj_type: type) -> None:
        """
        Add type information for object.
        
        Args:
            obj: Object to store type for
            obj_type: Type of the object
        """
        key = (id(obj), obj.__sizeof__ if hasattr(obj, '__sizeof__') else 0)
        self._cache.set(key, obj_type)
    
    def get_type(self, obj: Any) -> Optional[type]:
        """
        Get stored type for object.
        
        Args:
            obj: Object to get type for
            
        Returns:
            Stored type if found, None otherwise
        """
        key = (id(obj), obj.__sizeof__ if hasattr(obj, '__sizeof__') else 0)
        return self._cache.get(key)
    
    def clear(self) -> None:
        """Clear type cache."""
        self._cache.clear()
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._cache.get_stats()


class ModuleCache:
    """
    Cache for module-related information.
    
    Stores module states, specifications, and other module-related data.
    """
    
    def __init__(self):
        """Initialize module cache."""
        self.visited_specs: ThreadSafeCache[int, Any] = ThreadSafeCache(name="visited_specs")
        self.spec_to_wrapped: ThreadSafeCache[int, Any] = ThreadSafeCache(name="spec_to_wrapped")
        self.required_modules: ThreadSafeCache[int, List] = ThreadSafeCache(name="required_modules")
        self.visited_files: Set[str] = set()
        self._files_lock = threading.Lock()
    
    def hash_spec(self, spec: Any) -> int:
        """
        Create hash for module spec.
        
        Args:
            spec: Module specification
            
        Returns:
            Hash value for spec
        """
        if hasattr(spec, 'name') and hasattr(spec, 'loader') and hasattr(spec, 'origin'):
            return hash((spec.name, spec.loader, spec.origin))
        return hash(str(spec))
    
    def add_visited_spec(self, spec: Any) -> None:
        """Mark spec as visited."""
        spec_hash = self.hash_spec(spec)
        self.visited_specs.set(spec_hash, spec)
    
    def is_spec_visited(self, spec: Any) -> bool:
        """Check if spec has been visited."""
        spec_hash = self.hash_spec(spec)
        return self.visited_specs.contains(spec_hash)
    
    def add_spec_mapping(self, spec: Any, wrapped_module: Any) -> None:
        """Add mapping from spec to wrapped module."""
        spec_hash = self.hash_spec(spec)
        self.spec_to_wrapped.set(spec_hash, wrapped_module)
    
    def get_wrapped_module(self, spec: Any) -> Optional[Any]:
        """Get wrapped module for spec."""
        spec_hash = self.hash_spec(spec)
        return self.spec_to_wrapped.get(spec_hash)
    
    def add_required_modules(self, module: Any, requirements: List) -> None:
        """Add required modules for a module."""
        module_id = id(module)
        self.required_modules.set(module_id, requirements)
    
    def get_required_modules(self, module: Any) -> List:
        """Get required modules for a module."""
        module_id = id(module)
        return self.required_modules.get(module_id, [])
    
    def add_visited_file(self, filepath: str) -> None:
        """Mark file as visited."""
        with self._files_lock:
            self.visited_files.add(filepath)
    
    def is_file_visited(self, filepath: str) -> bool:
        """Check if file has been visited."""
        with self._files_lock:
            return filepath in self.visited_files
    
    def clear(self) -> None:
        """Clear all module cache data."""
        self.visited_specs.clear()
        self.spec_to_wrapped.clear()
        self.required_modules.clear()
        with self._files_lock:
            self.visited_files.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'visited_specs': self.visited_specs.get_stats().to_dict(),
            'spec_to_wrapped': self.spec_to_wrapped.get_stats().to_dict(),
            'required_modules': self.required_modules.get_stats().to_dict(),
            'visited_files_count': len(self.visited_files)
        }


class FunctionCache:
    """
    Cache for function-related information.
    
    Stores function dependencies, dumped functions, and other function metadata.
    """
    
    def __init__(self):
        """Initialize function cache."""
        self.function_dependencies: ThreadSafeCache[int, Dict] = ThreadSafeCache(name="function_deps")
        self.function_globals: ThreadSafeCache[int, Dict] = ThreadSafeCache(name="function_globals")
        self.dumped_functions: ThreadSafeCache[str, int] = ThreadSafeCache(name="dumped_functions")
        self.visited_functions: ThreadSafeCache[int, bool] = ThreadSafeCache(name="visited_functions")
    
    def add_function_dependencies(self, func: Any, dependencies: Dict) -> None:
        """Add dependencies for function."""
        func_id = id(func)
        self.function_dependencies.set(func_id, dependencies)
    
    def get_function_dependencies(self, func: Any) -> Dict:
        """Get dependencies for function."""
        func_id = id(func)
        return self.function_dependencies.get(func_id, {})
    
    def add_function_globals(self, func: Any, globals_dict: Dict) -> None:
        """Add global variables for function."""
        func_id = id(func)
        self.function_globals.set(func_id, globals_dict)
    
    def get_function_globals(self, func: Any) -> Dict:
        """Get global variables for function."""
        func_id = id(func)
        return self.function_globals.get(func_id, {})
    
    def increment_dumped_function(self, module: str, function: str) -> None:
        """Increment count for dumped function."""
        key = f"{module}.{function}"
        current_count = self.dumped_functions.get(key, 0)
        self.dumped_functions.set(key, current_count + 1)
    
    def get_dumped_count(self, module: str, function: str) -> int:
        """Get dump count for function."""
        key = f"{module}.{function}"
        return self.dumped_functions.get(key, 0)
    
    def mark_function_visited(self, func: Any) -> None:
        """Mark function as visited."""
        func_id = id(func)
        self.visited_functions.set(func_id, True)
    
    def is_function_visited(self, func: Any) -> bool:
        """Check if function has been visited."""
        func_id = id(func)
        return self.visited_functions.get(func_id, False)
    
    def clear(self) -> None:
        """Clear all function cache data."""
        self.function_dependencies.clear()
        self.function_globals.clear()
        self.dumped_functions.clear()
        self.visited_functions.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'function_dependencies': self.function_dependencies.get_stats().to_dict(),
            'function_globals': self.function_globals.get_stats().to_dict(),
            'dumped_functions': self.dumped_functions.get_stats().to_dict(),
            'visited_functions': self.visited_functions.get_stats().to_dict()
        }


class PytracerCacheManager:
    """
    Central cache manager for all pytracer caching needs.
    
    Provides a unified interface to all cache subsystems with
    proper lifecycle management and monitoring.
    """
    
    def __init__(self):
        """Initialize cache manager."""
        self.object_mapping = ObjectMappingCache()
        self.type_cache = TypeCache()
        self.module_cache = ModuleCache()
        self.function_cache = FunctionCache()
        
        # Legacy compatibility
        self.globals_to_update: Dict[Any, Dict] = {}
        self.cached_error: Optional[Any] = None
        
        # Hidden module for required functions
        self.hidden = types.ModuleType('cache.hidden')
        self.hidden.required_functions = {
            "numpy": [
                "ufunc", "nan", "frompyfunc", "isscalar", "dtype",
                "isnan", "ndarray", "issubdtype", "can_cast"
            ],
            "scipy.linalg._fblas": ["daxpy"]
        }
    
    # Object mapping interface
    def add_global_mapping(self, original: Any, wrapped: Any) -> None:
        """Add global object mapping."""
        self.object_mapping.add_mapping(original, wrapped)
    
    def get_global_mapping(self, original: Any) -> Optional[Any]:
        """Get wrapped object for original."""
        return self.object_mapping.get_wrapped(original)
    
    def has_global_mapping(self, original: Any) -> bool:
        """Check if object has global mapping."""
        return self.object_mapping.has_mapping(original)
    
    # Type interface
    def add_type(self, obj: Any, obj_type: type) -> None:
        """Add type information for object."""
        self.type_cache.add_type(obj, obj_type)
    
    def get_type(self, obj: Any) -> Optional[type]:
        """Get type information for object."""
        return self.type_cache.get_type(obj)
    
    # Module interface
    def hash_spec(self, spec: Any) -> int:
        """Hash module specification."""
        return self.module_cache.hash_spec(spec)
    
    def add_visited_spec(self, spec: Any) -> None:
        """Mark spec as visited."""
        self.module_cache.add_visited_spec(spec)
    
    # Function interface
    def increment_visit(self, module: str, function: str) -> None:
        """Increment visit count for function."""
        self.function_cache.increment_dumped_function(module, function)
    
    def clear_all(self) -> None:
        """Clear all caches."""
        self.object_mapping.clear()
        self.type_cache.clear()
        self.module_cache.clear()
        self.function_cache.clear()
        self.globals_to_update.clear()
        self.cached_error = None
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics from all caches."""
        return {
            'object_mapping': self.object_mapping.get_stats().to_dict(),
            'type_cache': self.type_cache.get_stats().to_dict(),
            'module_cache': self.module_cache.get_stats(),
            'function_cache': self.function_cache.get_stats(),
            'globals_to_update_size': len(self.globals_to_update),
            'has_cached_error': self.cached_error is not None
        }
    
    @contextmanager
    def transaction(self):
        """
        Context manager for cache transactions.
        
        Allows for atomic cache operations that can be rolled back
        if something goes wrong.
        """
        # For now, this is a placeholder for future implementation
        # of transactional cache operations
        try:
            yield self
        except Exception:
            # In a full implementation, this would rollback changes
            raise


# Global cache instance for backward compatibility
cache_manager = PytracerCacheManager()

# Legacy interface functions for backward compatibility
def add_global_mapping(original: Any, wrapped: Any) -> None:
    """Legacy function for adding global mapping."""
    cache_manager.add_global_mapping(original, wrapped)

def get_global_mapping(original: Any) -> Optional[Any]:
    """Legacy function for getting global mapping."""
    return cache_manager.get_global_mapping(original)

def has_global_mapping(original: Any) -> bool:
    """Legacy function for checking global mapping."""
    return cache_manager.has_global_mapping(original)

def add_type(obj: Any, obj_type: type) -> None:
    """Legacy function for adding type."""
    cache_manager.add_type(obj, obj_type)

def get_type(obj: Any) -> Optional[type]:
    """Legacy function for getting type."""
    return cache_manager.get_type(obj)

def hash_spec(spec: Any) -> int:
    """Legacy function for hashing spec."""
    return cache_manager.hash_spec(spec)

def increment_visit(module: str, function: str) -> None:
    """Legacy function for incrementing visit count."""
    cache_manager.increment_visit(module, function)

# Legacy global variables for backward compatibility
visited_functions = {}
visited_files = set()
modules_not_initialized = {}
submodules = {}
orispec_to_wrappedmodule = {}
required_modules = {}
visited_spec = {}
function_to_dependencies_dict = {}
function_to_dependencies_globals = {}
dumped_functions = {}
globals_to_update = cache_manager.globals_to_update
cached_error = None
module_args = {}

# Legacy functions for backward compatibility
def set_module_args(args):
    """Set module arguments from command line args."""
    module_args.update(vars(args))


# Public API
__all__ = [
    'CacheStats',
    'ThreadSafeCache',
    'ObjectMappingCache',
    'TypeCache',
    'ModuleCache',
    'FunctionCache',
    'PytracerCacheManager',
    'cache_manager',
    # Legacy interface
    'add_global_mapping',
    'get_global_mapping',
    'has_global_mapping',
    'add_type',
    'get_type',
    'hash_spec',
    'increment_visit',
]