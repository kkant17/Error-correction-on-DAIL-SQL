"""
Configuration for Error Correction Pipeline
"""
import os

# Pipeline Parameters (aligned with methodology)
MIN_TRIPLETS_FOR_CLUSTERING = 10  # A: minimum triplets to collect before clustering (per methodology)
CLUSTER_COMBINE_THRESHOLD = 0.90  # 90% threshold for combining queries
CORRECT_QUERY_TEST_RATIO = 0.15   # Sample 15% of correct queries for validation
MIN_PASS_RATE = 0.95              # 95% pass rate requirement (per methodology)
ZERO_FAILURE_TOLERANCE = False    # Use 95% threshold instead of 100%

# Transformation & Validation Parameters
ENABLE_TRANSFORMATION = False  # Enable query transformation (default: False for safety)
ENABLE_EXECUTION_VALIDATION = False  # Enable execution-based validation (requires DB)
TRANSFORMATION_CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence to apply transformation
EXECUTION_TIMEOUT = 5  # Maximum execution time per query (seconds)

# Vector Database Configuration
VECTOR_DB_BASE_DIR = "vector_sql_db"
CORRECT_QUERIES_DB_PATH = os.path.join(VECTOR_DB_BASE_DIR, "correct")
INCORRECT_QUERIES_DB_PATH = os.path.join(VECTOR_DB_BASE_DIR, "incorrect")

# Embedding Model Configuration
SQL_EMBEDDING_MODEL = "microsoft/codebert-base"  # Can be changed to code-t5, graphcodebert, etc.
EMBEDDING_DIMENSION = 768  # CodeBERT embedding dimension
MAX_SEQUENCE_LENGTH = 512  # Maximum SQL query length for embedding

# FAISS Configuration
FAISS_INDEX_TYPE = "Flat"  # Options: Flat, IVFFlat, HNSW
SIMILARITY_METRIC = "cosine"  # Options: cosine, euclidean, dot_product

# Rule Engine Configuration
RULE_STORAGE_PATH = "error_correction/rules"
MAX_RULES_PER_CLUSTER = 50
RULE_APPLICATION_TIMEOUT = 5  # seconds

# Error Type Classes (Limited set for LLM classification)
ERROR_CLASSES = [
    "JOIN_ERROR",           # Incorrect JOIN conditions or missing JOINs
    "AGGREGATION_ERROR",    # Wrong use of GROUP BY, HAVING, or aggregate functions
    "FILTER_ERROR",         # Incorrect WHERE/HAVING conditions
    "COLUMN_SELECTION",     # Wrong columns selected or missing columns
    "SUBQUERY_ERROR",       # Issues with nested queries
    "ORDERING_ERROR",       # Incorrect ORDER BY or LIMIT
    "DISTINCT_ERROR",       # Misuse of DISTINCT
    "TABLE_REFERENCE",      # Wrong table names or aliases
    "OPERATOR_ERROR",       # Wrong operators (=, !=, >, <, etc.)
    "NULL_HANDLING",        # Incorrect handling of NULL values
    "OTHER"                 # Catch-all for unclassified errors
]

# Clustering Configuration
CLUSTERING_LINKAGE = "ward"  # Hierarchical clustering linkage method
CLUSTERING_METRIC = "euclidean"
MIN_CLUSTER_SIZE = 2
MAX_CLUSTER_SIZE = 10

# LLM Configuration (inherits from main ask_llm.py)
EXPLANATION_PROMPT_TEMPLATE = """You are a SQL expert. Compare the predicted SQL query with the gold (correct) SQL query and explain why the predicted query is wrong.

Database: {db_id}
Question: {question}
Gold SQL: {gold_sql}
Predicted SQL: {predicted_sql}

Provide a concise explanation of the error in 2-3 sentences."""

RULE_GENERATION_PROMPT_TEMPLATE = """You are a SQL expert. Based on the explanation of why a SQL query is wrong, generate a correction rule.

Incorrect Query: {incorrect_query}
Correct Query: {correct_query}
Explanation: {explanation}

Generate a rule in the following JSON format:
{{
    "pattern": "<regex pattern that matches the error signature>",
    "correction": "<description of how to transform the query to fix the error>",
    "metadata": {{
        "error_type": "<one of: {error_classes}>",
        "confidence": "<high/medium/low>",
        "description": "<brief description of the rule>"
    }}
}}

Important:
- The pattern should be a valid Python regex that identifies the specific error
- The correction should be a clear description of the transformation needed
- Choose the most appropriate error_type from the provided list
- Only output the JSON, nothing else."""

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FILE = "error_correction/pipeline.log"
ENABLE_VERBOSE_LOGGING = True

# Paths
RESULTS_DIR = "results"
DATASET_DIR = "dataset"
