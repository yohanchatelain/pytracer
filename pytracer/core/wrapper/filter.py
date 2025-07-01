"""
Improved filter module for pytracer.

This module provides a clean, testable implementation of filtering functionality
with proper separation of concerns, error handling, and type safety.
"""

import os
import re
import sys
from abc import ABC, ABCMeta, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Pattern, Optional, Union
from enum import Enum

from pytracer.core.config_v2 import ConfigurationManager, TracerConfig
from pytracer.core.errors import (
    ConfigurationError, Result, Success, Failure,
    ErrorCollector, ErrorReporter
)
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Singleton

logger = get_logger()


class FilterType(Enum):
    """Types of filters available."""
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


@dataclass
class FilterRule:
    """
    Represents a single filter rule.
    
    Attributes:
        module_pattern: Regex pattern for module matching
        function_pattern: Regex pattern for function matching
        module_regex: Compiled regex for module
        function_regex: Compiled regex for function
    """
    module_pattern: str
    function_pattern: str
    module_regex: Pattern[str]
    function_regex: Pattern[str]
    
    @classmethod
    def create(cls, module_pattern: str, function_pattern: str) -> 'FilterRule':
        """
        Create a filter rule with compiled regex patterns.
        
        Args:
            module_pattern: Module pattern (supports wildcards)
            function_pattern: Function pattern (supports wildcards)
            
        Returns:
            FilterRule instance
            
        Raises:
            ValueError: If patterns are invalid
        """
        try:
            # Convert wildcards to regex
            module_regex_str = module_pattern.replace("*", ".*")
            function_regex_str = function_pattern.replace("*", ".*")
            
            module_regex = re.compile(module_regex_str)
            function_regex = re.compile(function_regex_str)
            
            return cls(
                module_pattern=module_pattern,
                function_pattern=function_pattern,
                module_regex=module_regex,
                function_regex=function_regex
            )
        except re.error as e:
            raise ValueError(f"Invalid pattern: {e}")


class FilterParser:
    """
    Parses filter files and creates filter rules.
    
    Handles file I/O and parsing logic separately from filtering logic.
    """
    
    def __init__(self, encoding: str = 'utf-8'):
        """
        Initialize filter parser.
        
        Args:
            encoding: File encoding to use
        """
        self.encoding = encoding
        self.error_collector = ErrorCollector()
    
    def parse_file(self, filepath: Union[str, Path]) -> Result[List[FilterRule]]:
        """
        Parse a filter file and return filter rules.
        
        Args:
            filepath: Path to filter file
            
        Returns:
            Result containing list of filter rules or error
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            return Failure(ConfigurationError(
                f"Filter file not found: {filepath}",
                context={'filepath': str(filepath)}
            ))
        
        rules = []
        self.error_collector.clear()
        
        try:
            with filepath.open(encoding=self.encoding) as file:
                for line_num, line in enumerate(file, 1):
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    rule_result = self._parse_line(line, line_num, str(filepath))
                    if rule_result.is_success():
                        rule = rule_result.unwrap()
                        rules.append(rule)
                        
                        # Add class method patterns for classes (uppercase first letter)
                        parts = line.split()
                        if len(parts) >= 2 and parts[1][0].isupper():
                            try:
                                class_method_rule = FilterRule.create(parts[0], f"{parts[1]}.*")
                                rules.append(class_method_rule)
                            except ValueError:
                                pass  # Ignore if pattern creation fails
                    else:
                        self.error_collector.add_result(rule_result)
        
        except Exception as e:
            return Failure(ConfigurationError(
                f"Error reading filter file: {e}",
                context={'filepath': str(filepath)},
                cause=e
            ))
        
        # Report parsing errors but still return successful rules
        if self.error_collector.has_errors():
            error_reporter = ErrorReporter()
            error_reporter.report_errors(self.error_collector.get_errors())
        
        return Success(rules)
    
    def _parse_line(self, line: str, line_num: int, filepath: str) -> Result[FilterRule]:
        """
        Parse a single line from a filter file.
        
        Args:
            line: Line content to parse
            line_num: Line number for error reporting
            filepath: File path for error reporting
            
        Returns:
            Result containing FilterRule or error
        """
        try:
            parts = line.split()
            if len(parts) != 2:
                return Failure(ConfigurationError(
                    f"Invalid filter format on line {line_num}: '{line}'. Expected: 'module function'",
                    context={
                        'line': line,
                        'line_number': line_num,
                        'filepath': filepath
                    }
                ))
            
            module_pattern, function_pattern = parts
            
            # Validate patterns
            if not module_pattern or not function_pattern:
                return Failure(ConfigurationError(
                    f"Empty pattern on line {line_num}: '{line}'",
                    context={
                        'line': line,
                        'line_number': line_num,
                        'filepath': filepath
                    }
                ))
            
            rule = FilterRule.create(module_pattern, function_pattern)
            return Success(rule)
            
        except ValueError as e:
            return Failure(ConfigurationError(
                f"Invalid pattern on line {line_num}: {e}",
                context={
                    'line': line,
                    'line_number': line_num,
                    'filepath': filepath
                },
                cause=e
            ))


class FilterEngine:
    """
    Core filtering engine that applies filter rules.
    
    Separated from parsing logic for better testability and performance.
    """
    
    def __init__(self, rules: List[FilterRule]):
        """
        Initialize filter engine with rules.
        
        Args:
            rules: List of filter rules to apply
        """
        self.rules = rules
        self._module_cache = {}  # Cache for module matching results
        self._function_cache = {}  # Cache for function matching results
    
    def matches_module(self, module_name: str) -> bool:
        """
        Check if a module matches any filter rules.
        
        Args:
            module_name: Name of module to check
            
        Returns:
            True if module matches any rule
        """
        if not module_name or not self.rules:
            return False
        
        # Check cache first
        if module_name in self._module_cache:
            return self._module_cache[module_name]
        
        # Check against all rules
        result = any(rule.module_regex.fullmatch(module_name) for rule in self.rules)
        
        # Cache result
        self._module_cache[module_name] = result
        return result
    
    def matches_function(self, function_name: str, module_name: Optional[str] = None) -> bool:
        """
        Check if a function matches any filter rules.
        
        Args:
            function_name: Name of function to check
            module_name: Optional module name for more specific matching
            
        Returns:
            True if function matches any rule
        """
        if not function_name or not self.rules:
            return False
        
        # Create cache key
        cache_key = (function_name, module_name)
        if cache_key in self._function_cache:
            return self._function_cache[cache_key]
        
        result = False
        
        if module_name:
            # Check function in specific module
            result = self._matches_function_in_module(function_name, module_name)
        else:
            # Check function across all modules
            result = self._matches_function_global(function_name)
        
        # Cache result
        self._function_cache[cache_key] = result
        return result
    
    def matches_submodule(self, submodule_name: str, module_name: str) -> bool:
        """
        Check if a submodule matches any filter rules.
        
        Args:
            submodule_name: Name of submodule to check
            module_name: Parent module name
            
        Returns:
            True if submodule matches any rule
        """
        return self.matches_function(submodule_name, module_name)
    
    def matches_entire_module(self, module_name: str) -> bool:
        """
        Check if an entire module is matched (wildcard function pattern).
        
        Args:
            module_name: Name of module to check
            
        Returns:
            True if entire module is matched
        """
        wildcard_pattern = ".*"
        return self.matches_function(wildcard_pattern, module_name)
    
    def _matches_function_in_module(self, function_name: str, module_name: str) -> bool:
        """Check if function matches in specific module."""
        for rule in self.rules:
            if (rule.module_regex.fullmatch(module_name) and
                rule.function_regex.fullmatch(function_name)):
                return True
        return False
    
    def _matches_function_global(self, function_name: str) -> bool:
        """Check if function matches across all modules."""
        for rule in self.rules:
            if rule.function_regex.fullmatch(function_name):
                return True
        return False
    
    def clear_cache(self) -> None:
        """Clear internal matching caches."""
        self._module_cache.clear()
        self._function_cache.clear()
    
    def get_stats(self) -> dict:
        """Get statistics about filter usage."""
        return {
            'total_rules': len(self.rules),
            'module_cache_size': len(self._module_cache),
            'function_cache_size': len(self._function_cache)
        }


class AbstractFilter(ABC):
    """
    Abstract base class for filters.
    
    Defines the interface that all filters must implement.
    """
    
    def __init__(self, config: TracerConfig, filter_type: FilterType):
        """
        Initialize abstract filter.
        
        Args:
            config: Tracer configuration
            filter_type: Type of filter (inclusion/exclusion)
        """
        self.config = config
        self.filter_type = filter_type
        self.parser = FilterParser()
        self.engine: Optional[FilterEngine] = None
        self._initialize()
    
    @abstractmethod
    def _get_filter_files(self) -> List[str]:
        """Get list of filter files from configuration."""
        pass
    
    def _initialize(self) -> None:
        """Initialize the filter with rules from configuration files."""
        all_rules = []
        filter_files = self._get_filter_files()
        
        for filepath in filter_files:
            if filepath:  # Skip empty/None paths
                result = self.parser.parse_file(filepath)
                if result.is_success():
                    all_rules.extend(result.unwrap())
                else:
                    if hasattr(result, 'error'):
                        logger.warning(f"Failed to parse filter file {filepath}: {result.error}")
                    else:
                        logger.warning(f"Failed to parse filter file {filepath}: Unknown error")
        
        # Add default rules
        default_rules = self._get_default_rules()
        all_rules.extend(default_rules)
        
        self.engine = FilterEngine(all_rules)
        
        logger.debug(f"Initialized {self.filter_type.value} filter with {len(all_rules)} rules")
    
    @abstractmethod
    def _get_default_rules(self) -> List[FilterRule]:
        """Get default filter rules."""
        pass
    
    def matches_module(self, module_name: str) -> bool:
        """Check if module matches filter."""
        if not self.engine:
            return False
        return self.engine.matches_module(module_name)
    
    def matches_function(self, function_name: str, module_name: Optional[str] = None) -> bool:
        """Check if function matches filter."""
        if not self.engine:
            return False
        return self.engine.matches_function(function_name, module_name)
    
    def matches_submodule(self, submodule_name: str, module_name: str) -> bool:
        """Check if submodule matches filter."""
        if not self.engine:
            return False
        return self.engine.matches_submodule(submodule_name, module_name)
    
    def matches_entire_module(self, module_name: str) -> bool:
        """Check if entire module matches filter."""
        if not self.engine:
            return False
        return self.engine.matches_entire_module(module_name)


class InclusionFilter(AbstractFilter):
    """
    Filter for including specific modules and functions.
    
    Only items that match inclusion rules will be processed.
    """
    
    def __init__(self, config: TracerConfig):
        """Initialize inclusion filter."""
        super().__init__(config, FilterType.INCLUSION)
    
    def _get_filter_files(self) -> List[str]:
        """Get inclusion filter files from configuration."""
        return self.config.include_files
    
    def _get_default_rules(self) -> List[FilterRule]:
        """Get default inclusion rules (none by default)."""
        return []


class ExclusionFilter(AbstractFilter):
    """
    Filter for excluding specific modules and functions.
    
    Items that match exclusion rules will be filtered out.
    """
    
    def __init__(self, config: TracerConfig):
        """Initialize exclusion filter."""
        super().__init__(config, FilterType.EXCLUSION)
    
    def _get_filter_files(self) -> List[str]:
        """Get exclusion filter files from configuration."""
        return self.config.exclude_files
    
    def _get_default_rules(self) -> List[FilterRule]:
        """Get default exclusion rules."""
        rules = []
        
        # Exclude built-in modules not in modules_to_load
        modules_to_load = self.config.modules_to_load
        for builtin_module in sys.builtin_module_names:
            if builtin_module not in modules_to_load:
                try:
                    rule = FilterRule.create(builtin_module, "*")
                    rules.append(rule)
                except ValueError:
                    logger.warning(f"Invalid builtin module pattern: {builtin_module}")
        
        # Exclude modules explicitly marked for exclusion
        for module_to_exclude in self.config.modules_to_exclude:
            try:
                # Exclude the module itself
                rule1 = FilterRule.create(module_to_exclude, "*")
                rules.append(rule1)
                
                # Exclude submodules
                rule2 = FilterRule.create(f"{module_to_exclude}.*", "*")
                rules.append(rule2)
            except ValueError:
                logger.warning(f"Invalid exclusion pattern: {module_to_exclude}")
        
        # Exclude standard Python modules
        if hasattr(self.config, 'python_modules_path') and self.config.python_modules_path:
            python_modules_path = self.config.python_modules_path
        else:
            version = sys.version_info
            root = sys.base_prefix
            python_modules_path = f"{root}/lib/python{version.major}.{version.minor}"
        
        try:
            if os.path.exists(python_modules_path):
                python_modules = os.listdir(python_modules_path)
                for python_module in python_modules:
                    if python_module.endswith(".py"):
                        module_name, _ = os.path.splitext(python_module)
                        if module_name not in modules_to_load:
                            try:
                                rule = FilterRule.create(module_name, "*")
                                rules.append(rule)
                            except ValueError:
                                logger.warning(f"Invalid Python module pattern: {module_name}")
        except OSError as e:
            logger.warning(f"Could not read Python modules path {python_modules_path}: {e}")
        
        return rules


class FilterManager:
    """
    Manages both inclusion and exclusion filters.
    
    Provides a unified interface for all filtering operations
    with proper precedence rules.
    """
    
    def __init__(self, config: TracerConfig):
        """
        Initialize filter manager.
        
        Args:
            config: Tracer configuration
        """
        self.config = config
        self.inclusion_filter = InclusionFilter(config)
        self.exclusion_filter = ExclusionFilter(config)
    
    def should_include(self, module_name: str, function_name: Optional[str] = None) -> bool:
        """
        Determine if a module/function should be included based on filter rules.
        
        Args:
            module_name: Name of module
            function_name: Optional function name
            
        Returns:
            True if should be included, False otherwise
        """
        # If explicitly excluded, don't include
        if self.exclusion_filter.matches_module(module_name):
            return False
        
        if function_name and self.exclusion_filter.matches_function(function_name, module_name):
            return False
        
        # If inclusion filter has rules, check inclusion
        if self.inclusion_filter.engine and self.inclusion_filter.engine.rules:
            if not self.inclusion_filter.matches_module(module_name):
                return False
            
            if function_name and not self.inclusion_filter.matches_function(function_name, module_name):
                return False
        
        return True
    
    def is_module_excluded(self, module_name: str) -> bool:
        """Check if module is explicitly excluded."""
        return self.exclusion_filter.matches_module(module_name)
    
    def is_function_excluded(self, function_name: str, module_name: Optional[str] = None) -> bool:
        """Check if function is explicitly excluded."""
        return self.exclusion_filter.matches_function(function_name, module_name)
    
    def is_entire_module_excluded(self, module_name: str) -> bool:
        """Check if entire module is excluded."""
        return self.exclusion_filter.matches_entire_module(module_name)
    
    def get_stats(self) -> dict:
        """Get statistics about filter usage."""
        inclusion_stats = self.inclusion_filter.engine.get_stats() if self.inclusion_filter.engine else {}
        exclusion_stats = self.exclusion_filter.engine.get_stats() if self.exclusion_filter.engine else {}
        
        return {
            'inclusion_filter': inclusion_stats,
            'exclusion_filter': exclusion_stats
        }


# Factory function for backward compatibility
def create_filter_manager(config_manager: ConfigurationManager) -> FilterManager:
    """
    Create a FilterManager from a configuration manager.
    
    Args:
        config_manager: Configuration manager instance
        
    Returns:
        FilterManager instance
    """
    config = config_manager.get_config()
    return FilterManager(config)


# Singleton metaclass that combines ABC and Singleton
class SingletonABCMeta(ABCMeta, Singleton):
    """Metaclass that combines ABC and Singleton patterns."""
    pass

# Backward compatibility aliases for old class names  
class FilterInclusion(InclusionFilter, metaclass=SingletonABCMeta):
    """Backward compatibility alias for InclusionFilter with Singleton pattern."""
    pass

class FilterExclusion(ExclusionFilter, metaclass=SingletonABCMeta):
    """Backward compatibility alias for ExclusionFilter with Singleton pattern.""" 
    pass

# Legacy Filter base class for compatibility
class Filter(AbstractFilter):
    """Backward compatibility base class."""
    def __init__(self, config: TracerConfig):
        # Default to exclusion filter behavior for compatibility
        super().__init__(config, FilterType.EXCLUSION)
    
    def _get_filter_files(self) -> List[str]:
        return self.config.exclude_files
    
    def _get_default_rules(self) -> List[FilterRule]:
        return []

# Public API
__all__ = [
    'FilterType',
    'FilterRule',
    'FilterParser',
    'FilterEngine',
    'AbstractFilter',
    'InclusionFilter',
    'ExclusionFilter', 
    'FilterManager',
    'create_filter_manager',
    # Backward compatibility
    'Filter',
    'FilterInclusion',
    'FilterExclusion',
]