"""
Improved builtins module for pytracer.

This module provides a clean, type-safe implementation of builtin overrides
with proper error handling, documentation, and following Python best practices.
"""

import builtins
import inspect
import types
from typing import Any, Optional, Union, Tuple, TypeVar

try:
    import pytracer.cache as cache_module
except (ImportError, AttributeError):
    # Fallback for testing or when cache module is not available
    import sys
    if 'pytracer.cache' in sys.modules:
        cache_module = sys.modules['pytracer.cache']
    else:
        # Create a minimal cache interface for testing
        class _MockCache:
            @staticmethod
            def get_type(obj):
                return None
            @staticmethod
            def add_type(obj, obj_type):
                pass
        cache_module = _MockCache()

# Type variables for better type hints
T = TypeVar('T')
ClassInfo = Union[type, Tuple[type, ...]]

# Store original builtins for safe access
_ORIGINAL_BUILTINS = {
    'type': builtins.type,
    'isinstance': builtins.isinstance,
    'super': builtins.super,
    'issubclass': builtins.issubclass,
    'object': builtins.object,
    'globals': builtins.globals,
}

# Store original types functions
_ORIGINAL_TYPES = {
    'new_class': types.new_class,
    'prepare_class': types.prepare_class,
    'resolve_bases': types.resolve_bases,
    'MappingProxyType': types.MappingProxyType,
}

# Store original inspect functions
_ORIGINAL_INSPECT = {
    'isclass': inspect.isclass,
}

# Constants
PYTRACER_INSTANCE_ATTR = '_Pytracer_instance'


class TypeRegistry:
    """
    Registry for managing type mappings in pytracer.
    
    Provides a clean interface to the cache system for type management.
    """
    
    @staticmethod
    def get_original_type(obj: Any) -> Optional[type]:
        """
        Get the original type of an object from cache.
        
        Args:
            obj: Object to get original type for
            
        Returns:
            Original type if found in cache, None otherwise
        """
        return cache_module.get_type(obj)
    
    @staticmethod
    def register_type(obj: Any, original_type: type) -> None:
        """
        Register an object's original type in cache.
        
        Args:
            obj: Object to register
            original_type: Original type of the object
        """
        cache_module.add_type(obj, original_type)


def get_effective_type(obj: Any) -> type:
    """
    Get the effective type of an object, checking cache first.
    
    Args:
        obj: Object to get type for
        
    Returns:
        The effective type of the object
    """
    cached_type = TypeRegistry.get_original_type(obj)
    if cached_type is not None:
        return cached_type
    return _ORIGINAL_BUILTINS['type'](obj)


def safe_type(*args: Any, **kwargs: Any) -> Union[type, Any]:
    """
    Safe type function that handles both type checking and type creation.
    
    Args:
        *args: Arguments passed to type()
        **kwargs: Keyword arguments passed to type()
        
    Returns:
        Type information or new type depending on arguments
    """
    if len(args) == 1:
        # Type inquiry: type(obj)
        obj = args[0]
        effective_type = get_effective_type(obj)
        
        # Return original type if we have a custom Type instance
        if effective_type == CustomType:
            return _ORIGINAL_BUILTINS['type']
        return effective_type
    else:
        # Type creation: type(name, bases, dict)
        return _ORIGINAL_BUILTINS['type'](*args, **kwargs)


class CustomType(type):
    """
    Custom type metaclass that integrates with pytracer's type system.
    
    This metaclass allows pytracer to track and modify type behavior
    while maintaining compatibility with Python's type system.
    """
    
    def __new__(cls, *args: Any, **kwargs: Any) -> Union['CustomType', type]:
        """
        Create a new type instance.
        
        Args:
            *args: Arguments for type creation
            **kwargs: Keyword arguments for type creation
            
        Returns:
            New type instance
        """
        if len(args) == 3 and cls.__name__ != 'CustomType':
            # Normal type creation with name, bases, dict
            return _ORIGINAL_BUILTINS['type'].__new__(cls, *args, **kwargs)
        
        # Type inquiry or special handling
        return safe_type(*args, **kwargs)


def get_original_type(type_obj: type) -> type:
    """
    Get the original type from a potentially wrapped type.
    
    Args:
        type_obj: Type object to unwrap
        
    Returns:
        Original type
    """
    if type_obj == CustomType:
        return _ORIGINAL_BUILTINS['type']
    return type_obj


def safe_isinstance(obj: Any, class_or_tuple: ClassInfo, /) -> bool:
    """
    Safe isinstance function that works with pytracer's type system.
    
    Args:
        obj: Object to check
        class_or_tuple: Class or tuple of classes to check against
        
    Returns:
        True if obj is instance of class_or_tuple
    """
    if _ORIGINAL_BUILTINS['isinstance'](class_or_tuple, tuple):
        # Handle tuple of types
        unwrapped_tuple = tuple(
            get_original_type(cls) for cls in class_or_tuple
        )
        return _ORIGINAL_BUILTINS['isinstance'](obj, unwrapped_tuple)
    elif class_or_tuple == CustomType:
        # Special case for our custom type
        return _ORIGINAL_BUILTINS['isinstance'](obj, _ORIGINAL_BUILTINS['type'])
    else:
        # Normal isinstance check - single type
        return _ORIGINAL_BUILTINS['isinstance'](obj, class_or_tuple)


def safe_issubclass(cls: type, classinfo: ClassInfo) -> bool:
    """
    Safe issubclass function that works with pytracer's type system.
    
    Args:
        cls: Class to check
        classinfo: Class or tuple of classes to check against
        
    Returns:
        True if cls is subclass of classinfo
    """
    # For now, delegate to original implementation
    # This can be enhanced later if needed
    return _ORIGINAL_BUILTINS['issubclass'](cls, classinfo)


class SafeDict(dict):
    """
    Safe dictionary implementation for pytracer use.
    
    This provides a dict-like interface while allowing for
    potential tracing and monitoring of dictionary operations.
    """
    
    def __getitem__(self, key: Any) -> Any:
        """Get item with potential tracing."""
        return super().__getitem__(key)
    
    def __setitem__(self, key: Any, value: Any) -> None:
        """Set item with potential tracing."""
        super().__setitem__(key, value)


class SafeSuper(super):
    """
    Safe super implementation for pytracer use.
    
    Provides compatibility with pytracer's type system while
    maintaining all functionality of the original super().
    """
    
    def __new__(cls, *args: Any, **kwargs: Any) -> 'SafeSuper':
        """Create new super instance with proper type handling."""
        return _ORIGINAL_BUILTINS['super'](_ORIGINAL_BUILTINS['type']).__new__(
            cls, *args, **kwargs
        )
    
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call super with proper delegation."""
        return _ORIGINAL_BUILTINS['super'].__call__(*args, **kwargs)


class SafeMappingProxyType(dict):
    """
    Safe MappingProxyType implementation.
    
    Provides dict-like behavior while maintaining compatibility
    with pytracer's tracing system.
    """
    
    def __getitem__(self, key: Any) -> Any:
        """Get item with potential tracing."""
        return super().__getitem__(key)
    
    def __setitem__(self, key: Any, value: Any) -> None:
        """Set item with potential tracing."""
        super().__setitem__(key, value)


# Type creation wrappers
def safe_new_class(*args: Any, **kwargs: Any) -> type:
    """Safe wrapper for types.new_class."""
    return _ORIGINAL_TYPES['new_class'](*args, **kwargs)


def safe_prepare_class(*args: Any, **kwargs: Any) -> Any:
    """Safe wrapper for types.prepare_class."""
    return _ORIGINAL_TYPES['prepare_class'](*args, **kwargs)


def safe_resolve_bases(*args: Any, **kwargs: Any) -> Tuple[type, ...]:
    """Safe wrapper for types.resolve_bases."""
    return _ORIGINAL_TYPES['resolve_bases'](*args, **kwargs)


def safe_isclass(obj: Any) -> bool:
    """
    Safe isclass function that works with pytracer instances.
    
    Args:
        obj: Object to check
        
    Returns:
        True if obj is a class, False otherwise
    """
    # Check for pytracer instance marker
    if hasattr(obj, PYTRACER_INSTANCE_ATTR):
        return False
    
    return _ORIGINAL_INSPECT['isclass'](obj)


class BuiltinOverrideManager:
    """
    Manager for builtin function overrides.
    
    Provides a clean interface for installing and uninstalling
    pytracer's builtin overrides with proper state management.
    """
    
    _overrides_installed = False
    _original_builtins_backup = {}
    
    @classmethod
    def install_overrides(cls) -> None:
        """
        Install pytracer's builtin overrides.
        
        Raises:
            RuntimeError: If overrides are already installed
        """
        if cls._overrides_installed:
            raise RuntimeError("Builtin overrides are already installed")
        
        # Backup original builtins
        cls._original_builtins_backup = {
            'type': builtins.type,
            'isinstance': builtins.isinstance,
            'issubclass': builtins.issubclass,
        }
        
        # Install our overrides
        builtins.type = CustomType
        builtins.isinstance = safe_isinstance
        builtins.issubclass = safe_issubclass
        
        cls._overrides_installed = True
    
    @classmethod
    def uninstall_overrides(cls) -> None:
        """
        Uninstall pytracer's builtin overrides.
        
        Raises:
            RuntimeError: If overrides are not currently installed
        """
        if not cls._overrides_installed:
            raise RuntimeError("Builtin overrides are not installed")
        
        # Restore original builtins
        for name, original_func in cls._original_builtins_backup.items():
            setattr(builtins, name, original_func)
        
        cls._original_builtins_backup.clear()
        cls._overrides_installed = False
    
    @classmethod
    def is_installed(cls) -> bool:
        """Check if overrides are currently installed."""
        return cls._overrides_installed


# Convenience function for backward compatibility
def overload_builtins() -> None:
    """
    Install pytracer's builtin overrides.
    
    This function provides backward compatibility with the original
    overload_builtins() function while using the new manager.
    """
    BuiltinOverrideManager.install_overrides()


# Public API
__all__ = [
    'CustomType',
    'TypeRegistry',
    'get_effective_type',
    'safe_type',
    'safe_isinstance',
    'safe_issubclass',
    'safe_isclass',
    'SafeDict',
    'SafeSuper',
    'SafeMappingProxyType',
    'BuiltinOverrideManager',
    'overload_builtins',
]