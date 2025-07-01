"""
Isolated tests for the improved pytracer architecture.

These tests are completely isolated from the existing codebase
to avoid dependency issues during testing.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any
import sys

# Mock the old config system to avoid circular dependencies
sys.modules['pytracer.utils.log'] = MagicMock()
sys.modules['pytracer.utils.log'].get_logger = MagicMock(return_value=MagicMock())

from pytracer.core.config_v2 import (
    TracerConfig, ConfigurationManager, ConfigurationError,
    LoggerConfig, IOConfig, CacheConfig, NumpyConfig,
    LogLevel, LogFormat, IOType
)
from pytracer.core.errors import (
    PytracerError, WrapperError, ImportInterceptionError,
    Result, Success, Failure, safe_call, ErrorCollector, ErrorReporter
)
from pytracer.core.wrapper_v2 import (
    WrapperStrategy, FunctionWrapperStrategy, ClassWrapperStrategy,
    ModuleWrapperStrategy, WrapperEngine, WrapperContext, ObjectType,
    create_default_wrapper_engine
)


class TestConfigurationSystemIsolated(unittest.TestCase):
    """Test the improved configuration system in isolation."""
    
    def setUp(self):
        self.test_config_data = {
            "modules_to_load": ["numpy", "scipy"],
            "modules_to_exclude": ["test_module"],
            "include_file": [],  # Empty to avoid file validation issues
            "exclude_file": [],
            "logger": {
                "format": "logger",
                "output": "stdout",
                "color": True,
                "level": "info"
            },
            "io": {
                "type": "pickle",
                "backtrace": False,
                "cache": {
                    "root": ".__pytracercache__",
                    "traces": "traces",
                    "stats": "stats"
                }
            },
            "numpy": {
                "ufunc": True
            }
        }
    
    def test_tracer_config_from_dict(self):
        """Test creating TracerConfig from dictionary."""
        config = TracerConfig.from_dict(self.test_config_data)
        
        self.assertEqual(config.modules_to_load, ["numpy", "scipy"])
        self.assertEqual(config.modules_to_exclude, ["test_module"])
        self.assertEqual(config.logger_config.format, LogFormat.LOGGER)
        self.assertEqual(config.logger_config.level, LogLevel.INFO)
        self.assertEqual(config.io_config.type, IOType.PICKLE)
        self.assertTrue(config.numpy_config.ufunc)
    
    def test_tracer_config_validation_success(self):
        """Test successful configuration validation."""
        config = TracerConfig.from_dict(self.test_config_data)
        # Should not raise an exception
        config.validate()
    
    def test_tracer_config_from_file(self):
        """Test loading configuration from file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.test_config_data, f)
            config_path = f.name
        
        try:
            config = TracerConfig.from_file(config_path)
            self.assertEqual(config.modules_to_load, ["numpy", "scipy"])
        finally:
            os.unlink(config_path)
    
    def test_tracer_config_file_not_found(self):
        """Test error handling when config file doesn't exist."""
        with self.assertRaises(ConfigurationError):
            TracerConfig.from_file("/nonexistent/config.json")
    
    def test_tracer_config_invalid_json(self):
        """Test error handling for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json}")
            config_path = f.name
        
        try:
            with self.assertRaises(ConfigurationError):
                TracerConfig.from_file(config_path)
        finally:
            os.unlink(config_path)
    
    def test_configuration_manager_with_defaults(self):
        """Test ConfigurationManager with default settings."""
        manager = ConfigurationManager.with_defaults()
        config = manager.get_config()
        self.assertIsInstance(config, TracerConfig)
        self.assertEqual(config.modules_to_load, [])
    
    def test_cache_config_paths(self):
        """Test CacheConfig path generation."""
        cache_config = CacheConfig(root="test_cache", traces="test_traces")
        
        traces_path = cache_config.get_traces_path()
        self.assertEqual(str(traces_path), "test_cache/test_traces")
        
        stats_path = cache_config.get_stats_path()
        self.assertEqual(str(stats_path), "test_cache/stats")
    
    def test_config_to_dict(self):
        """Test configuration serialization."""
        config = TracerConfig.from_dict(self.test_config_data)
        serialized = config.to_dict()
        
        self.assertEqual(serialized['modules_to_load'], ["numpy", "scipy"])
        self.assertEqual(serialized['logger']['level'], "info")


class TestErrorHandlingIsolated(unittest.TestCase):
    """Test the improved error handling system in isolation."""
    
    def test_pytracer_error_creation(self):
        """Test PytracerError creation with context."""
        context = {"module": "test_module", "function": "test_func"}
        error = WrapperError("test_obj", "function", "Test error message",
                           context=context, suggested_action="Try again")
        
        self.assertIn("test_obj", str(error))
        self.assertIn("Test error message", str(error))
        
        # Context should be merged with object info
        expected_context = {
            "object_name": "test_obj", 
            "object_type": "function",
            "module": "test_module", 
            "function": "test_func"
        }
        self.assertEqual(error.context, expected_context)
        self.assertEqual(error.suggested_action, "Try again")
    
    def test_pytracer_error_to_dict(self):
        """Test error serialization to dictionary."""
        error = ImportInterceptionError("numpy", "Import failed")
        error_dict = error.to_dict()
        
        self.assertEqual(error_dict['type'], 'ImportInterceptionError')
        self.assertIn('numpy', error_dict['message'])
        self.assertEqual(error_dict['context']['module_name'], 'numpy')
    
    def test_result_success(self):
        """Test Result type for successful operations."""
        result = Success(42)
        
        self.assertTrue(result.is_success())
        self.assertFalse(result.is_failure())
        self.assertEqual(result.unwrap(), 42)
        self.assertEqual(result.unwrap_or(0), 42)
    
    def test_result_failure(self):
        """Test Result type for failed operations."""
        error = ValueError("Test error")
        result = Failure(error)
        
        self.assertFalse(result.is_success())
        self.assertTrue(result.is_failure())
        self.assertEqual(result.unwrap_or(42), 42)
        
        with self.assertRaises(ValueError):
            result.unwrap()
    
    def test_result_map_success(self):
        """Test Result.map for successful results."""
        result = Success(5)
        mapped = result.map(lambda x: x * 2)
        
        self.assertTrue(mapped.is_success())
        self.assertEqual(mapped.unwrap(), 10)
    
    def test_result_map_failure(self):
        """Test Result.map for failed results."""
        result = Failure(ValueError("Test error"))
        mapped = result.map(lambda x: x * 2)
        
        self.assertTrue(mapped.is_failure())
        self.assertIsInstance(mapped.error, ValueError)
    
    def test_safe_call_success(self):
        """Test safe_call with successful function."""
        def divide(a, b):
            return a / b
        
        result = safe_call(divide, 10, 2)
        self.assertTrue(result.is_success())
        self.assertEqual(result.unwrap(), 5.0)
    
    def test_safe_call_failure(self):
        """Test safe_call with failing function."""
        def divide(a, b):
            return a / b
        
        result = safe_call(divide, 10, 0)
        self.assertTrue(result.is_failure())
        self.assertIsInstance(result.error, ZeroDivisionError)
    
    def test_error_collector(self):
        """Test ErrorCollector for accumulating errors."""
        collector = ErrorCollector()
        
        self.assertFalse(collector.has_errors())
        
        collector.add_error(ValueError("Error 1"))
        collector.add_error(TypeError("Error 2"))
        
        self.assertTrue(collector.has_errors())
        self.assertEqual(len(collector.get_errors()), 2)
        
        result = collector.to_result("success")
        self.assertTrue(result.is_failure())
        self.assertIsInstance(result.error, ValueError)
    
    def test_error_collector_with_results(self):
        """Test ErrorCollector with Result objects."""
        collector = ErrorCollector()
        
        collector.add_result(Success(42))
        collector.add_result(Failure(ValueError("Error")))
        
        self.assertTrue(collector.has_errors())
        self.assertEqual(len(collector.get_errors()), 1)


class TestWrapperSystemIsolated(unittest.TestCase):
    """Test the improved wrapper system in isolation."""
    
    def setUp(self):
        self.tracer_callback = MagicMock()
        self.function_wrapper = FunctionWrapperStrategy(self.tracer_callback)
        self.class_wrapper = ClassWrapperStrategy(self.function_wrapper)
        self.engine = WrapperEngine([self.function_wrapper, self.class_wrapper])
    
    def test_function_wrapper_can_wrap(self):
        """Test function wrapper strategy detection."""
        def test_func():
            return 42
        
        context = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION,
            module_name="test"
        )
        
        self.assertTrue(self.function_wrapper.can_wrap(test_func, context))
        self.assertFalse(self.function_wrapper.can_wrap(42, context))
        self.assertFalse(self.function_wrapper.can_wrap("string", context))
    
    def test_function_wrapper_wrap(self):
        """Test function wrapping."""
        def test_func(x):
            return x * 2
        
        context = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION,
            module_name="test"
        )
        
        result = self.function_wrapper.wrap(test_func, context)
        self.assertTrue(result.is_success())
        
        wrapped_func = result.unwrap()
        
        # Test that wrapped function works
        self.assertEqual(wrapped_func(5), 10)
        
        # Test that callback was called
        self.tracer_callback.assert_called()
    
    def test_function_wrapper_unwrap(self):
        """Test function unwrapping."""
        def test_func():
            return 42
        
        context = WrapperContext(
            object_name="test_func", 
            object_type=ObjectType.FUNCTION,
            module_name="test"
        )
        
        wrap_result = self.function_wrapper.wrap(test_func, context)
        wrapped_func = wrap_result.unwrap()
        
        unwrap_result = self.function_wrapper.unwrap(wrapped_func)
        self.assertTrue(unwrap_result.is_success())
        
        original_func = unwrap_result.unwrap()
        self.assertEqual(original_func, test_func)
    
    def test_function_wrapper_already_wrapped(self):
        """Test detection of already wrapped functions."""
        def test_func():
            return 42
        
        context = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION, 
            module_name="test"
        )
        
        # Wrap once
        result1 = self.function_wrapper.wrap(test_func, context)
        wrapped_func = result1.unwrap()
        
        # Try to wrap again
        result2 = self.function_wrapper.wrap(wrapped_func, context)
        self.assertTrue(result2.is_failure())
    
    def test_class_wrapper_can_wrap(self):
        """Test class wrapper strategy detection."""
        class TestClass:
            def method(self):
                return 42
        
        context = WrapperContext(
            object_name="TestClass",
            object_type=ObjectType.CLASS,
            module_name="test"
        )
        
        self.assertTrue(self.class_wrapper.can_wrap(TestClass, context))
        self.assertFalse(self.class_wrapper.can_wrap(int, context))  # builtin
        self.assertFalse(self.class_wrapper.can_wrap(42, context))
    
    def test_wrapper_engine_integration(self):
        """Test WrapperEngine with multiple strategies."""
        def test_func():
            return 42
        
        class TestClass:
            def method(self):
                return 24
        
        func_context = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION,
            module_name="test"
        )
        
        class_context = WrapperContext(
            object_name="TestClass", 
            object_type=ObjectType.CLASS,
            module_name="test"
        )
        
        # Test function wrapping
        func_result = self.engine.wrap_object(test_func, func_context)
        self.assertTrue(func_result.is_success())
        
        # Test class wrapping
        class_result = self.engine.wrap_object(TestClass, class_context)
        self.assertTrue(class_result.is_success())
        
        # Test wrapped count
        self.assertEqual(self.engine.get_wrapped_count(), 2)
    
    def test_wrapper_engine_no_strategy(self):
        """Test WrapperEngine when no strategy can wrap object."""
        context = WrapperContext(
            object_name="string_obj",
            object_type=ObjectType.FUNCTION,
            module_name="test"
        )
        
        result = self.engine.wrap_object("string", context)
        self.assertTrue(result.is_failure())
        self.assertIsInstance(result.error, WrapperError)
    
    def test_create_default_wrapper_engine(self):
        """Test creating default wrapper engine."""
        callback = MagicMock()
        engine = create_default_wrapper_engine(callback)
        
        self.assertEqual(len(engine.strategies), 3)  # function, class, module
        
        # Test that strategies are ordered by priority
        priorities = [s.get_priority() for s in engine.strategies]
        self.assertEqual(priorities, sorted(priorities, reverse=True))


class TestWrapperContextIsolated(unittest.TestCase):
    """Test WrapperContext functionality in isolation."""
    
    def test_wrapper_context_creation(self):
        """Test WrapperContext creation."""
        context = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION,
            module_name="test_module",
            metadata={"key": "value"}
        )
        
        self.assertEqual(context.object_name, "test_func")
        self.assertEqual(context.object_type, ObjectType.FUNCTION)
        self.assertEqual(context.module_name, "test_module")
        self.assertEqual(context.metadata["key"], "value")
    
    def test_wrapper_context_full_name(self):
        """Test full name generation."""
        # Without parent
        context1 = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION,
            module_name="test_module"
        )
        self.assertEqual(context1.get_full_name(), "test_module.test_func")
        
        # With parent
        class Parent:
            __name__ = "ParentClass"
        
        context2 = WrapperContext(
            object_name="test_method",
            object_type=ObjectType.METHOD,
            module_name="test_module",
            parent_object=Parent()
        )
        self.assertEqual(context2.get_full_name(), "ParentClass.test_method")


class TestArchitecturalIntegration(unittest.TestCase):
    """Test integration between architectural components."""
    
    def test_config_and_error_handling_integration(self):
        """Test integration between configuration and error handling."""
        # Test configuration error creation
        with self.assertRaises(ConfigurationError) as cm:
            TracerConfig.from_file("/nonexistent/config.json")
        
        error = cm.exception
        self.assertIsInstance(error, ConfigurationError)
        self.assertIn("not found", str(error))
    
    def test_wrapper_and_error_handling_integration(self):
        """Test integration between wrapper system and error handling."""
        engine = WrapperEngine([])  # No strategies
        
        context = WrapperContext(
            object_name="test_func",
            object_type=ObjectType.FUNCTION,
            module_name="test"
        )
        
        result = engine.wrap_object(lambda: None, context)
        
        self.assertTrue(result.is_failure())
        self.assertIsInstance(result.error, WrapperError)
        
        # Test error information
        error_dict = result.error.to_dict()
        self.assertEqual(error_dict['type'], 'WrapperError')
        self.assertIn('test_func', error_dict['message'])
    
    def test_full_pipeline_simulation(self):
        """Test a simplified version of the full tracing pipeline."""
        # 1. Configuration
        config_data = {
            "modules_to_load": ["test_module"],
            "logger": {"level": "debug"}
        }
        config = TracerConfig.from_dict(config_data)
        
        # 2. Wrapper engine setup
        tracer_events = []
        
        def mock_tracer(event, context):
            tracer_events.append((event, context['function_name']))
        
        engine = create_default_wrapper_engine(mock_tracer)
        
        # 3. Wrap a test function
        def test_function(x, y):
            return x + y
        
        context = WrapperContext(
            object_name="test_function",
            object_type=ObjectType.FUNCTION,
            module_name=config.modules_to_load[0]
        )
        
        wrap_result = engine.wrap_object(test_function, context)
        self.assertTrue(wrap_result.is_success())
        
        # 4. Execute wrapped function
        wrapped_func = wrap_result.unwrap()
        result = wrapped_func(10, 20)
        
        # 5. Verify results
        self.assertEqual(result, 30)
        self.assertEqual(len(tracer_events), 2)  # pre_call and post_call
        self.assertEqual(tracer_events[0][0], 'pre_call')
        self.assertEqual(tracer_events[1][0], 'post_call')
        self.assertIn('test_function', tracer_events[0][1])


if __name__ == '__main__':
    unittest.main()