# Error Correction Pipeline - Pre-Flight Checklist

Use this checklist before running the pipeline for the first time.

## ✅ Installation Checklist

### System Requirements
- [ ] Python 3.8+ installed
- [ ] Git installed (for cloning dependencies)
- [ ] At least 8GB RAM available
- [ ] ~5GB disk space for models and data
- [ ] (Optional) NVIDIA GPU with CUDA for faster processing

### Python Dependencies
- [ ] Base DAIL-SQL requirements installed (`pip install -r requirements.txt`)
- [ ] Error correction requirements installed (`pip install -r error_correction/requirements.txt`)
- [ ] Verify installation:
  ```bash
  python -c "import faiss; import transformers; import torch; print('OK')"
  ```

### Ollama Setup (for local models)
- [ ] Ollama installed (download from https://ollama.ai)
- [ ] Ollama service running (`ollama serve`)
- [ ] Model pulled (`ollama pull deepseek-coder:6.7b`)
- [ ] Test connection:
  ```bash
  curl http://localhost:11434/api/tags
  ```

### Directory Structure
- [ ] Run setup script:
  - Linux/Mac: `bash error_correction/setup.sh`
  - Windows: `error_correction\setup.bat`
- [ ] Verify directories created:
  ```
  vector_sql_db/correct/
  vector_sql_db/incorrect/
  error_correction/rules/
  results/
  ```

## ✅ Data Preparation Checklist

### Base Model Predictions
- [ ] DAIL-SQL preprocessing completed (`python data_preprocess.py`)
- [ ] Question generation completed (`python generate_question.py ...`)
- [ ] Base model run completed (`python ask_llm.py ...`)
- [ ] Files exist:
  - [ ] `dataset/process/.../questions.json`
  - [ ] `dataset/process/.../RESULTS_MODEL-{model}.txt`
  - [ ] `results/eval_{model}.txt`

### File Verification
- [ ] Questions file is valid JSON:
  ```bash
  python -c "import json; json.load(open('path/to/questions.json'))"
  ```
- [ ] Predictions file exists and is not empty
- [ ] Evaluation results file contains "CORRECT" and "INCORRECT" entries

## ✅ Configuration Checklist

### Model Settings
- [ ] Model name configured correctly (e.g., `deepseek-coder:6.7b` or `gpt-4`)
- [ ] API key available (for OpenAI) or Ollama URL configured
- [ ] Temperature set appropriately (0.3 recommended for rule generation)

### Pipeline Parameters
Review [error_correction/config.py](config.py):

- [ ] `MIN_TRIPLETS_FOR_CLUSTERING = 15` (adjust for testing)
- [ ] `CLUSTER_COMBINE_THRESHOLD = 0.90` (90%)
- [ ] `CORRECT_QUERY_TEST_RATIO = 0.15` (15%)
- [ ] `SQL_EMBEDDING_MODEL` matches your preference
- [ ] `ERROR_CLASSES` covers your use cases

### Resource Limits
- [ ] Set `--max_triplets` for initial testing (e.g., 10)
- [ ] Ensure sufficient disk space for vector databases
- [ ] Check available RAM (embeddings can use 2-4GB)

## ✅ Pre-Run Verification

### Test Components Individually

1. **Test Embedder**:
   ```python
   from error_correction.vector_store import SQLEmbedder
   embedder = SQLEmbedder()
   emb = embedder.embed_query("SELECT * FROM users")
   print(f"Embedding shape: {emb.shape}")  # Should be (768,)
   ```

2. **Test Vector DB**:
   ```python
   from error_correction.vector_store import VectorDatabase
   import numpy as np
   db = VectorDatabase("test_db")
   emb = np.random.rand(768)
   db.add_query("SELECT test", emb)
   print(f"DB size: {db.size()}")  # Should be 1
   ```

3. **Test LLM Connection**:
   ```python
   from llm.chatgpt import init_chatgpt, ask_llm
   init_chatgpt("ollama", "", "deepseek-coder:6.7b", "http://localhost:11434/v1")
   response = ask_llm("deepseek-coder:6.7b", ["Say 'OK'"], 0.0, 1)
   print(response)
   ```

### Dry Run
- [ ] Run with `--max_triplets 1` to test full pipeline:
  ```bash
  python error_correction/pipeline.py \
    --max_triplets 1 \
    --eval_results results/eval_model.txt \
    --predictions_file .../RESULTS_MODEL-model.txt \
    --questions_file .../questions.json \
    --model your-model \
    --openai_api_key your-key
  ```
- [ ] Check logs: `error_correction/pipeline.log`
- [ ] Verify output files created in `error_correction/rules/`

## ✅ Monitoring Checklist

### During Execution
- [ ] Monitor logs in real-time:
  ```bash
  tail -f error_correction/pipeline.log
  ```
- [ ] Check GPU utilization (if applicable):
  ```bash
  nvidia-smi
  ```
- [ ] Monitor disk space:
  ```bash
  df -h
  ```

### Expected Output
- [ ] Pipeline stages complete in order (1-2, 3, 4, 5, 6, 7, 8)
- [ ] Triplets generated successfully
- [ ] Rules validated
- [ ] Clusters created (if enough triplets)
- [ ] Final statistics displayed

## ✅ Post-Run Verification

### Output Files
- [ ] `error_correction/rules/triplets.json` exists and is valid JSON
- [ ] `error_correction/rules/clusters.json` exists (if clustering ran)
- [ ] `error_correction/rules/rules.json` contains validated rules
- [ ] Vector databases created:
  - [ ] `vector_sql_db/correct/faiss.index`
  - [ ] `vector_sql_db/incorrect/faiss.index`

### Quality Checks
- [ ] Review sample triplets:
  ```python
  import json
  triplets = json.load(open('error_correction/rules/triplets.json'))
  print(json.dumps(triplets[0], indent=2))
  ```
- [ ] Verify rules make sense:
  ```python
  rules = json.load(open('error_correction/rules/rules.json'))
  for rule in rules[:5]:
      print(f"Pattern: {rule['pattern']}")
      print(f"Type: {rule['error_type']}\n")
  ```
- [ ] Check cluster statistics:
  ```python
  clusters = json.load(open('error_correction/rules/clusters.json'))
  sizes = [c['size'] for c in clusters]
  print(f"Clusters: {len(clusters)}, Avg size: {sum(sizes)/len(sizes):.1f}")
  ```

## ✅ Troubleshooting Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Import errors | `pip install -r error_correction/requirements.txt` |
| Ollama connection failed | `ollama serve` in another terminal |
| Out of memory | Reduce `--max_triplets`, close other apps |
| CUDA out of memory | Use CPU: `export CUDA_VISIBLE_DEVICES=""` |
| JSON decode error | Check input file encoding (should be UTF-8) |
| No triplets generated | Check if eval file has "INCORRECT" entries |
| No clusters created | Lower `MIN_TRIPLETS_FOR_CLUSTERING` |
| All clusters discarded | Rules too broad, review `ERROR_CLASSES` |

## ✅ Production Readiness Checklist

Before deploying to production:

- [ ] Test with full dataset (remove `--max_triplets`)
- [ ] Validate rule quality manually (sample 10-20 rules)
- [ ] Benchmark performance (time, memory, LLM costs)
- [ ] Set up monitoring/alerting for pipeline failures
- [ ] Document any custom configuration changes
- [ ] Create backup of vector databases
- [ ] Version control for generated rules
- [ ] Establish rule update/refresh schedule

## 📝 Notes

Use this space for run-specific notes:

```
Date: _______________
Model: _______________
Dataset: _______________
Parameters: _______________

Results:
- Triplets: _____
- Clusters: _____
- Rules: _____

Issues encountered:
1.
2.

Observations:
1.
2.
```

---

**Ready to run?** If all checkboxes are ✅, proceed with:

```bash
# Linux/Mac
bash error_correction/example_run_ollama.sh

# Windows
error_correction\example_run_ollama.bat
```

or manually with custom parameters:

```bash
python error_correction/pipeline.py \
  --eval_results results/eval_model.txt \
  --predictions_file .../RESULTS_MODEL-model.txt \
  --questions_file .../questions.json \
  --model deepseek-coder:6.7b \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1
```
