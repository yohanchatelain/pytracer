"""
Improved configuration system for pytracer.

This module provides a type-safe, validated configuration system that replaces
the old singleton-based configuration with dependency injection.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from enum import Enum

from pytracer.utils.log import get_logger

logger = get_logger()


class LogLevel(Enum):
    """Log levels for the application."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogFormat(Enum):
    """Log output formats."""
    PRINT = "print"
    LOGGER = "logger"


class IOType(Enum):
    """I/O format types."""
    PICKLE = "pickle"
    HDF5 = "hdf5"
    JSON = "json"


@dataclass
class LoggerConfig:
    """Configuration for logging system."""
    format: LogFormat = LogFormat.LOGGER
    output: str = "stdout"
    color: bool = True
    level: LogLevel = LogLevel.INFO
    
    def validate(self) -> None:
        """Validate logger configuration."""
        if self.output and self.output != "stdout":
            output_path = Path(self.output)
            if not output_path.parent.exists():
                raise ConfigurationError(
                    f"Log output directory does not exist: {output_path.parent}")


@dataclass 
class CacheConfig:
    """Configuration for cache directories."""
    root: str = ".__pytracercache__"
    traces: str = "traces"
    stats: str = "stats"
    sources: str = "sources"
    info: str = "info"
    report: str = "report"
    
    def get_traces_path(self) -> Path:
        """Get full path to traces directory."""
        return Path(self.root) / self.traces
    
    def get_stats_path(self) -> Path:
        """Get full path to stats directory."""
        return Path(self.root) / self.stats
    
    def validate(self) -> None:
        """Validate cache configuration."""
        if not self.root:
            raise ConfigurationError("Cache root directory cannot be empty")


@dataclass
class IOConfig:
    """Configuration for I/O operations."""
    type: IOType = IOType.PICKLE
    backtrace: bool = False
    cache: CacheConfig = field(default_factory=CacheConfig)
    
    def validate(self) -> None:
        """Validate I/O configuration."""
        self.cache.validate()


@dataclass
class NumpyConfig:
    """Configuration for NumPy specific settings."""
    ufunc: bool = True
    
    def validate(self) -> None:
        """Validate NumPy configuration."""
        pass


@dataclass
class TracerConfig:
    """Main configuration class for pytracer."""
    
    # Module configuration
    modules_to_load: List[str] = field(default_factory=list)
    modules_to_exclude: List[str] = field(default_factory=list)
    python_modules_path: Optional[str] = None
    
    # File filters
    include_files: List[str] = field(default_factory=list)
    exclude_files: List[str] = field(default_factory=list)
    
    # Component configurations
    logger_config: LoggerConfig = field(default_factory=LoggerConfig)
    io_config: IOConfig = field(default_factory=IOConfig)
    numpy_config: NumpyConfig = field(default_factory=NumpyConfig)
    
    @classmethod
    def from_file(cls, config_path: Union[str, Path]) -> 'TracerConfig':
        """
        Load configuration from a JSON file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            TracerConfig instance
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        
        try:
            with config_path.open() as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in config file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to read config file: {e}")
        
        return cls.from_dict(data, config_path.parent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_path: Optional[Path] = None) -> 'TracerConfig':
        """
        Create configuration from dictionary.
        
        Args:
            data: Configuration dictionary
            base_path: Base path for resolving relative paths
            
        Returns:
            TracerConfig instance
        """
        try:
            # Extract logger configuration
            logger_data = data.get('logger', {})
            logger_config = LoggerConfig(
                format=LogFormat(logger_data.get('format', 'logger')),
                output=logger_data.get('output', 'stdout'),
                color=logger_data.get('color', True),
                level=LogLevel(logger_data.get('level', 'info'))
            )
            
            # Extract cache configuration
            io_data = data.get('io', {})
            cache_data = io_data.get('cache', {})
            cache_config = CacheConfig(
                root=cache_data.get('root', '.__pytracercache__'),
                traces=cache_data.get('traces', 'traces'),
                stats=cache_data.get('stats', 'stats'),
                sources=cache_data.get('sources', 'sources'),
                info=cache_data.get('info', 'info'),
                report=cache_data.get('report', 'report')
            )
            
            # Extract I/O configuration
            io_config = IOConfig(
                type=IOType(io_data.get('type', 'pickle')),
                backtrace=io_data.get('backtrace', False),
                cache=cache_config
            )
            
            # Extract NumPy configuration
            numpy_data = data.get('numpy', {})
            numpy_config = NumpyConfig(
                ufunc=numpy_data.get('ufunc', True)
            )
            
            # Resolve relative paths
            include_files = data.get('include_file', [])
            exclude_files = data.get('exclude_file', [])
            
            if base_path:
                include_files = [cls._resolve_path(f, base_path) for f in include_files]
                exclude_files = [cls._resolve_path(f, base_path) for f in exclude_files]
            
            config = cls(
                modules_to_load=data.get('modules_to_load', []),
                modules_to_exclude=data.get('modules_to_exclude', []),
                python_modules_path=data.get('python_modules_path'),
                include_files=include_files,
                exclude_files=exclude_files,
                logger_config=logger_config,
                io_config=io_config,
                numpy_config=numpy_config
            )
            
            config.validate()
            return config
            
        except (ValueError, KeyError) as e:
            raise ConfigurationError(f"Invalid configuration data: {e}")
    
    @staticmethod
    def _resolve_path(path: str, base_path: Path) -> str:
        """Resolve relative paths against base path."""
        if os.path.isabs(path):
            return path
        return str(base_path / path)
    
    def validate(self) -> None:
        """
        Validate the entire configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate required fields
        if not self.modules_to_load:
            logger.warning("No modules specified to load")
        
        # Validate file paths
        for file_path in self.include_files + self.exclude_files:
            if not Path(file_path).exists():
                raise ConfigurationError(f"Filter file not found: {file_path}")
        
        # Validate component configurations
        self.logger_config.validate()
        self.io_config.validate()
        self.numpy_config.validate()
        
        logger.debug("Configuration validation successful")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return {
            'modules_to_load': self.modules_to_load,
            'modules_to_exclude': self.modules_to_exclude,
            'python_modules_path': self.python_modules_path,
            'include_file': self.include_files,
            'exclude_file': self.exclude_files,
            'logger': {
                'format': self.logger_config.format.value,
                'output': self.logger_config.output,
                'color': self.logger_config.color,
                'level': self.logger_config.level.value
            },
            'io': {
                'type': self.io_config.type.value,
                'backtrace': self.io_config.backtrace,
                'cache': {
                    'root': self.io_config.cache.root,
                    'traces': self.io_config.cache.traces,
                    'stats': self.io_config.cache.stats,
                    'sources': self.io_config.cache.sources,
                    'info': self.io_config.cache.info,
                    'report': self.io_config.cache.report
                }
            },
            'numpy': {
                'ufunc': self.numpy_config.ufunc
            }
        }


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""
    pass


class ConfigurationManager:
    """
    Manages configuration loading and caching.
    
    This class provides a non-singleton interface for configuration management,
    supporting dependency injection and testing.
    """
    
    def __init__(self, config: Optional[TracerConfig] = None):
        """
        Initialize configuration manager.
        
        Args:
            config: Optional pre-loaded configuration
        """
        self._config = config
    
    @classmethod
    def from_environment(cls) -> 'ConfigurationManager':
        """
        Create configuration manager from environment variables.
        
        Returns:
            ConfigurationManager instance
            
        Raises:
            ConfigurationError: If required environment variables are missing
        """
        config_path = os.getenv('PYTRACER_CONFIG')
        if not config_path:
            raise ConfigurationError("PYTRACER_CONFIG environment variable not set")
        
        config = TracerConfig.from_file(config_path)
        return cls(config)
    
    @classmethod
    def from_file(cls, config_path: Union[str, Path]) -> 'ConfigurationManager':
        """
        Create configuration manager from file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            ConfigurationManager instance
        """
        config = TracerConfig.from_file(config_path)
        return cls(config)
    
    @classmethod
    def with_defaults(cls) -> 'ConfigurationManager':
        """
        Create configuration manager with default settings.
        
        Returns:
            ConfigurationManager instance with defaults
        """
        config = TracerConfig()
        return cls(config)
    
    def get_config(self) -> TracerConfig:
        """
        Get the current configuration.
        
        Returns:
            TracerConfig instance
            
        Raises:
            ConfigurationError: If no configuration is loaded
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded")
        return self._config
    
    def reload_config(self, config_path: Union[str, Path]) -> None:
        """
        Reload configuration from file.
        
        Args:
            config_path: Path to configuration file
        """
        self._config = TracerConfig.from_file(config_path)
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration with new values.
        
        Args:
            **kwargs: Configuration values to update
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded")
        
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
            else:
                raise ConfigurationError(f"Unknown configuration key: {key}")
        
        self._config.validate()