"""
Improved wrapper system using strategy pattern.

This module provides a clean, testable wrapper system that replaces
the monolithic Wrapper class with focused, single-responsibility components.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional, Callable, Type
from dataclasses import dataclass
from enum import Enum
import functools
import inspect
import types

from pytracer.core.errors import WrapperError, Result, Success, Failure, safe_call
from pytracer.utils.log import get_logger

logger = get_logger()


class ObjectType(Enum):
    """Types of objects that can be wrapped."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    BUILTIN = "builtin"
    PROPERTY = "property"


@dataclass
class WrapperContext:
    """Context information for wrapping operations."""
    object_name: str
    object_type: ObjectType
    module_name: str
    parent_object: Optional[Any] = None
    wrapper_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def get_full_name(self) -> str:
        """Get the fully qualified name of the object."""
        if self.parent_object:
            parent_name = getattr(self.parent_object, '__name__', str(self.parent_object))
            return f"{parent_name}.{self.object_name}"
        return f"{self.module_name}.{self.object_name}"


class WrapperStrategy(ABC):
    """
    Abstract base class for object wrapping strategies.
    
    Each strategy is responsible for wrapping a specific type of object
    (functions, classes, modules, etc.) following the single responsibility principle.
    """
    
    @abstractmethod
    def can_wrap(self, obj: Any, context: WrapperContext) -> bool:
        """
        Check if this strategy can wrap the given object.
        
        Args:
            obj: Object to potentially wrap
            context: Wrapping context
            
        Returns:
            True if this strategy can wrap the object
        """
        pass
    
    @abstractmethod
    def wrap(self, obj: Any, context: WrapperContext) -> Result[Any]:
        """
        Wrap the given object.
        
        Args:
            obj: Object to wrap
            context: Wrapping context
            
        Returns:
            Result containing the wrapped object or error
        """
        pass
    
    @abstractmethod
    def unwrap(self, wrapped_obj: Any) -> Result[Any]:
        """
        Unwrap a previously wrapped object.
        
        Args:
            wrapped_obj: Wrapped object to unwrap
            
        Returns:
            Result containing the original object or error
        """
        pass
    
    def get_priority(self) -> int:
        """
        Get the priority of this strategy.
        
        Higher priority strategies are tried first.
        Default priority is 0.
        
        Returns:
            Priority value
        """
        return 0


class FunctionWrapperStrategy(WrapperStrategy):
    """Strategy for wrapping functions and methods."""
    
    WRAPPED_MARKER = '_pytracer_wrapped'
    ORIGINAL_FUNC_ATTR = '_pytracer_original'
    
    def __init__(self, tracer_callback: Optional[Callable] = None):
        """
        Initialize function wrapper strategy.
        
        Args:
            tracer_callback: Optional callback for function tracing
        """
        self.tracer_callback = tracer_callback
    
    def can_wrap(self, obj: Any, context: WrapperContext) -> bool:
        """Check if object is a function or method that can be wrapped."""
        return (
            (inspect.isfunction(obj) or inspect.ismethod(obj)) and
            not self._is_already_wrapped(obj) and
            not self._is_special_function(obj)
        )
    
    def wrap(self, obj: Any, context: WrapperContext) -> Result[Any]:
        """Wrap a function with tracing capabilities."""
        if not self.can_wrap(obj, context):
            return Failure(WrapperError(
                context.object_name,
                context.object_type.value,
                "Cannot wrap this function"
            ))
        
        try:
            wrapped_func = self._create_wrapped_function(obj, context)
            return Success(wrapped_func)
        except Exception as e:
            return Failure(WrapperError(
                context.object_name,
                context.object_type.value,
                f"Failed to create wrapper: {e}",
                cause=e
            ))
    
    def unwrap(self, wrapped_obj: Any) -> Result[Any]:
        """Unwrap a function to get the original."""
        if not self._is_already_wrapped(wrapped_obj):
            return Failure(WrapperError(
                str(wrapped_obj),
                "function",
                "Object is not wrapped"
            ))
        
        try:
            original = getattr(wrapped_obj, self.ORIGINAL_FUNC_ATTR)
            return Success(original)
        except AttributeError:
            return Failure(WrapperError(
                str(wrapped_obj),
                "function", 
                "Cannot find original function"
            ))
    
    def get_priority(self) -> int:
        return 10
    
    def _is_already_wrapped(self, obj: Any) -> bool:
        """Check if function is already wrapped."""
        return hasattr(obj, self.WRAPPED_MARKER)
    
    def _is_special_function(self, obj: Any) -> bool:
        """Check if function is a special method that shouldn't be wrapped."""
        if hasattr(obj, '__name__'):
            name = obj.__name__
            return (
                name.startswith('__') and name.endswith('__') and
                name not in {'__call__', '__init__', '__new__'}
            )
        return False
    
    def _create_wrapped_function(self, func: Any, context: WrapperContext) -> Any:
        """Create a wrapped version of the function."""
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Pre-execution tracing
            if self.tracer_callback:
                trace_context = {
                    'function_name': context.get_full_name(),
                    'args': args,
                    'kwargs': kwargs,
                    'context': context
                }
                self.tracer_callback('pre_call', trace_context)
            
            try:
                # Execute original function
                result = func(*args, **kwargs)
                
                # Post-execution tracing
                if self.tracer_callback:
                    trace_context['result'] = result
                    self.tracer_callback('post_call', trace_context)
                
                return result
                
            except Exception as e:
                # Error tracing
                if self.tracer_callback:
                    trace_context = {
                        'function_name': context.get_full_name(),
                        'args': args,
                        'kwargs': kwargs,
                        'error': e,
                        'context': context
                    }
                    self.tracer_callback('error', trace_context)
                raise
        
        # Mark as wrapped and store original
        setattr(wrapper, self.WRAPPED_MARKER, True)
        setattr(wrapper, self.ORIGINAL_FUNC_ATTR, func)
        
        return wrapper


class ClassWrapperStrategy(WrapperStrategy):
    """Strategy for wrapping classes."""
    
    WRAPPED_MARKER = '_pytracer_class_wrapped'
    ORIGINAL_CLASS_ATTR = '_pytracer_original_class'
    
    def __init__(self, method_wrapper: FunctionWrapperStrategy):
        """
        Initialize class wrapper strategy.
        
        Args:
            method_wrapper: Strategy for wrapping methods
        """
        self.method_wrapper = method_wrapper
    
    def can_wrap(self, obj: Any, context: WrapperContext) -> bool:
        """Check if object is a class that can be wrapped."""
        return (
            inspect.isclass(obj) and
            not self._is_already_wrapped(obj) and
            not self._is_builtin_class(obj)
        )
    
    def wrap(self, obj: Any, context: WrapperContext) -> Result[Any]:
        """Wrap a class by wrapping its methods."""
        if not self.can_wrap(obj, context):
            return Failure(WrapperError(
                context.object_name,
                context.object_type.value,
                "Cannot wrap this class"
            ))
        
        try:
            wrapped_class = self._create_wrapped_class(obj, context)
            return Success(wrapped_class)
        except Exception as e:
            return Failure(WrapperError(
                context.object_name,
                context.object_type.value,
                f"Failed to wrap class: {e}",
                cause=e
            ))
    
    def unwrap(self, wrapped_obj: Any) -> Result[Any]:
        """Unwrap a class to get the original."""
        if not self._is_already_wrapped(wrapped_obj):
            return Failure(WrapperError(
                str(wrapped_obj),
                "class",
                "Object is not wrapped"
            ))
        
        try:
            original = getattr(wrapped_obj, self.ORIGINAL_CLASS_ATTR)
            return Success(original)
        except AttributeError:
            return Failure(WrapperError(
                str(wrapped_obj),
                "class",
                "Cannot find original class"
            ))
    
    def get_priority(self) -> int:
        return 5
    
    def _is_already_wrapped(self, obj: Any) -> bool:
        """Check if class is already wrapped."""
        return hasattr(obj, self.WRAPPED_MARKER)
    
    def _is_builtin_class(self, obj: Any) -> bool:
        """Check if class is a builtin that shouldn't be wrapped."""
        return obj.__module__ in ('builtins', '__builtin__')
    
    def _create_wrapped_class(self, cls: Type, context: WrapperContext) -> Type:
        """Create a wrapped version of the class."""
        
        # Create new class dict with wrapped methods
        new_dict = {}
        
        for name, method in cls.__dict__.items():
            if self.method_wrapper.can_wrap(method, context):
                method_context = WrapperContext(
                    object_name=name,
                    object_type=ObjectType.METHOD,
                    module_name=context.module_name,
                    parent_object=cls
                )
                
                wrap_result = self.method_wrapper.wrap(method, method_context)
                if wrap_result.is_success():
                    new_dict[name] = wrap_result.unwrap()
                else:
                    logger.warning(f"Failed to wrap method {name}: {wrap_result.error}")
                    new_dict[name] = method
            else:
                new_dict[name] = method
        
        # Create new class with wrapped methods
        wrapped_class = type(cls.__name__, cls.__bases__, new_dict)
        
        # Mark as wrapped and store original
        setattr(wrapped_class, self.WRAPPED_MARKER, True)
        setattr(wrapped_class, self.ORIGINAL_CLASS_ATTR, cls)
        
        return wrapped_class


class ModuleWrapperStrategy(WrapperStrategy):
    """Strategy for wrapping modules."""
    
    WRAPPED_MARKER = '_pytracer_module_wrapped'
    ORIGINAL_MODULE_ATTR = '_pytracer_original_module'
    
    def __init__(self, 
                 function_wrapper: FunctionWrapperStrategy,
                 class_wrapper: ClassWrapperStrategy):
        """
        Initialize module wrapper strategy.
        
        Args:
            function_wrapper: Strategy for wrapping functions
            class_wrapper: Strategy for wrapping classes
        """
        self.function_wrapper = function_wrapper
        self.class_wrapper = class_wrapper
    
    def can_wrap(self, obj: Any, context: WrapperContext) -> bool:
        """Check if object is a module that can be wrapped."""
        return (
            inspect.ismodule(obj) and
            not self._is_already_wrapped(obj) and
            not self._is_builtin_module(obj)
        )
    
    def wrap(self, obj: Any, context: WrapperContext) -> Result[Any]:
        """Wrap a module by wrapping its functions and classes."""
        if not self.can_wrap(obj, context):
            return Failure(WrapperError(
                context.object_name,
                context.object_type.value,
                "Cannot wrap this module"
            ))
        
        try:
            wrapped_module = self._create_wrapped_module(obj, context)
            return Success(wrapped_module)
        except Exception as e:
            return Failure(WrapperError(
                context.object_name,
                context.object_type.value,
                f"Failed to wrap module: {e}",
                cause=e
            ))
    
    def unwrap(self, wrapped_obj: Any) -> Result[Any]:
        """Unwrap a module to get the original."""
        if not self._is_already_wrapped(wrapped_obj):
            return Failure(WrapperError(
                str(wrapped_obj),
                "module",
                "Object is not wrapped"
            ))
        
        try:
            original = getattr(wrapped_obj, self.ORIGINAL_MODULE_ATTR)
            return Success(original)
        except AttributeError:
            return Failure(WrapperError(
                str(wrapped_obj),
                "module",
                "Cannot find original module"
            ))
    
    def get_priority(self) -> int:
        return 1
    
    def _is_already_wrapped(self, obj: Any) -> bool:
        """Check if module is already wrapped."""
        return hasattr(obj, self.WRAPPED_MARKER)
    
    def _is_builtin_module(self, obj: Any) -> bool:
        """Check if module is a builtin that shouldn't be wrapped."""
        return getattr(obj, '__name__', '').startswith('_')
    
    def _create_wrapped_module(self, module: types.ModuleType, context: WrapperContext) -> types.ModuleType:
        """Create a wrapped version of the module."""
        
        # Create new module with same properties
        wrapped_module = types.ModuleType(module.__name__)
        wrapped_module.__dict__.update(module.__dict__)
        
        # Wrap functions and classes in the module
        for name, obj in module.__dict__.items():
            if name.startswith('_'):
                continue
                
            obj_context = WrapperContext(
                object_name=name,
                object_type=self._get_object_type(obj),
                module_name=module.__name__,
                parent_object=module
            )
            
            if self.function_wrapper.can_wrap(obj, obj_context):
                wrap_result = self.function_wrapper.wrap(obj, obj_context)
                if wrap_result.is_success():
                    setattr(wrapped_module, name, wrap_result.unwrap())
                else:
                    logger.warning(f"Failed to wrap function {name}: {wrap_result.error}")
                    
            elif self.class_wrapper.can_wrap(obj, obj_context):
                wrap_result = self.class_wrapper.wrap(obj, obj_context)
                if wrap_result.is_success():
                    setattr(wrapped_module, name, wrap_result.unwrap())
                else:
                    logger.warning(f"Failed to wrap class {name}: {wrap_result.error}")
        
        # Mark as wrapped and store original
        setattr(wrapped_module, self.WRAPPED_MARKER, True)
        setattr(wrapped_module, self.ORIGINAL_MODULE_ATTR, module)
        
        return wrapped_module
    
    def _get_object_type(self, obj: Any) -> ObjectType:
        """Determine the type of an object."""
        if inspect.isfunction(obj):
            return ObjectType.FUNCTION
        elif inspect.ismethod(obj):
            return ObjectType.METHOD
        elif inspect.isclass(obj):
            return ObjectType.CLASS
        elif inspect.ismodule(obj):
            return ObjectType.MODULE
        elif inspect.isbuiltin(obj):
            return ObjectType.BUILTIN
        else:
            return ObjectType.FUNCTION  # Default fallback


class WrapperEngine:
    """
    Main engine for object wrapping using pluggable strategies.
    
    This class coordinates multiple wrapper strategies and provides
    a unified interface for wrapping different types of objects.
    """
    
    def __init__(self, strategies: Optional[List[WrapperStrategy]] = None):
        """
        Initialize wrapper engine.
        
        Args:
            strategies: List of wrapper strategies to use
        """
        self.strategies = strategies or []
        self.strategies.sort(key=lambda s: s.get_priority(), reverse=True)
        self._wrapped_objects = {}
    
    def add_strategy(self, strategy: WrapperStrategy) -> None:
        """
        Add a wrapper strategy.
        
        Args:
            strategy: Strategy to add
        """
        self.strategies.append(strategy)
        self.strategies.sort(key=lambda s: s.get_priority(), reverse=True)
    
    def wrap_object(self, obj: Any, context: WrapperContext) -> Result[Any]:
        """
        Wrap an object using the appropriate strategy.
        
        Args:
            obj: Object to wrap
            context: Wrapping context
            
        Returns:
            Result containing wrapped object or error
        """
        # Check if already wrapped
        obj_id = id(obj)
        if obj_id in self._wrapped_objects:
            return Success(self._wrapped_objects[obj_id])
        
        # Try each strategy in priority order
        for strategy in self.strategies:
            if strategy.can_wrap(obj, context):
                result = strategy.wrap(obj, context)
                if result.is_success():
                    wrapped_obj = result.unwrap()
                    self._wrapped_objects[obj_id] = wrapped_obj
                    logger.debug(f"Wrapped {context.object_type.value} {context.object_name} using {strategy.__class__.__name__}")
                    return result
                else:
                    logger.warning(f"Strategy {strategy.__class__.__name__} failed to wrap {context.object_name}: {result.error}")
        
        # No strategy could wrap the object
        return Failure(WrapperError(
            context.object_name,
            context.object_type.value,
            "No strategy available to wrap this object"
        ))
    
    def unwrap_object(self, wrapped_obj: Any) -> Result[Any]:
        """
        Unwrap an object using the appropriate strategy.
        
        Args:
            wrapped_obj: Wrapped object to unwrap
            
        Returns:
            Result containing original object or error
        """
        for strategy in self.strategies:
            result = strategy.unwrap(wrapped_obj)
            if result.is_success():
                # Remove from wrapped objects cache
                for obj_id, cached_obj in list(self._wrapped_objects.items()):
                    if cached_obj is wrapped_obj:
                        del self._wrapped_objects[obj_id]
                        break
                return result
        
        return Failure(WrapperError(
            str(wrapped_obj),
            "unknown",
            "No strategy available to unwrap this object"
        ))
    
    def get_wrapped_count(self) -> int:
        """Get the number of wrapped objects."""
        return len(self._wrapped_objects)
    
    def clear_cache(self) -> None:
        """Clear the wrapped objects cache."""
        self._wrapped_objects.clear()


def create_default_wrapper_engine(tracer_callback: Optional[Callable] = None) -> WrapperEngine:
    """
    Create a wrapper engine with default strategies.
    
    Args:
        tracer_callback: Optional callback for function tracing
        
    Returns:
        Configured WrapperEngine
    """
    function_wrapper = FunctionWrapperStrategy(tracer_callback)
    class_wrapper = ClassWrapperStrategy(function_wrapper)
    module_wrapper = ModuleWrapperStrategy(function_wrapper, class_wrapper)
    
    return WrapperEngine([function_wrapper, class_wrapper, module_wrapper])