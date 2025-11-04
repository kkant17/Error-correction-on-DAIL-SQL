# Error Correction Pipeline for DAIL-SQL

An intelligent error correction pipeline that learns from SQL query generation errors and creates reusable correction rules through LLM-generated explanations and hierarchical clustering.

## Overview

This pipeline implements an advanced error correction system that:

1. **Classifies Queries**: Separates correct and incorrect SQL queries from base model output
2. **Stores in Vector Database**: Uses FAISS to efficiently store and retrieve similar queries
3. **Generates Explanations**: Uses LLM to explain why incorrect queries are wrong
4. **Creates Correction Rules**: Generates regex-based rules with transformation descriptions
5. **Validates Rules**: Ensures rules correctly identify the error patterns
6. **Clusters Similar Rules**: Groups related rules using hierarchical clustering
7. **Tests on Correct Queries**: Zero-failure validation against correct query samples
8. **Saves Validated Rules**: Stores production-ready rules for future use

## Architecture

```
error_correction/
├── vector_store/          # Vector database management
│   ├── embedder.py        # CodeBERT SQL embeddings
│   └── vector_db.py       # FAISS operations
├── rule_engine/           # Rule generation and application
│   ├── rule_schema.py     # Data structures
│   ├── rule_generator.py  # LLM-based generation
│   └── rule_applicator.py # Regex matching
├── clustering/            # Hierarchical clustering
│   └── hierarchical_cluster.py
├── config.py              # Configuration
├── pipeline.py            # Main orchestrator
└── requirements.txt       # Dependencies
```

## Installation

### Prerequisites

Ensure you have the base DAIL-SQL environment set up. Then install additional dependencies:

```bash
# Install additional requirements
pip install -r error_correction/requirements.txt
```

### GPU Support (Optional but Recommended)

#### NVIDIA GPU (CUDA)

For faster embedding generation with NVIDIA GPUs:

```bash
# For CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For GPU-enabled FAISS
pip uninstall faiss-cpu
pip install faiss-gpu
```

#### Intel Arc GPU (XPU)

**✅ Fully compatible with Intel Arc GPUs using ipex-llm!**

The pipeline automatically detects Intel Arc GPUs and supports:
- LLM calls via your existing ipex-llm setup (via Ollama)
- Auto-detection of XPU for embeddings (or CPU fallback)
- Seamless integration with your current workflow

```bash
# Test Intel Arc compatibility
python error_correction/test_intel_arc.py

# The pipeline auto-detects Intel Arc, no extra config needed!
```

For detailed Intel Arc setup and optimization, see [INTEL_ARC_SETUP.md](INTEL_ARC_SETUP.md)

## Configuration

Edit [config.py](config.py) to customize pipeline behavior:

```python
# Key Parameters
MIN_TRIPLETS_FOR_CLUSTERING = 15  # Minimum triplets before clustering
CLUSTER_COMBINE_THRESHOLD = 0.90  # 90% combine threshold
CORRECT_QUERY_TEST_RATIO = 0.15   # Sample 15% of correct queries
ZERO_FAILURE_TOLERANCE = True     # Zero-failure requirement

# Embedding Model
SQL_EMBEDDING_MODEL = "microsoft/codebert-base"

# Error Classification
ERROR_CLASSES = [
    "JOIN_ERROR", "AGGREGATION_ERROR", "FILTER_ERROR",
    "COLUMN_SELECTION", "SUBQUERY_ERROR", "ORDERING_ERROR",
    "DISTINCT_ERROR", "TABLE_REFERENCE", "OPERATOR_ERROR",
    "NULL_HANDLING", "OTHER"
]
```

## Usage

### Step 1: Run Base Model and Generate Evaluation

First, run the base DAIL-SQL model:

```bash
python ask_llm.py \
  --model gpt-4 \
  --question ./dataset/process/SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096 \
  --openai_api_key YOUR_API_KEY
```

This creates:
- `RESULTS_MODEL-{model}.txt` - Predicted queries
- `results/eval_{model}.txt` - Evaluation results

### Step 2: Run Error Correction Pipeline

```bash
python error_correction/pipeline.py \
  --eval_results results/eval_gpt-4.txt \
  --predictions_file ./dataset/process/SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096/RESULTS_MODEL-gpt-4.txt \
  --questions_file ./dataset/process/SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096/questions.json \
  --model gpt-4 \
  --openai_api_key YOUR_API_KEY \
  --temperature 0.3
```

#### Optional Parameters

```bash
# Test with limited queries
--max_triplets 20

# Use custom API endpoint (Ollama, etc.)
--openai_api_base http://localhost:11434/v1
```

### Step 3: Review Results

The pipeline generates:

```
error_correction/rules/
├── triplets.json   # All <query, explanation, rules> triplets
├── clusters.json   # Hierarchical clusters of rules
└── rules.json      # Validated correction rules

vector_sql_db/
├── correct/        # Vector DB of correct queries
└── incorrect/      # Vector DB of incorrect queries

error_correction/pipeline.log  # Detailed logs
```

## Pipeline Stages Explained

### Stage 1-2: Query Classification and Storage

Parses evaluation results and stores queries:
- **Correct queries** → `vector_sql_db/correct/`
- **Incorrect queries** → `vector_sql_db/incorrect/`

Uses CodeBERT embeddings for semantic similarity search.

### Stage 3: Explanation Generation

For each incorrect query, generates explanation:

```
Prompt: "Why is this SQL query wrong? Compare predicted vs gold query."

Example Output:
"The predicted query is missing a JOIN between tables 'users' and 'orders'.
The WHERE clause filters on 'users.id' but doesn't establish the relationship
through ORDER.user_id, causing a Cartesian product."
```

### Stage 4: Rule Generation

Generates correction rules in structured format:

```json
{
  "pattern": "SELECT.*FROM users.*WHERE.*user_id",
  "correction": "Add JOIN clause linking users.id to orders.user_id before WHERE",
  "error_type": "JOIN_ERROR"
}
```

### Stage 5: Rule Validation

Verifies each rule:
1. Pattern must match the incorrect query
2. Regex must be valid
3. Error type must be in allowed classes

### Stage 6: Hierarchical Clustering

Groups similar rules using:
- Query embedding similarity
- Ward linkage clustering
- Dynamic cluster size optimization

### Stage 7: Testing on Correct Queries

**Zero-failure requirement**:
- Samples 15% of correct queries
- Tests if rules incorrectly flag them
- Discards clusters with any false positives

### Stage 8: Save Results

Saves validated rules for production use.

## Output Format

### Triplet Example

```json
{
  "triplet_id": "triplet_a3f8e912_20251018143022",
  "incorrect_query": "SELECT name FROM users WHERE user_id = 5",
  "correct_query": "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.id = 5",
  "explanation": "Missing JOIN between users and orders tables...",
  "rules": [
    {
      "rule_id": "rule_b7c2f034_20251018143023",
      "pattern": "SELECT.*FROM users.*WHERE.*user_id",
      "correction": "Add JOIN with orders table on users.id = orders.user_id",
      "error_type": "JOIN_ERROR"
    }
  ],
  "db_id": "sales",
  "question": "What is the name of the user who made order 5?"
}
```

### Cluster Example

```json
{
  "cluster_id": "cluster_20251018143025_5",
  "size": 5,
  "representative_triplet": { /* triplet object */ },
  "rules": [ /* list of rules */ ]
}
```

## Advanced Usage

### Custom Embedding Model

Change in [config.py](config.py):

```python
SQL_EMBEDDING_MODEL = "Salesforce/codet5-base"  # or other code models
```

### Adjust Clustering Parameters

```python
CLUSTERING_LINKAGE = "average"  # Options: ward, average, complete
MIN_CLUSTER_SIZE = 3
MAX_CLUSTER_SIZE = 15
```

### Add Custom Error Classes

```python
ERROR_CLASSES = [
    "JOIN_ERROR",
    "YOUR_CUSTOM_ERROR",
    # ... other classes
]
```

Then update the rule generation prompt template.

## Troubleshooting

### Issue: "Not enough triplets for clustering"

**Solution**: Lower `MIN_TRIPLETS_FOR_CLUSTERING` or run on more queries.

### Issue: "FAISS index error"

**Solution**: Ensure embedding dimensions match:
```python
EMBEDDING_DIMENSION = 768  # For CodeBERT
```

### Issue: "No clusters created"

**Solution**:
- Check if combine threshold is too high
- Review clustering parameters
- Ensure queries have sufficient diversity

### Issue: "All clusters discarded after testing"

**Solution**:
- Rules may be too broad and matching correct queries
- Review rule patterns in logs
- Adjust `CORRECT_QUERY_TEST_RATIO` or error class definitions

## Performance Considerations

### Memory Usage

- **FAISS Index**: ~4 bytes × embedding_dim × num_queries
- **Embeddings**: Loaded on-demand, cleared after batch processing

### Speed Optimization

1. **Batch Processing**: Embedder processes queries in batches of 32
2. **GPU Acceleration**: Use CUDA-enabled PyTorch and FAISS
3. **Parallel LLM Calls**: Could be added for multiple queries

### Cost Estimation

For 100 incorrect queries with GPT-4:
- Explanations: ~200 tokens/query = 20K tokens
- Rules: ~300 tokens/query = 30K tokens
- **Total**: ~50K tokens ≈ $1.50

## Extending the Pipeline

### Add Custom Rule Transformations

Edit [rule_applicator.py](rule_engine/rule_applicator.py):

```python
def apply_transformation(self, query: str, rule: Rule) -> str:
    # Implement actual SQL transformation
    # Could use SQL parsing libraries or LLM
    pass
```

### Integrate with Production

```python
from error_correction.vector_store import IncorrectQueriesDB
from error_correction.rule_engine import RuleApplicator

# Load saved rules
with open('error_correction/rules/rules.json') as f:
    rules_data = json.load(f)
    rules = [Rule.from_dict(r) for r in rules_data]

# Apply to new query
applicator = RuleApplicator()
matched_rules, corrected = applicator.apply_rules(query, rules)
```

## Logging

Logs are written to:
- **Console**: INFO level
- **File**: `error_correction/pipeline.log` (all levels)

Adjust in [config.py](config.py):
```python
LOG_LEVEL = "DEBUG"  # For verbose output
```

## Citation

If you use this error correction pipeline, please cite:

```bibtex
@software{dail_sql_error_correction,
  title={Error Correction Pipeline for DAIL-SQL},
  author={Your Name},
  year={2025},
  url={https://github.com/your-repo}
}
```

## License

Same as DAIL-SQL base project.

## Contributing

Contributions welcome! Areas for improvement:
- Actual SQL transformation implementation (currently pattern-matching only)
- Multi-modal error detection (schema-aware)
- Active learning for rule refinement
- Integration with execution-based validation

## Contact

For issues and questions, please open a GitHub issue or contact [your email].
