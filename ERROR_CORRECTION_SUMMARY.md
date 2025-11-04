# Error Correction Pipeline - Implementation Summary

## Overview

A complete, modular error correction pipeline has been implemented for DAIL-SQL that automatically learns from SQL generation errors and creates reusable correction rules through LLM-generated explanations and hierarchical clustering.

## Implementation Status: ✅ COMPLETE

All planned components have been successfully implemented and are ready for use.

## File Structure

```
error_correction/
├── __init__.py                      # Package initialization
├── config.py                        # Central configuration (A=15, threshold=90%, etc.)
├── pipeline.py                      # Main orchestrator script ⭐
├── requirements.txt                 # Additional dependencies
├── README.md                        # Comprehensive documentation
├── setup.sh                         # Setup script (Linux/Mac)
├── setup.bat                        # Setup script (Windows)
├── example_run_ollama.sh           # Example with Ollama (Linux/Mac)
├── example_run_ollama.bat          # Example with Ollama (Windows)
│
├── vector_store/                    # Vector database module
│   ├── __init__.py
│   ├── embedder.py                 # SQL-specific embeddings (CodeBERT)
│   └── vector_db.py                # FAISS vector database manager
│
├── rule_engine/                     # Rule generation & application
│   ├── __init__.py
│   ├── rule_schema.py              # Data structures (Rule, RuleTriplet, RuleCluster)
│   ├── rule_generator.py           # LLM-based rule generation
│   └── rule_applicator.py          # Regex pattern matching & verification
│
└── clustering/                      # Hierarchical clustering
    ├── __init__.py
    └── hierarchical_cluster.py     # Ward linkage clustering & validation

Generated directories (created at runtime):
vector_sql_db/
├── correct/                         # FAISS index for correct queries
└── incorrect/                       # FAISS index for incorrect queries

error_correction/rules/              # Saved results
├── triplets.json                    # <query, explanation, rules> triplets
├── clusters.json                    # Hierarchical clusters
└── rules.json                       # Validated correction rules
```

## Key Features Implemented

### ✅ Step 1-2: Query Classification & Vector Storage
- Parses evaluation results to identify correct/incorrect queries
- Stores queries in separate FAISS vector databases
- Uses CodeBERT embeddings for semantic similarity
- Metadata includes db_id, question, gold SQL

### ✅ Step 3: LLM-based Explanation Generation
- Prompts LLM to compare predicted vs gold queries
- Generates concise 2-3 sentence explanations
- Error handling for LLM API failures

### ✅ Step 4: Rule Generation & Validation
- Generates rules in structured format:
  - `pattern`: Regex matching error signatures
  - `correction`: Transformation description
  - `error_type`: Classification (11 predefined classes)
- Validates regex patterns
- Verifies rules match the incorrect queries they were generated for

### ✅ Step 5: Triplet Collection
- Collects <query, explanation, rules> triplets
- Supports multiple rules per triplet
- Minimum A=15 triplets before clustering

### ✅ Step 6: Hierarchical Clustering
- Ward linkage with euclidean distance
- Dynamic cluster size optimization (2-10 rules per cluster)
- Combines threshold: 90% of queries must be combined
- Representative selection for each cluster
- Discards clusters failing validation

### ✅ Step 7: Validation on Correct Queries
- Samples 15% of correct queries
- Zero-failure tolerance: any false positive → discard cluster
- Tests if rules incorrectly flag correct queries

### ✅ Step 8: Save Results
- JSON format for all outputs
- Persistent vector databases
- Detailed logging

## Technologies Used

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Vector DB | FAISS | Lightweight, fast, no server needed |
| Embeddings | CodeBERT (microsoft/codebert-base) | SQL/code-specific embeddings |
| Clustering | scipy.cluster.hierarchy | Robust hierarchical clustering |
| LLM API | OpenAI-compatible | Works with GPT-4, Ollama, etc. |
| Rule Matching | Python regex | Efficient pattern matching |

## Configuration Parameters

All configurable in [error_correction/config.py](error_correction/config.py):

```python
MIN_TRIPLETS_FOR_CLUSTERING = 15      # A parameter
CLUSTER_COMBINE_THRESHOLD = 0.90      # 90% threshold
CORRECT_QUERY_TEST_RATIO = 0.15       # Sample 15% for testing
ZERO_FAILURE_TOLERANCE = True         # Zero-failure requirement

SQL_EMBEDDING_MODEL = "microsoft/codebert-base"
EMBEDDING_DIMENSION = 768
MAX_SEQUENCE_LENGTH = 512

ERROR_CLASSES = [
    "JOIN_ERROR", "AGGREGATION_ERROR", "FILTER_ERROR",
    "COLUMN_SELECTION", "SUBQUERY_ERROR", "ORDERING_ERROR",
    "DISTINCT_ERROR", "TABLE_REFERENCE", "OPERATOR_ERROR",
    "NULL_HANDLING", "OTHER"
]
```

## Quick Start

### Installation

```bash
# Linux/Mac
bash error_correction/setup.sh

# Windows
error_correction\setup.bat
```

### Usage with Ollama (Local Open-Source Models)

```bash
# Linux/Mac
bash error_correction/example_run_ollama.sh

# Windows
error_correction\example_run_ollama.bat
```

### Manual Usage

```bash
# Step 1: Run base DAIL-SQL
python ask_llm.py \
  --model deepseek-coder:6.7b \
  --question ./dataset/process/SPIDER-TEST_... \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1

# Step 2: Run error correction pipeline
python error_correction/pipeline.py \
  --eval_results results/eval_deepseek-coder_6.7b.txt \
  --predictions_file ./dataset/.../RESULTS_MODEL-deepseek-coder_6.7b.txt \
  --questions_file ./dataset/.../questions.json \
  --model deepseek-coder:6.7b \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1
```

## Output Format

### Triplet Example
```json
{
  "triplet_id": "triplet_a3f8e912_...",
  "incorrect_query": "SELECT name FROM users WHERE user_id = 5",
  "correct_query": "SELECT u.name FROM users u JOIN orders o ...",
  "explanation": "Missing JOIN between users and orders tables...",
  "rules": [
    {
      "rule_id": "rule_b7c2f034_...",
      "pattern": "SELECT.*FROM users.*WHERE.*user_id",
      "correction": "Add JOIN with orders table...",
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
  "cluster_id": "cluster_20251018...",
  "size": 5,
  "representative_triplet": { /* ... */ },
  "rules": [ /* list of 5 rules */ ]
}
```

## Testing Recommendations

### Phase 1: Small-Scale Testing (Recommended First)
```bash
# Test with 10 triplets using Ollama
python error_correction/pipeline.py \
  --max_triplets 10 \
  --model deepseek-coder:6.7b \
  --openai_api_base http://localhost:11434/v1 \
  # ... other args
```

### Phase 2: Medium-Scale Testing
```bash
# Test with 50 triplets
python error_correction/pipeline.py \
  --max_triplets 50 \
  # ... other args
```

### Phase 3: Full Pipeline
```bash
# Process all incorrect queries
python error_correction/pipeline.py \
  # ... other args (no --max_triplets)
```

## Recommended Ollama Models

For SQL error correction tasks:

1. **deepseek-coder:6.7b** ⭐ (Best for code/SQL)
   ```bash
   ollama pull deepseek-coder:6.7b
   ```

2. **codellama:7b** (Good for code tasks)
   ```bash
   ollama pull codellama:7b
   ```

3. **qwen2.5-coder:7b** (Strong code understanding)
   ```bash
   ollama pull qwen2.5-coder:7b
   ```

4. **mistral:7b** (General purpose, good fallback)
   ```bash
   ollama pull mistral:7b
   ```

## Performance Estimates

### Computational Cost
- **Vector DB Storage**: ~4MB per 1000 queries (768-dim embeddings)
- **Clustering**: ~10-30 seconds for 100 triplets
- **Embedding Generation**: ~1-5 queries/second (GPU), ~0.2 queries/second (CPU)

### LLM API Costs (with local Ollama)
- **Free!** Running locally, no API costs
- Speed depends on your GPU (RTX 3060: ~10-20 tokens/sec)

### LLM API Costs (with GPT-4)
- **Explanation**: ~200 tokens/query
- **Rule Generation**: ~300 tokens/query
- **100 queries**: ~50K tokens ≈ $1.50

## Known Limitations & Future Work

### Current Limitations
1. ⚠️ **Rule Transformation**: Pattern matching only - no actual SQL transformation implemented yet
2. ⚠️ **Rule Validation**: Regex-based, doesn't execute queries to verify corrections
3. ⚠️ **Single Query Focus**: Doesn't handle cross-query pattern learning

### Future Enhancements
- [ ] Implement actual SQL transformation using AST manipulation or LLM
- [ ] Add execution-based rule validation
- [ ] Support for multi-query pattern learning
- [ ] Active learning for rule refinement
- [ ] Integration with schema-aware error detection
- [ ] Rule versioning and A/B testing

## Troubleshooting

### "Not enough triplets for clustering"
**Solution**: Lower `MIN_TRIPLETS_FOR_CLUSTERING` in config.py or process more queries

### "No clusters created"
**Solution**: Check combine threshold, ensure query diversity, review clustering parameters

### "All clusters discarded after testing"
**Solution**: Rules may be too broad, review patterns in logs

### "FAISS index error"
**Solution**: Ensure `EMBEDDING_DIMENSION = 768` matches CodeBERT

### Ollama connection errors
**Solution**:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

## Documentation

- **Main README**: [error_correction/README.md](error_correction/README.md)
- **Configuration**: [error_correction/config.py](error_correction/config.py)
- **Pipeline Logs**: `error_correction/pipeline.log`

## Contributing

Areas for contribution:
1. Implement SQL transformation logic in `rule_applicator.py`
2. Add execution-based validation
3. Support for additional embedding models
4. Performance optimizations
5. Extended error class taxonomy

## License

Same as DAIL-SQL base project.

## Author

Implemented as part of DAIL-SQL error correction enhancement.

---

**Status**: ✅ Ready for testing and deployment
**Last Updated**: 2025-10-18
