"""
Configuration for Error Correction Pipeline
"""
import os

# Pipeline Parameters (aligned with methodology)
MIN_TRIPLETS_FOR_CLUSTERING = 20  # Minimum triplets to collect before clustering
CLUSTER_COMBINE_THRESHOLD = 0.50  # 50% threshold for combining queries (relaxed for testing)
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
RULE_STORAGE_PATH = "error_correction/results"
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
CLUSTERING_LINKAGE = "average"  # Works with cosine distance
CLUSTERING_METRIC = "cosine"    # Semantic similarity for embeddings
MIN_CLUSTER_SIZE = 2
MAX_CLUSTER_SIZE = 10

# Distance Thresholds for three-level clustering (cosine: 0=identical, 1=orthogonal)
PATTERN_DISTANCE_THRESHOLD = 0.3   # Level 2: pattern+replacement similarity (stricter)
SOLUTION_DISTANCE_THRESHOLD = 0.5  # Level 3: solution similarity (more lenient)

# LLM Configuration (inherits from main ask_llm.py)
EXPLANATION_PROMPT_TEMPLATE = """You are a SQL expert. Analyze the predicted SQL query and explain why it is likely wrong based on the natural language question and database context.

Database: {db_id}
Question: {question}
Predicted SQL: {predicted_sql}

{schema_context}

Provide a concise explanation of the error in 2-3 sentences. Focus on what is wrong with the query structure, logic, or SQL syntax based on the question requirements and the database schema.

IMPORTANT: 
- Use the database schema to verify table names, column names, and relationships
- Check if the query references tables/columns that exist in the schema
- Verify JOIN conditions match foreign key relationships
- Do NOT assume you know the correct query - only explain what is wrong with the given query
- Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters)."""

SOLUTION_PROMPT_TEMPLATE = """You are a SQL expert. Based on the error explanation, suggest a concise solution for how to fix the incorrect SQL query.

Database: {db_id}
Incorrect SQL: {incorrect_query}
Explanation: {explanation}

{schema_context}

Provide a concise 2-3 sentence solution describing the key transformation needed to fix the error. Focus on what needs to change (e.g., remove JOIN, add WHERE clause, change column names) and how to change it.

IMPORTANT:
- Describe the transformation in words, NOT as SQL code
- Be concise and specific
- Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters)."""

RULE_GENERATION_PROMPT_TEMPLATE = """Generate a regex rule to transform THIS specific SQL query.

Incorrect Query: {incorrect_query}

Solution: {solution}

IMPORTANT:
- Pattern MUST match the actual query text above (not a generic pattern)
- The query IS wrong - ALWAYS provide a transformation
- Replacement must be valid SQL (no backslash escapes like \\. or \\_)

Output format (5 lines only):
PATTERN: <regex matching the query above>
REPLACEMENT: <valid SQL with \\1, \\2 backreferences>
CORRECTION: <what this does>
ERROR_TYPE: <{error_classes}>
CONFIDENCE: <high/medium/low>"""

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FILE = "error_correction/pipeline.log"
ENABLE_VERBOSE_LOGGING = True

# Paths
RESULTS_DIR = "results"
DATASET_DIR = "dataset"
