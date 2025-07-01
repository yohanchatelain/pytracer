"""
Structured error handling system for pytracer.

This module provides a comprehensive exception hierarchy and result types
for explicit error handling throughout the application.
"""

from typing import TypeVar, Generic, Union, Callable, Any
from abc import ABC, abstractmethod
from enum import Enum
import traceback


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PytracerError(Exception):
    """
    Base exception for all pytracer errors.
    
    Provides structured error information including severity,
    context, and suggested actions.
    """
    
    def __init__(self, 
                 message: str,
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                 context: dict = None,
                 cause: Exception = None,
                 suggested_action: str = None):
        """
        Initialize pytracer error.
        
        Args:
            message: Human-readable error message
            severity: Error severity level
            context: Additional context information
            cause: Original exception that caused this error
            suggested_action: Suggested action to resolve the error
        """
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.context = context or {}
        self.cause = cause
        self.suggested_action = suggested_action
        self.traceback_info = traceback.format_exc()
    
    def to_dict(self) -> dict:
        """Convert error to dictionary for logging/serialization."""
        return {
            'type': self.__class__.__name__,
            'message': self.message,
            'severity': self.severity.value,
            'context': self.context,
            'cause': str(self.cause) if self.cause else None,
            'suggested_action': self.suggested_action,
            'traceback': self.traceback_info
        }
    
    def __str__(self) -> str:
        parts = [f"{self.__class__.__name__}: {self.message}"]
        
        if self.context:
            parts.append(f"Context: {self.context}")
        
        if self.suggested_action:
            parts.append(f"Suggested action: {self.suggested_action}")
        
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        
        return "\n".join(parts)


class ConfigurationError(PytracerError):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            suggested_action="Check configuration file and environment variables",
            **kwargs
        )


class ImportInterceptionError(PytracerError):
    """Raised when import interception fails."""
    
    def __init__(self, module_name: str, message: str, **kwargs):
        super().__init__(
            f"Failed to intercept import of '{module_name}': {message}",
            severity=ErrorSeverity.HIGH,
            context={'module_name': module_name},
            suggested_action="Check module name and import path",
            **kwargs
        )


class WrapperError(PytracerError):
    """Raised when function/class/module wrapping fails."""
    
    def __init__(self, obj_name: str, obj_type: str, message: str, **kwargs):
        # Merge context if provided
        base_context = {'object_name': obj_name, 'object_type': obj_type}
        if 'context' in kwargs:
            base_context.update(kwargs.pop('context'))
        
        # Use provided suggested_action or default
        suggested_action = kwargs.pop('suggested_action', 
                                     "Check if object is wrappable and not already wrapped")
        
        super().__init__(
            f"Failed to wrap {obj_type} '{obj_name}': {message}",
            severity=ErrorSeverity.MEDIUM,
            context=base_context,
            suggested_action=suggested_action,
            **kwargs
        )


class TracingError(PytracerError):
    """Raised during function execution tracing."""
    
    def __init__(self, function_name: str, message: str, **kwargs):
        super().__init__(
            f"Tracing failed for function '{function_name}': {message}",
            severity=ErrorSeverity.MEDIUM,
            context={'function_name': function_name},
            suggested_action="Check function arguments and execution context",
            **kwargs
        )


class IOError(PytracerError):
    """Raised during I/O operations (reading/writing traces)."""
    
    def __init__(self, operation: str, filepath: str, message: str, **kwargs):
        super().__init__(
            f"I/O operation '{operation}' failed for '{filepath}': {message}",
            severity=ErrorSeverity.HIGH,
            context={'operation': operation, 'filepath': filepath},
            suggested_action="Check file permissions and disk space",
            **kwargs
        )


class ParsingError(PytracerError):
    """Raised during trace parsing operations."""
    
    def __init__(self, trace_file: str, message: str, **kwargs):
        super().__init__(
            f"Failed to parse trace file '{trace_file}': {message}",
            severity=ErrorSeverity.MEDIUM,
            context={'trace_file': trace_file},
            suggested_action="Check trace file format and integrity",
            **kwargs
        )


class VisualizationError(PytracerError):
    """Raised during visualization/GUI operations."""
    
    def __init__(self, component: str, message: str, **kwargs):
        super().__init__(
            f"Visualization error in '{component}': {message}",
            severity=ErrorSeverity.LOW,
            context={'component': component},
            suggested_action="Check data format and visualization parameters",
            **kwargs
        )


# Result type for explicit error handling
T = TypeVar('T')
E = TypeVar('E', bound=Exception)


class Result(Generic[T], ABC):
    """
    Result type for explicit error handling.
    
    Provides a way to handle errors explicitly without raising exceptions,
    making error handling more predictable and testable.
    """
    
    @abstractmethod
    def is_success(self) -> bool:
        """Check if result represents success."""
        pass
    
    @abstractmethod
    def is_failure(self) -> bool:
        """Check if result represents failure."""
        pass
    
    @abstractmethod
    def unwrap(self) -> T:
        """Get the success value or raise the error."""
        pass
    
    @abstractmethod
    def unwrap_or(self, default: T) -> T:
        """Get the success value or return default."""
        pass
    
    @abstractmethod
    def map(self, func: Callable[[T], Any]) -> 'Result':
        """Apply function to success value."""
        pass
    
    @abstractmethod
    def map_error(self, func: Callable[[Exception], Exception]) -> 'Result':
        """Apply function to error value."""
        pass


class Success(Result[T]):
    """Represents a successful result."""
    
    def __init__(self, value: T):
        self.value = value
    
    def is_success(self) -> bool:
        return True
    
    def is_failure(self) -> bool:
        return False
    
    def unwrap(self) -> T:
        return self.value
    
    def unwrap_or(self, default: T) -> T:
        return self.value
    
    def map(self, func: Callable[[T], Any]) -> 'Result':
        try:
            return Success(func(self.value))
        except Exception as e:
            return Failure(e)
    
    def map_error(self, func: Callable[[Exception], Exception]) -> 'Result':
        return self
    
    def __repr__(self) -> str:
        return f"Success({self.value})"


class Failure(Result[T]):
    """Represents a failed result."""
    
    def __init__(self, error: Exception):
        self.error = error
    
    def is_success(self) -> bool:
        return False
    
    def is_failure(self) -> bool:
        return True
    
    def unwrap(self) -> T:
        raise self.error
    
    def unwrap_or(self, default: T) -> T:
        return default
    
    def map(self, func: Callable[[T], Any]) -> 'Result':
        return self
    
    def map_error(self, func: Callable[[Exception], Exception]) -> 'Result':
        try:
            return Failure(func(self.error))
        except Exception as e:
            return Failure(e)
    
    def __repr__(self) -> str:
        return f"Failure({self.error})"


def safe_call(func: Callable[..., T], *args, **kwargs) -> Result[T]:
    """
    Safely call a function and return a Result.
    
    Args:
        func: Function to call
        *args: Positional arguments
        **kwargs: Keyword arguments
    
    Returns:
        Result containing either the return value or the exception
    """
    try:
        result = func(*args, **kwargs)
        return Success(result)
    except Exception as e:
        return Failure(e)


def safe_call_with_context(func: Callable[..., T], 
                          context: dict,
                          error_type: type = PytracerError,
                          *args, 
                          **kwargs) -> Result[T]:
    """
    Safely call a function with additional context for errors.
    
    Args:
        func: Function to call
        context: Context information for errors
        error_type: Type of error to wrap exceptions in
        *args: Positional arguments
        **kwargs: Keyword arguments
    
    Returns:
        Result containing either the return value or wrapped exception
    """
    try:
        result = func(*args, **kwargs)
        return Success(result)
    except Exception as e:
        if isinstance(e, PytracerError):
            wrapped_error = e
        else:
            wrapped_error = error_type(
                message=str(e),
                context=context,
                cause=e
            )
        return Failure(wrapped_error)


class ErrorCollector:
    """
    Collects multiple errors for batch processing.
    
    Useful for validation and processing operations that can have
    multiple independent errors.
    """
    
    def __init__(self):
        self.errors = []
    
    def add_error(self, error: Exception) -> None:
        """Add an error to the collection."""
        self.errors.append(error)
    
    def add_result(self, result: Result[T]) -> None:
        """Add a result, collecting any errors."""
        if result.is_failure():
            self.errors.append(result.error)
    
    def has_errors(self) -> bool:
        """Check if any errors have been collected."""
        return len(self.errors) > 0
    
    def get_errors(self) -> list:
        """Get all collected errors."""
        return self.errors.copy()
    
    def clear(self) -> None:
        """Clear all collected errors."""
        self.errors.clear()
    
    def to_result(self, success_value: T = None) -> Result[T]:
        """
        Convert to a Result.
        
        Args:
            success_value: Value to return if no errors
        
        Returns:
            Success if no errors, Failure with first error otherwise
        """
        if self.has_errors():
            return Failure(self.errors[0])
        return Success(success_value)


class ErrorReporter:
    """
    Reports errors to various outputs (logs, files, etc.).
    
    Provides structured error reporting with different formats
    and severity-based filtering.
    """
    
    def __init__(self, min_severity: ErrorSeverity = ErrorSeverity.LOW):
        self.min_severity = min_severity
    
    def should_report(self, error: PytracerError) -> bool:
        """Check if error should be reported based on severity."""
        severity_order = [
            ErrorSeverity.LOW,
            ErrorSeverity.MEDIUM, 
            ErrorSeverity.HIGH,
            ErrorSeverity.CRITICAL
        ]
        
        return (severity_order.index(error.severity) >= 
                severity_order.index(self.min_severity))
    
    def report_error(self, error: Exception) -> None:
        """
        Report a single error.
        
        Args:
            error: Error to report
        """
        if isinstance(error, PytracerError):
            if self.should_report(error):
                self._report_pytracer_error(error)
        else:
            self._report_generic_error(error)
    
    def report_errors(self, errors: list) -> None:
        """
        Report multiple errors.
        
        Args:
            errors: List of errors to report
        """
        for error in errors:
            self.report_error(error)
    
    def _report_pytracer_error(self, error: PytracerError) -> None:
        """Report a PytracerError with full context."""
        from pytracer.utils.log import get_logger
        logger = get_logger()
        
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(str(error))
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(str(error))
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(str(error))
        else:
            logger.info(str(error))
    
    def _report_generic_error(self, error: Exception) -> None:
        """Report a generic exception."""
        from pytracer.utils.log import get_logger
        logger = get_logger()
        logger.error(f"Unexpected error: {error}")