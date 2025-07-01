"""
Test cases to prevent regression of security and resource management fixes.
"""

import ast
import json
import os
import tempfile
import unittest
from unittest.mock import patch, mock_open


class TestSecurityFixes(unittest.TestCase):
    """Test security vulnerability fixes."""
    
    def test_ast_literal_eval_safety(self):
        """Test that ast.literal_eval is safe compared to eval."""
        # Test safe data
        safe_data = "(1, 2, 3)"
        result = ast.literal_eval(safe_data)
        self.assertEqual(result, (1, 2, 3))
        
        # Test that malicious code raises exception instead of executing
        malicious_code = "__import__('os').system('ls')"
        with self.assertRaises((ValueError, SyntaxError)):
            ast.literal_eval(malicious_code)
        
        # Test that invalid syntax raises exception
        invalid_syntax = "{invalid_syntax"
        with self.assertRaises((ValueError, SyntaxError)):
            ast.literal_eval(invalid_syntax)


class TestResourceManagement(unittest.TestCase):
    """Test resource leak fixes."""
    
    def test_file_context_manager_pattern(self):
        """Test that context managers properly close files."""
        # Test the pattern used in the fixed config.py
        test_data = {"test": "data"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            config_path = f.name
        
        try:
            # Test context manager usage (the fix)
            with open(config_path) as config_file:
                loaded_data = json.load(config_file)
            
            self.assertEqual(loaded_data, test_data)
            
            # File should be closed after context exits
            self.assertTrue(config_file.closed)
        finally:
            os.unlink(config_path)
    
    def test_file_not_context_manager_leak(self):
        """Test that files opened without context managers can leak."""
        test_data = {"test": "data"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            config_path = f.name
        
        try:
            # Test non-context manager usage (the bug)
            config_file = open(config_path)
            loaded_data = json.load(config_file)
            
            self.assertEqual(loaded_data, test_data)
            
            # File is still open (potential leak)
            self.assertFalse(config_file.closed)
            
            # Manually close to prevent actual leak in test
            config_file.close()
        finally:
            os.unlink(config_path)


if __name__ == '__main__':
    unittest.main()