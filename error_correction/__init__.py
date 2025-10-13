"""
Error Correction Pipeline for DAIL-SQL

This module provides a comprehensive error correction pipeline that includes:
- Vector database management for storing and retrieving queries
- Rule engine for validation and application of correction rules
- LLM explainer for generating explanations
- Rule generator for creating rules from explanations
- Clustering manager for hierarchical clustering of query-rule triplets
- Pipeline orchestrator for coordinating the entire process

The pipeline follows a systematic approach to error correction:
1. Store correct and wrong queries in vector databases
2. Generate explanations for query errors using LLM
3. Generate rules from explanations
4. Cluster query-explanation-rule triplets hierarchically
5. Apply rules to correct similar errors
"""

from .vector_db_manager import VectorDBManager
from .rule_engine import RuleEngine, RuleTester
from .llm_explainer import LLMExplainer
from .rule_generator import RuleGenerator
from .clustering_manager import ClusteringManager
from .pipeline_orchestrator import PipelineOrchestrator, ErrorCorrectionPipeline
from .config import ErrorCorrectionConfig

__version__ = "1.0.0"
__author__ = "DAIL-SQL Error Correction Team"

__all__ = [
    "VectorDBManager",
    "RuleEngine",
    "RuleTester", 
    "LLMExplainer",
    "RuleGenerator",
    "ClusteringManager",
    "PipelineOrchestrator",
    "ErrorCorrectionPipeline",
    "ErrorCorrectionConfig"
]
