"""
Configuration parameters for the Error Correction Pipeline

This module contains all configuration parameters used throughout the error correction pipeline.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import os
import json
import logging


@dataclass
class ErrorCorrectionConfig:
    """Configuration class for error correction pipeline parameters"""
    
    # DAIL-SQL Integration
    DAIL_SQL_PATH: str = os.path.join(os.path.dirname(__file__), "dail_sql_interface.py")  # Path to DAIL SQL interface script
    
    # Triplet and Clustering Parameters
    MIN_TRIPLET_COUNT: int = 10  # Minimum triplets before clustering
    CLUSTERING_THRESHOLD: float = 0.7  # Threshold for hierarchical clustering
    A_PERCENT_THRESHOLD: float = 0.7  # Minimum percentage of queries that must combine
    X_SAMPLE_SIZE: int = 100  # Number of correct queries to test new rules on
    MAX_CLUSTERING_ITERATIONS: int = 10  # Maximum iterations for clustering
    
    # LLM Configuration
    LLM_MODEL: str = "phi3:instruct"  # Default to local Ollama model
    LLM_API_KEY: Optional[str] = None  # API key for LLM service (not needed for Ollama)
    LLM_API_BASE: Optional[str] = None  # Base URL for API
    LLM_PROVIDER: str = "ollama"  # Default provider is ollama (local)
    MAX_TOKENS: int = 4096  # Maximum tokens for LLM responses
    TEMPERATURE: float = 0.3  # Temperature for LLM generation
    
    # Rule Validation
    RULE_VALIDATION_RETRIES: int = 3  # Number of retries for rule validation
    
    # Threshold parameters
    SIMILARITY_THRESHOLD: float = 0.85  # Threshold for query similarity matching
    CONFIDENCE_THRESHOLD: float = 0.7  # Threshold for rule confidence
    
    # Sampling parameters
    MAX_QUERIES_PER_CLUSTER: int = 50  # Maximum queries per cluster
    
    # Vector database parameters
    VECTOR_BACKEND: str = os.getenv('VECTOR_BACKEND', 'faiss')  # 'faiss' | 'chroma'
    VECTOR_DIMENSION: int = 384  # Dimension of query embeddings
    MAX_VECTOR_DB_SIZE: int = 10000  # Maximum size of vector database
    
    # Clustering parameters
    CLUSTERING_ALGORITHM: str = "hierarchical"  # Clustering algorithm to use
    MIN_CLUSTER_SIZE: int = 3  # Minimum size for a cluster
    MAX_CLUSTER_SIZE: int = 100  # Maximum size for a cluster
    
    # File paths
    DATA_DIR: str = "error_correction/data"
    CORRECT_QUERIES_DIR: str = "error_correction/data/correct_queries"
    WRONG_QUERIES_DIR: str = "error_correction/data/wrong_queries"
    RULES_DIR: str = "error_correction/data/rules"
    TRIPLETS_DIR: str = "error_correction/data/triplets"
    CONFIG_FILE: str = "error_correction/config.json"  # Configuration file path
    
    # Database parameters
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "dail_sql_error_correction"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    
    # Logging parameters
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "error_correction.log"
    
    # Performance parameters
    BATCH_SIZE: int = 32  # Batch size for processing
    MAX_WORKERS: int = 4  # Maximum number of worker threads
    CACHE_SIZE: int = 1000  # Cache size for frequently accessed data
    
    def __post_init__(self):
        """Initialize directories and validate configuration"""
        self._create_directories()
        self._validate_config()
        self._setup_logging()
    
    def _create_directories(self):
        """Create necessary directories if they don't exist"""
        directories = [
            self.DATA_DIR,
            self.CORRECT_QUERIES_DIR,
            self.WRONG_QUERIES_DIR,
            self.RULES_DIR,
            self.TRIPLETS_DIR
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=getattr(logging, self.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.LOG_FILE),
                logging.StreamHandler()
            ]
        )
    
    def _validate_config(self):
        """Validate configuration parameters"""
        if not 0 <= self.A_PERCENT_THRESHOLD <= 1:
            raise ValueError("A_PERCENT_THRESHOLD must be between 0 and 1")
        
        if not 0 <= self.SIMILARITY_THRESHOLD <= 1:
            raise ValueError("SIMILARITY_THRESHOLD must be between 0 and 1")
        
        if not 0 <= self.CONFIDENCE_THRESHOLD <= 1:
            raise ValueError("CONFIDENCE_THRESHOLD must be between 0 and 1")
        
        if not 0 <= self.CLUSTERING_THRESHOLD <= 1:
            raise ValueError("CLUSTERING_THRESHOLD must be between 0 and 1")
        
        if self.X_SAMPLE_SIZE <= 0:
            raise ValueError("X_SAMPLE_SIZE must be positive")
        
        if self.MIN_TRIPLET_COUNT <= 0:
            raise ValueError("MIN_TRIPLET_COUNT must be positive")
        
        if self.VECTOR_DIMENSION <= 0:
            raise ValueError("VECTOR_DIMENSION must be positive")
        
        if self.MAX_CLUSTERING_ITERATIONS <= 0:
            raise ValueError("MAX_CLUSTERING_ITERATIONS must be positive")
        
        if self.RULE_VALIDATION_RETRIES < 0:
            raise ValueError("RULE_VALIDATION_RETRIES must be non-negative")
        
        # Validate DAIL_SQL_PATH exists
        if not os.path.exists(self.DAIL_SQL_PATH):
            logging.warning(f"DAIL_SQL_PATH does not exist: {self.DAIL_SQL_PATH}")
        
        # Validate vector backend
        if self.VECTOR_BACKEND not in ['faiss', 'chroma']:
            logging.warning(f"Unknown VECTOR_BACKEND '{self.VECTOR_BACKEND}', defaulting to 'faiss'")
            self.VECTOR_BACKEND = 'faiss'
    
    @classmethod
    def from_env(cls) -> 'ErrorCorrectionConfig':
        """Create configuration from environment variables"""
        config_dict = {}
        
        # Map environment variables to config parameters
        env_mapping = {
            'DAIL_SQL_PATH': 'DAIL_SQL_PATH',
            'MIN_TRIPLET_COUNT': 'MIN_TRIPLET_COUNT',
            'CLUSTERING_THRESHOLD': 'CLUSTERING_THRESHOLD',
            'A_PERCENT_THRESHOLD': 'A_PERCENT_THRESHOLD',
            'X_SAMPLE_SIZE': 'X_SAMPLE_SIZE',
            'LLM_MODEL': 'LLM_MODEL',
            'LLM_API_KEY': 'LLM_API_KEY',
            'LLM_API_BASE': 'LLM_API_BASE',
            'LLM_PROVIDER': 'LLM_PROVIDER',
            'MAX_CLUSTERING_ITERATIONS': 'MAX_CLUSTERING_ITERATIONS',
            'RULE_VALIDATION_RETRIES': 'RULE_VALIDATION_RETRIES',
            'SIMILARITY_THRESHOLD': 'SIMILARITY_THRESHOLD',
            'CONFIDENCE_THRESHOLD': 'CONFIDENCE_THRESHOLD',
            'VECTOR_DIMENSION': 'VECTOR_DIMENSION',
            'MAX_TOKENS': 'MAX_TOKENS',
            'TEMPERATURE': 'TEMPERATURE',
            'LOG_LEVEL': 'LOG_LEVEL',
            'BATCH_SIZE': 'BATCH_SIZE',
            'MAX_WORKERS': 'MAX_WORKERS'
        }
        
        for env_var, config_key in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert string values to appropriate types
                if config_key in ['MIN_TRIPLET_COUNT', 'X_SAMPLE_SIZE', 'MAX_CLUSTERING_ITERATIONS', 
                                'RULE_VALIDATION_RETRIES', 'VECTOR_DIMENSION', 'MAX_TOKENS', 
                                'BATCH_SIZE', 'MAX_WORKERS']:
                    config_dict[config_key] = int(value)
                elif config_key in ['CLUSTERING_THRESHOLD', 'A_PERCENT_THRESHOLD', 'SIMILARITY_THRESHOLD', 
                                  'CONFIDENCE_THRESHOLD', 'TEMPERATURE']:
                    config_dict[config_key] = float(value)
                else:
                    config_dict[config_key] = value
        
        return cls(**config_dict)
    
    @classmethod
    def from_file(cls, config_file: str) -> 'ErrorCorrectionConfig':
        """Create configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config_dict = json.load(f)
            return cls(**config_dict)
        except FileNotFoundError:
            logging.warning(f"Config file not found: {config_file}. Using default configuration.")
            return cls()
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in config file: {e}. Using default configuration.")
            return cls()
        except Exception as e:
            logging.error(f"Error loading config file: {e}. Using default configuration.")
            return cls()
    
    def save_to_file(self, config_file: Optional[str] = None) -> bool:
        """Save configuration to JSON file"""
        try:
            file_path = config_file or self.CONFIG_FILE
            config_dict = self.to_dict()
            
            with open(file_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            logging.info(f"Configuration saved to {file_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to save configuration: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'DAIL_SQL_PATH': self.DAIL_SQL_PATH,
            'VECTOR_BACKEND': self.VECTOR_BACKEND,
            'MIN_TRIPLET_COUNT': self.MIN_TRIPLET_COUNT,
            'CLUSTERING_THRESHOLD': self.CLUSTERING_THRESHOLD,
            'A_PERCENT_THRESHOLD': self.A_PERCENT_THRESHOLD,
            'X_SAMPLE_SIZE': self.X_SAMPLE_SIZE,
            'LLM_MODEL': self.LLM_MODEL,
            'LLM_API_KEY': self.LLM_API_KEY,
            'MAX_CLUSTERING_ITERATIONS': self.MAX_CLUSTERING_ITERATIONS,
            'RULE_VALIDATION_RETRIES': self.RULE_VALIDATION_RETRIES,
            'SIMILARITY_THRESHOLD': self.SIMILARITY_THRESHOLD,
            'CONFIDENCE_THRESHOLD': self.CONFIDENCE_THRESHOLD,
            'X_SAMPLE_SIZE': self.X_SAMPLE_SIZE,
            'MAX_QUERIES_PER_CLUSTER': self.MAX_QUERIES_PER_CLUSTER,
            'VECTOR_DIMENSION': self.VECTOR_DIMENSION,
            'MAX_VECTOR_DB_SIZE': self.MAX_VECTOR_DB_SIZE,
            'MAX_TOKENS': self.MAX_TOKENS,
            'TEMPERATURE': self.TEMPERATURE,
            'CLUSTERING_ALGORITHM': self.CLUSTERING_ALGORITHM,
            'MIN_CLUSTER_SIZE': self.MIN_CLUSTER_SIZE,
            'MAX_CLUSTER_SIZE': self.MAX_CLUSTER_SIZE,
            'BATCH_SIZE': self.BATCH_SIZE,
            'MAX_WORKERS': self.MAX_WORKERS,
            'CACHE_SIZE': self.CACHE_SIZE,
            'DATA_DIR': self.DATA_DIR,
            'LOG_LEVEL': self.LOG_LEVEL,
            'LOG_FILE': self.LOG_FILE
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ErrorCorrectionConfig':
        """Create configuration from dictionary"""
        return cls(**config_dict)
    
    def update(self, **kwargs):
        """Update configuration parameters"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown configuration parameter: {key}")
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM-specific configuration"""
        return {
            'model': self.LLM_MODEL,
            'api_key': self.LLM_API_KEY,
            'max_tokens': self.MAX_TOKENS,
            'temperature': self.TEMPERATURE
        }
    
    def get_clustering_config(self) -> Dict[str, Any]:
        """Get clustering-specific configuration"""
        return {
            'min_triplet_count': self.MIN_TRIPLET_COUNT,
            'clustering_threshold': self.CLUSTERING_THRESHOLD,
            'max_iterations': self.MAX_CLUSTERING_ITERATIONS,
            'algorithm': self.CLUSTERING_ALGORITHM,
            'min_cluster_size': self.MIN_CLUSTER_SIZE,
            'max_cluster_size': self.MAX_CLUSTER_SIZE
        }
    
    def get_rule_config(self) -> Dict[str, Any]:
        """Get rule-specific configuration"""
        return {
            'a_percent_threshold': self.A_PERCENT_THRESHOLD,
            'x_sample_size': self.X_SAMPLE_SIZE,
            'validation_retries': self.RULE_VALIDATION_RETRIES,
            'confidence_threshold': self.CONFIDENCE_THRESHOLD
        }


# Default configuration instance
default_config = ErrorCorrectionConfig()
