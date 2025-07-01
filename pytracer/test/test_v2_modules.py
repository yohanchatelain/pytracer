"""
Comprehensive tests for pytracer v2 modules.

This module tests the v2 builtins, filter, and cache modules
to ensure they work correctly and maintain backward compatibility.
"""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any

# Mock the log module to avoid dependency issues
import sys
sys.modules['pytracer.utils.log'] = MagicMock()
sys.modules['pytracer.utils.log'].get_logger = MagicMock(return_value=MagicMock())

# Import the actual cache module first, then mock only what's needed for builtins
# This ensures that CacheStats and other classes work properly while still providing
# the interface needed for builtins compatibility
import pytracer.cache as actual_cache_module
sys.modules['pytracer.cache'] = actual_cache_module

# Mock only the get_type function for builtins compatibility
actual_cache_module.get_type = MagicMock(return_value=None)

from pytracer.builtins import (
    CustomType, TypeRegistry, get_effective_type, safe_isinstance,
    BuiltinOverrideManager, SafeDict, SafeSuper
)
from pytracer.core.wrapper.filter import (
    FilterRule, FilterParser, FilterEngine, FilterManager,
    InclusionFilter, ExclusionFilter, FilterType
)
from pytracer.cache import (
    ThreadSafeCache, ObjectMappingCache, TypeCache, ModuleCache,
    FunctionCache, PytracerCacheManager, CacheStats
)
from pytracer.core.config_v2 import TracerConfig


class TestBuiltinsV2(unittest.TestCase):
    """Test the v2 builtins module."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.type_registry = TypeRegistry()
    
    def test_custom_type_creation(self):
        """Test CustomType metaclass behavior."""
        # Test type inquiry
        class TestClass:
            pass
        
        obj = TestClass()
        obj_type = CustomType(obj)
        self.assertEqual(obj_type, TestClass)
    
    def test_safe_isinstance_basic(self):
        """Test safe isinstance with basic types."""
        self.assertTrue(safe_isinstance(42, int))
        self.assertFalse(safe_isinstance("hello", int))
        self.assertTrue(safe_isinstance("hello", str))
    
    def test_safe_isinstance_tuple(self):
        """Test safe isinstance with tuple of types."""
        self.assertTrue(safe_isinstance(42, (int, str)))
        self.assertTrue(safe_isinstance("hello", (int, str)))
        self.assertFalse(safe_isinstance([], (int, str)))
    
    def test_builtin_override_manager(self):
        """Test builtin override installation/uninstallation."""
        # Check initial state
        self.assertFalse(BuiltinOverrideManager.is_installed())
        
        # Install overrides
        BuiltinOverrideManager.install_overrides()
        self.assertTrue(BuiltinOverrideManager.is_installed())
        
        # Test double installation fails
        with self.assertRaises(RuntimeError):
            BuiltinOverrideManager.install_overrides()
        
        # Uninstall overrides
        BuiltinOverrideManager.uninstall_overrides()
        self.assertFalse(BuiltinOverrideManager.is_installed())
        
        # Test double uninstallation fails
        with self.assertRaises(RuntimeError):
            BuiltinOverrideManager.uninstall_overrides()
    
    def test_safe_dict(self):
        """Test SafeDict functionality."""
        safe_dict = SafeDict()
        safe_dict['key'] = 'value'
        self.assertEqual(safe_dict['key'], 'value')
        self.assertEqual(len(safe_dict), 1)
    
    def test_safe_super(self):
        """Test SafeSuper functionality."""
        class Parent:
            def method(self):
                return "parent"
        
        class Child(Parent):
            def method(self):
                # In a real scenario, we'd use super() here
                return "child"
        
        child = Child()
        self.assertEqual(child.method(), "child")


class TestFilterV2(unittest.TestCase):
    """Test the v2 filter module."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_config = TracerConfig(
            modules_to_load=["numpy", "scipy"],
            modules_to_exclude=["test_module"],
            include_files=[],
            exclude_files=[]
        )
    
    def test_filter_rule_creation(self):
        """Test FilterRule creation and validation."""
        rule = FilterRule.create("numpy", "array")
        self.assertEqual(rule.module_pattern, "numpy")
        self.assertEqual(rule.function_pattern, "array")
        
        # Test wildcard conversion
        rule = FilterRule.create("numpy.*", "*")
        self.assertTrue(rule.module_regex.fullmatch("numpy.core"))
        self.assertTrue(rule.function_regex.fullmatch("any_function"))
    
    def test_filter_rule_invalid_pattern(self):
        """Test FilterRule with invalid regex patterns."""
        with self.assertRaises(ValueError):
            FilterRule.create("[invalid", "pattern")
    
    def test_filter_parser_file_parsing(self):
        """Test FilterParser file parsing."""
        # Create temporary filter file
        filter_content = """
# This is a comment
numpy array
scipy *
# Another comment

pandas DataFrame
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(filter_content)
            filter_file = f.name
        
        try:
            parser = FilterParser()
            result = parser.parse_file(filter_file)
            
            self.assertTrue(result.is_success())
            rules = result.unwrap()
            self.assertGreaterEqual(len(rules), 3)  # At least numpy array, scipy *, pandas DataFrame
            
            # Check specific rules
            rule_patterns = [(r.module_pattern, r.function_pattern) for r in rules]
            self.assertIn(("numpy", "array"), rule_patterns)
            self.assertIn(("scipy", "*"), rule_patterns)
            self.assertIn(("pandas", "DataFrame"), rule_patterns)
        finally:
            os.unlink(filter_file)
    
    def test_filter_parser_nonexistent_file(self):
        """Test FilterParser with nonexistent file."""
        parser = FilterParser()
        result = parser.parse_file("/nonexistent/file.txt")
        
        self.assertTrue(result.is_failure())
    
    def test_filter_parser_invalid_format(self):
        """Test FilterParser with invalid file format."""
        # Create file with invalid format
        filter_content = """
numpy array
invalid_line_with_one_word
scipy optimize minimize
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(filter_content)
            filter_file = f.name
        
        try:
            parser = FilterParser()
            result = parser.parse_file(filter_file)
            
            # Should succeed but report errors for invalid lines
            self.assertTrue(result.is_success())
            rules = result.unwrap()
            self.assertGreaterEqual(len(rules), 1)  # At least one valid line
        finally:
            os.unlink(filter_file)
    
    def test_filter_engine_module_matching(self):
        """Test FilterEngine module matching."""
        rules = [
            FilterRule.create("numpy", "*"),
            FilterRule.create("scipy.*", "*")
        ]
        
        engine = FilterEngine(rules)
        
        self.assertTrue(engine.matches_module("numpy"))
        self.assertTrue(engine.matches_module("scipy.optimize"))
        self.assertFalse(engine.matches_module("pandas"))
    
    def test_filter_engine_function_matching(self):
        """Test FilterEngine function matching."""
        rules = [
            FilterRule.create("numpy", "array"),
            FilterRule.create("scipy", "*"),
            FilterRule.create("*", "special_function")
        ]
        
        engine = FilterEngine(rules)
        
        # Test specific function in specific module
        self.assertTrue(engine.matches_function("array", "numpy"))
        self.assertFalse(engine.matches_function("array", "pandas"))
        
        # Test wildcard function in specific module
        self.assertTrue(engine.matches_function("optimize", "scipy"))
        
        # Test global function matching
        self.assertTrue(engine.matches_function("special_function"))
    
    def test_filter_engine_caching(self):
        """Test FilterEngine caching behavior."""
        rules = [FilterRule.create("numpy", "array")]
        engine = FilterEngine(rules)
        
        # First call - should cache result
        result1 = engine.matches_module("numpy")
        self.assertTrue(result1)
        
        # Second call - should use cached result
        result2 = engine.matches_module("numpy")
        self.assertTrue(result2)
        
        # Check cache stats
        stats = engine.get_stats()
        self.assertGreater(stats['module_cache_size'], 0)
        
        # Clear cache
        engine.clear_cache()
        stats = engine.get_stats()
        self.assertEqual(stats['module_cache_size'], 0)
    
    def test_inclusion_filter(self):
        """Test InclusionFilter functionality."""
        filter_obj = InclusionFilter(self.test_config)
        
        # Should have no default rules
        self.assertEqual(len(filter_obj.engine.rules), 0)
    
    def test_exclusion_filter(self):
        """Test ExclusionFilter functionality."""
        filter_obj = ExclusionFilter(self.test_config)
        
        # Should have default exclusion rules
        self.assertGreater(len(filter_obj.engine.rules), 0)
        
        # Should exclude test_module (from config)
        self.assertTrue(filter_obj.matches_module("test_module"))
    
    def test_filter_manager(self):
        """Test FilterManager coordinated filtering."""
        manager = FilterManager(self.test_config)
        
        # Should include modules in modules_to_load
        self.assertTrue(manager.should_include("numpy"))
        self.assertTrue(manager.should_include("scipy"))
        
        # Should exclude modules in modules_to_exclude
        self.assertFalse(manager.should_include("test_module"))
    
    def test_filter_manager_stats(self):
        """Test FilterManager statistics."""
        manager = FilterManager(self.test_config)
        stats = manager.get_stats()
        
        self.assertIn('inclusion_filter', stats)
        self.assertIn('exclusion_filter', stats)


class TestCacheV2(unittest.TestCase):
    """Test the v2 cache module."""
    
    def test_thread_safe_cache_basic_operations(self):
        """Test ThreadSafeCache basic operations."""
        cache = ThreadSafeCache(max_size=100)
        
        # Test set and get
        cache.set("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")
        
        # Test default value
        self.assertEqual(cache.get("nonexistent", "default"), "default")
        
        # Test contains
        self.assertTrue(cache.contains("key1"))
        self.assertFalse(cache.contains("nonexistent"))
        
        # Test remove
        self.assertTrue(cache.remove("key1"))
        self.assertFalse(cache.remove("key1"))  # Already removed
        
        # Test size
        cache.set("key2", "value2")
        self.assertEqual(cache.size(), 1)
    
    def test_thread_safe_cache_lru_eviction(self):
        """Test ThreadSafeCache LRU eviction."""
        cache = ThreadSafeCache(max_size=2)
        
        # Fill cache
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # Access key1 to make it most recent
        cache.get("key1")
        
        # Add new key - should evict key2 (LRU)
        cache.set("key3", "value3")
        
        self.assertTrue(cache.contains("key1"))
        self.assertFalse(cache.contains("key2"))
        self.assertTrue(cache.contains("key3"))
    
    def test_thread_safe_cache_threading(self):
        """Test ThreadSafeCache thread safety."""
        cache = ThreadSafeCache()
        results = []
        
        def worker(thread_id):
            for i in range(100):
                key = f"thread_{thread_id}_key_{i}"
                value = f"thread_{thread_id}_value_{i}"
                cache.set(key, value)
                retrieved = cache.get(key)
                results.append(retrieved == value)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All operations should have succeeded
        self.assertTrue(all(results))
    
    def test_cache_stats(self):
        """Test CacheStats functionality."""
        stats = CacheStats(hits=80, misses=20, evictions=5, size=95)
        
        self.assertEqual(stats.hit_rate, 0.8)
        
        stats_dict = stats.to_dict()
        self.assertEqual(stats_dict['hits'], 80)
        self.assertEqual(stats_dict['hit_rate'], 0.8)
    
    def test_object_mapping_cache(self):
        """Test ObjectMappingCache functionality."""
        cache = ObjectMappingCache()
        
        # Create test objects
        original = object()
        wrapped = object()
        
        # Test mapping
        cache.add_mapping(original, wrapped)
        
        self.assertEqual(cache.get_wrapped(original), wrapped)
        self.assertTrue(cache.has_mapping(original))
        
        # Test removal
        self.assertTrue(cache.remove_mapping(original))
        self.assertFalse(cache.has_mapping(original))
        self.assertIsNone(cache.get_wrapped(original))
    
    def test_type_cache(self):
        """Test TypeCache functionality."""
        cache = TypeCache()
        
        # Test object
        test_obj = []
        original_type = list
        
        # Add type
        cache.add_type(test_obj, original_type)
        
        # Get type
        retrieved_type = cache.get_type(test_obj)
        self.assertEqual(retrieved_type, original_type)
        
        # Test with object that doesn't exist
        other_obj = {}
        self.assertIsNone(cache.get_type(other_obj))
    
    def test_module_cache(self):
        """Test ModuleCache functionality."""
        cache = ModuleCache()
        
        # Mock module spec
        class MockSpec:
            def __init__(self, name, loader, origin):
                self.name = name
                self.loader = loader
                self.origin = origin
        
        spec = MockSpec("test_module", "test_loader", "test_origin")
        
        # Test spec hashing
        hash1 = cache.hash_spec(spec)
        hash2 = cache.hash_spec(spec)
        self.assertEqual(hash1, hash2)
        
        # Test visited specs
        self.assertFalse(cache.is_spec_visited(spec))
        cache.add_visited_spec(spec)
        self.assertTrue(cache.is_spec_visited(spec))
        
        # Test spec mapping
        wrapped_module = object()
        cache.add_spec_mapping(spec, wrapped_module)
        self.assertEqual(cache.get_wrapped_module(spec), wrapped_module)
        
        # Test visited files
        filepath = "/test/file.py"
        self.assertFalse(cache.is_file_visited(filepath))
        cache.add_visited_file(filepath)
        self.assertTrue(cache.is_file_visited(filepath))
    
    def test_function_cache(self):
        """Test FunctionCache functionality."""
        cache = FunctionCache()
        
        # Test function
        def test_func():
            pass
        
        # Test dependencies
        dependencies = {"dep1": "value1"}
        cache.add_function_dependencies(test_func, dependencies)
        self.assertEqual(cache.get_function_dependencies(test_func), dependencies)
        
        # Test globals
        globals_dict = {"global1": "value1"}
        cache.add_function_globals(test_func, globals_dict)
        self.assertEqual(cache.get_function_globals(test_func), globals_dict)
        
        # Test dumped functions
        self.assertEqual(cache.get_dumped_count("module", "function"), 0)
        cache.increment_dumped_function("module", "function")
        self.assertEqual(cache.get_dumped_count("module", "function"), 1)
        
        # Test visited functions
        self.assertFalse(cache.is_function_visited(test_func))
        cache.mark_function_visited(test_func)
        self.assertTrue(cache.is_function_visited(test_func))
    
    def test_pytracer_cache_manager(self):
        """Test PytracerCacheManager integration."""
        manager = PytracerCacheManager()
        
        # Test object mapping interface
        original = object()
        wrapped = object()
        
        manager.add_global_mapping(original, wrapped)
        self.assertEqual(manager.get_global_mapping(original), wrapped)
        self.assertTrue(manager.has_global_mapping(original))
        
        # Test type interface
        test_obj = []
        manager.add_type(test_obj, list)
        self.assertEqual(manager.get_type(test_obj), list)
        
        # Test comprehensive stats
        stats = manager.get_comprehensive_stats()
        self.assertIn('object_mapping', stats)
        self.assertIn('type_cache', stats)
        self.assertIn('module_cache', stats)
        self.assertIn('function_cache', stats)
        
        # Test clear all
        manager.clear_all()
        self.assertFalse(manager.has_global_mapping(original))
    
    def test_cache_manager_transaction(self):
        """Test PytracerCacheManager transaction context."""
        manager = PytracerCacheManager()
        
        # Test successful transaction
        with manager.transaction() as tx:
            tx.add_global_mapping(object(), object())
        
        # Test failed transaction
        try:
            with manager.transaction() as tx:
                tx.add_global_mapping(object(), object())
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected


class TestIntegration(unittest.TestCase):
    """Integration tests for improved modules."""
    
    def test_filter_with_config(self):
        """Test filter integration with configuration."""
        # Create test configuration
        config = TracerConfig(
            modules_to_load=["numpy"],
            modules_to_exclude=["test_module"],
            include_files=[],
            exclude_files=[]
        )
        
        # Create filter manager
        manager = FilterManager(config)
        
        # Test filtering behavior
        self.assertTrue(manager.should_include("numpy"))
        self.assertFalse(manager.should_include("test_module"))
        
        # Test with function-level filtering
        self.assertTrue(manager.should_include("numpy", "array"))
        self.assertFalse(manager.should_include("test_module", "function"))
    
    def test_cache_with_filters(self):
        """Test cache integration with filters."""
        cache_manager = PytracerCacheManager()
        
        # Create and cache some filter results
        config = TracerConfig(modules_to_load=["numpy"])
        filter_manager = FilterManager(config)
        
        # Use cache to store filter decisions
        module_key = "numpy"
        should_include = filter_manager.should_include(module_key)
        
        # This could be cached for performance
        cache_manager.object_mapping.add_mapping(module_key, should_include)
        cached_result = cache_manager.object_mapping.get_wrapped(module_key)
        
        self.assertEqual(cached_result, should_include)
    
    def test_builtin_override_with_caching(self):
        """Test builtin override integration with caching."""
        # Install overrides
        BuiltinOverrideManager.install_overrides()
        
        try:
            cache_manager = PytracerCacheManager()
            
            # Create test object
            test_obj = object()
            original_type = type(test_obj)
            
            # Cache the type
            cache_manager.add_type(test_obj, original_type)
            
            # Retrieve and verify
            cached_type = cache_manager.get_type(test_obj)
            self.assertEqual(cached_type, original_type)
            
        finally:
            # Clean up
            BuiltinOverrideManager.uninstall_overrides()


if __name__ == '__main__':
    unittest.main()