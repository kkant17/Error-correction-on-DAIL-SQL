# Quick Start Guide - Complete Pipeline with deepseek-coder:6.7b

This guide will help you run the entire DAIL-SQL + Error Correction pipeline in just a few simple steps.

## Prerequisites

Before you start, make sure you have:

1. ✅ Python 3.8+ installed
2. ✅ Base DAIL-SQL requirements installed: `pip install -r requirements.txt`
3. ✅ Error correction requirements installed: `pip install -r error_correction/requirements.txt`
4. ✅ Ollama installed and running: Download from https://ollama.ai
5. ✅ Intel Arc GPU with drivers (optional but recommended)

## Understanding the Pipeline Components

### Base DAIL-SQL Model
The original DAIL-SQL pipeline generates SQL queries:
- `data_preprocess.py` - Preprocesses Spider dataset
- `generate_question.py` - Generates questions with few-shot examples
- `ask_llm.py` - Generates SQL predictions using LLM
- `eval/evaluation.py` - Evaluates predictions vs gold queries

### Error Correction Extension
The error correction pipeline analyzes mistakes:
- `error_correction/pipeline.py` - Analyzes errors, generates rules
- `run_full_pipeline.py` - Python wrapper to run both pipelines

## Quick Start Options 🚀

### Option 1: Using run_full_pipeline.py (Recommended - Python)

The main Python script that runs both base DAIL-SQL and error correction:

**Basic usage:**
```bash
# Run with Ollama model (requires Ollama running)
python run_full_pipeline.py --model codellama:7b --max_queries 60

# Skip base evaluation if you already have correct/incorrect JSON files
python run_full_pipeline.py --model codellama:7b --skip_base_eval --max_queries 60

# Run complete pipeline including base DAIL-SQL model generation
python run_full_pipeline.py --model codellama:7b --run_base_model --max_queries 60
```

**What it does:**
1. **Step 1**: Runs `ask_llm.py` (if --run_base_model) → creates baseline eval text file
2. **Step 2**: Runs `eval/evaluation.py` (or skips with --skip_base_eval)
3. **Step 3**: Runs `error_correction/pipeline.py` with the results
4. **Step 4**: Generates consolidated evaluation report

**Parameters:**
- `--model`: LLM model name (e.g., `codellama:7b`, `llama3.1:8b`, `deepseek-coder:6.7b`)
- `--max_queries`: Maximum queries to process (default: all)
- `--skip_base_eval`: Skip evaluation step (use existing vector DBs)
- `--run_base_model`: Run base DAIL-SQL model first (ask_llm.py) - creates baseline eval text file
- `--temperature`: Temperature for LLM (default: 0.0 for base, 0.3 for error correction)

### Option 2: Manual Step-by-Step (For Advanced Users)

If you prefer full control:

```bash
# Step 1: Preprocess data (first time only)
python data_preprocess.py

# Step 2: Generate questions (first time only)
python generate_question.py --data_type spider --split test --k_shot 3 ...

# Step 3: Run base DAIL-SQL model to generate predictions
python ask_llm.py --model codellama:7b --question <dataset_dir> ...

# Step 4: Evaluate predictions and save correct/incorrect JSON
python eval/evaluation.py --gold dataset/spider/dev_gold.sql --pred <predictions_file> \
    --save_correct results/correct_predictions.json \
    --save_incorrect results/incorrect_predictions.json

# Step 5: Run error correction pipeline
python -m error_correction.pipeline \
    --correct results/correct_predictions.json \
    --incorrect results/incorrect_predictions.json \
    --model codellama:7b
```

---

## What the Pipeline Does

```
┌────────────────────────────────────────────┐
│  Step 1: Data Evaluation (Optional)        │
├────────────────────────────────────────────┤
│  • Runs eval/evaluation.py                │
│  • Saves correct_predictions.json         │
│  • Saves incorrect_predictions.json       │
│  • Can be skipped with --skip_base_eval   │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 2: Populate Vector Databases         │
├────────────────────────────────────────────┤
│  • Loads correct queries (CodeBERT)       │
│  • Loads incorrect queries (CodeBERT)     │
│  • Stores in FAISS indexes                │
│  • vector_sql_db/correct/ (213 queries)   │
│  • vector_sql_db/incorrect/ (557 queries) │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 3: Error Correction Pipeline         │
├────────────────────────────────────────────┤
│  • Retrieves similar incorrect queries    │
│  • Generates error explanations (LLM)     │
│  • Generates solutions (LLM)              │
│  • Creates regex correction rules (LLM)   │
│  • Hierarchical clustering (3 levels)     │
│  • Validates rules on correct queries     │
│  • Commits rules passing 95% threshold    │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 4: Save Results                      │
├────────────────────────────────────────────┤
│  • Saves clusters.json                    │
│  • Saves rules.json                       │
│  • Saves triplets.json                    │
│  • Saves metrics.json                     │
│  • Saves accuracy_stats.json              │
│  • Saves transformations.json             │
│  • Generates consolidated eval report     │
└────────────────────────────────────────────┘
```

## Expected Runtime

With **7-8B models** on Ollama:

| Step | Time (60 queries) |
|------|-------------------|
| Data evaluation | ~2-5 minutes |
| Vector DB population | ~1-2 minutes |
| Error correction (explanations + rules) | ~15-30 minutes |
| Clustering & validation | ~5-10 minutes |
| **Total** | ~25-50 minutes |

**Notes:**
- Times vary based on model and hardware
- Vector DBs are reused across runs (use --skip_base_eval)
- Ollama may return HTTP 500 errors under load - restart Ollama if this happens

## Configuration

### Command-line Parameters

Edit parameters when running `run_full_pipeline.py`:

```bash
python run_full_pipeline.py \
  --model codellama:7b \           # Model to use
  --max_queries 60 \                # Number of queries to process
  --skip_base_eval \                # Skip evaluation (use existing DBs)
  --temperature 0.3                 # LLM temperature for rule generation
```

### Pipeline Configuration

Edit `error_correction/config.py` for advanced settings:

- `MIN_TRIPLETS_FOR_CLUSTERING = 20` - Minimum triplets before clustering
- `CLUSTER_COMBINE_THRESHOLD = 0.50` - Similarity threshold for clustering
- `MIN_PASS_RATE = 0.95` - 95% validation pass rate requirement
- `ENABLE_TRANSFORMATION = False` - Enable query transformation (experimental)
- `ENABLE_EXECUTION_VALIDATION = False` - Enable DB execution validation

## Output Files

After completion, you'll have:

### Evaluation Results
```
results/
├── correct_predictions.json                   # Queries that passed evaluation
├── incorrect_predictions.json                 # Queries that failed evaluation
├── eval_{model}.txt                           # Baseline evaluation (if --run_base_model used)
└── eval_error_correction_{model}.txt          # Consolidated evaluation report
```

### Error Correction Artifacts
```
error_correction/results/
├── triplets.json                               # Error triplets (incorrect, correct, explanation, solution, rules)
├── clusters.json                               # Hierarchical clusters of similar errors
├── rules.json                                  # Generated correction rules
├── metrics.json                                # Pipeline execution metrics
├── accuracy_stats.json                         # Validation accuracy statistics
└── transformations.json                        # Query transformations (if enabled)
```

### Vector Databases
```
vector_sql_db/
├── correct/
│   ├── faiss.index                            # FAISS index for correct queries
│   ├── queries.pkl                            # Query metadata
│   └── metadata.json                          # Database info (213 queries)
└── incorrect/
    ├── faiss.index                            # FAISS index for incorrect queries
    ├── queries.pkl                            # Query metadata
    └── metadata.json                          # Database info (557 queries)
```

### Logs
```
error_correction/
└── pipeline.log                                # Detailed execution logs
```

## Viewing Results

### 1. Check Base Model Accuracy

```bash
# Windows
findstr "Final Execution Accuracy" results\eval_deepseek-coder_6.7b.txt

# Linux/Mac
grep "Final Execution Accuracy" results/eval_deepseek-coder_6.7b.txt
```

### 2. View Error Triplets

```bash
# Windows
type error_correction\rules\triplets.json

# Linux/Mac (with pretty printing)
cat error_correction/rules/triplets.json | jq .
```

### 3. Examine Generated Rules

```bash
# Windows
type error_correction\rules\rules.json

# Linux/Mac
cat error_correction/rules/rules.json | jq .
```

### 4. View Pipeline Logs

```bash
# Windows
type error_correction\pipeline.log | more

# Linux/Mac
tail -100 error_correction/pipeline.log
```

## Troubleshooting

### Issue: "Ollama is not running"

**Solution:**
```bash
# Open a new terminal and run:
ollama serve
```

### Issue: "Model not found"

**Solution:** The script will automatically pull the model. If it fails:
```bash
ollama pull deepseek-coder:6.7b
```

### Issue: "Out of memory" during embedding generation

**Solution:** Edit the script to use CPU for embeddings:
```batch
REM Add this before running the pipeline:
set EMBEDDING_DEVICE=cpu
```

### Issue: Script runs but no triplets generated

**Solution:** Check if there are incorrect queries:
```bash
findstr "INCORRECT" results\eval_deepseek-coder_6.7b.txt
```
If none, the model is perfect! Try a harder dataset or increase test size.

### Issue: "Not enough triplets for clustering"

**Solution:** This is normal if only testing with 20 triplets. Options:
1. Increase `MAX_TRIPLETS` in the script (e.g., 50, 100, or remove limit)
2. Accept that rules are generated but not clustered (still useful!)

## Next Steps

### 1. Run with More Triplets

Edit `run_complete_pipeline.bat`:
```batch
set "MAX_TRIPLETS=100"    # or 999999 for all
```

### 2. Test Different Models

```bash
python run_full_pipeline.py --model qwen2.5-coder:7b --max_queries 60
python run_full_pipeline.py --model codellama:13b --max_queries 60
python run_full_pipeline.py --model llama3.1:8b --max_queries 60
```

### 3. Adjust Few-Shot Examples

```batch
set "K_SHOT=5"    # Use 5-shot instead of 3-shot
```

### 4. Use Different Dataset

```batch
set "SPLIT=train"    # Use training set instead of test
```

## Performance Tips

### For Intel Arc GPU Users

1. **Test GPU detection first:**
   ```bash
   python error_correction/test_intel_arc.py
   ```

2. **If embeddings are slow on Arc:**
   ```bash
   set EMBEDDING_DEVICE=cpu
   ```
   (LLM will still use Arc GPU via ipex-llm)

### For Faster Iteration

1. **Skip base model if results exist:**
   - The script will ask if you want to re-run
   - Select "n" to skip to error correction

2. **Test with small dataset first:**
   ```batch
   set "MAX_TRIPLETS=5"    # Very quick test
   ```

3. **Use cached preprocessing:**
   - Preprocessing is only done once
   - Subsequent runs start from Step 2

## Advanced Usage

### Manual Step-by-Step Execution

If you prefer to run each step manually:

```bash
# Step 1: Preprocess (once)
python data_preprocess.py

# Step 2: Generate questions (once per config)
python generate_question.py --data_type spider --split test --k_shot 3 ...

# Step 3: Run base model
python ask_llm.py --model deepseek-coder:6.7b --question <dataset_dir> ...

# Step 4: Run error correction
python error_correction/pipeline.py --eval_results results/eval_model.txt ...
```

See the scripts for exact parameters.

### Testing Intel Arc Compatibility

```bash
python error_correction/test_intel_arc.py
```

This will show:
- ✅ Intel Arc GPU detection status
- ✅ Which device will be used for embeddings
- ✅ All component compatibility

## FAQs

**Q: How long does it take?**
A: First run: ~1 hour. Subsequent runs: ~40 minutes (skips preprocessing).

**Q: Can I stop and resume?**
A: Partially. The base model run can't resume, but if it completes, you can re-run just error correction.

**Q: Do I need Intel Arc GPU?**
A: No! The pipeline works great on CPU too. It's just faster with Intel Arc.

**Q: Can I use GPT-4 instead of Ollama?**
A: Yes! Set your OpenAI API key and run:
```bash
export OPENAI_API_KEY=your_openai_key
python run_full_pipeline.py --model gpt-4 --max_queries 60
```

**Q: Why only 20 triplets by default?**
A: For quick testing. Increase `MAX_TRIPLETS` for production use.

**Q: What if I get errors?**
A: Check `error_correction/pipeline.log` for details and see the Troubleshooting section above.

## Support

- **Detailed docs:** [error_correction/README.md](error_correction/README.md)
- **Intel Arc setup:** [error_correction/INTEL_ARC_SETUP.md](error_correction/INTEL_ARC_SETUP.md)
- **Pre-flight checklist:** [error_correction/CHECKLIST.md](error_correction/CHECKLIST.md)
- **Implementation summary:** [ERROR_CORRECTION_SUMMARY.md](ERROR_CORRECTION_SUMMARY.md)

---

**Ready to go?**

```bash
# Full pipeline from scratch
python run_full_pipeline.py --model codellama:7b --run_base_model --max_queries 60

# Error correction only (predictions already exist)
python run_full_pipeline.py --model codellama:7b --max_queries 60

# Skip evaluation (use existing vector DBs)
python run_full_pipeline.py --model codellama:7b --skip_base_eval
```

Works on Windows, Linux, and Mac! 🚀
