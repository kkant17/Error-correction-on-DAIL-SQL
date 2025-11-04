# Quick Start Guide - Complete Pipeline with deepseek-coder:6.7b

This guide will help you run the entire DAIL-SQL + Error Correction pipeline in just a few simple steps.

## Prerequisites

Before you start, make sure you have:

1. ✅ Python 3.8+ installed
2. ✅ Base DAIL-SQL requirements installed: `pip install -r requirements.txt`
3. ✅ Error correction requirements installed: `pip install -r error_correction/requirements.txt`
4. ✅ Ollama installed and running: Download from https://ollama.ai
5. ✅ Intel Arc GPU with drivers (optional but recommended)

## Two Options Available 🚀

### Option 1: Complete Pipeline (All-in-One)

Runs everything sequentially:

**Windows:**
```batch
run_complete_pipeline.bat
```

**Linux/Mac:**
```bash
chmod +x run_complete_pipeline.sh
./run_complete_pipeline.sh
```

### Option 2: Comparison Pipeline (Recommended for Analysis)

Runs base model and error correction separately with organized results:

**Windows:**
```batch
run_comparison_pipeline.bat
```

**Benefits:**
- Results stored separately for easy comparison
- Run #1: Base model only (no error correction)
- Run #2: Error correction analysis
- Automatic comparison report

**After running:**
```batch
python compare_results.py
```

See [COMPARISON_GUIDE.md](COMPARISON_GUIDE.md) for details.

---

## What the Scripts Do

### Complete Pipeline (run_complete_pipeline.bat)

The all-in-one script will automatically:
1. ✅ Check if Ollama is running
2. ✅ Pull deepseek-coder:6.7b if needed
3. ✅ Preprocess data (if needed)
4. ✅ Generate questions
5. ✅ Run base DAIL-SQL model
6. ✅ Run error correction pipeline
7. ✅ Display results and statistics

## What the Script Does

```
┌────────────────────────────────────────────┐
│  Step 0: Prerequisites Check               │
├────────────────────────────────────────────┤
│  • Checks if Ollama is running            │
│  • Pulls deepseek-coder:6.7b if needed    │
│  • Optional: Tests Intel Arc GPU          │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 1: Data Preprocessing                │
├────────────────────────────────────────────┤
│  • Runs data_preprocess.py                │
│  • Generates questions with 3-shot        │
│  • Creates dataset directory              │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 2: Run Base DAIL-SQL Model           │
├────────────────────────────────────────────┤
│  • Runs ask_llm.py with deepseek-coder    │
│  • Generates SQL queries                  │
│  • Evaluates queries in real-time        │
│  • Saves results and accuracy             │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 3: Run Error Correction Pipeline     │
├────────────────────────────────────────────┤
│  • Parses evaluation results              │
│  • Stores queries in vector database      │
│  • Generates error explanations (LLM)     │
│  • Creates correction rules (LLM)         │
│  • Clusters similar rules                 │
│  • Tests on correct queries               │
│  • Saves validated rules                  │
└────────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────────┐
│  Step 4: Display Results                   │
├────────────────────────────────────────────┤
│  • Shows base model accuracy              │
│  • Shows error correction statistics      │
│  • Lists output files                     │
│  • Provides next steps                    │
└────────────────────────────────────────────┘
```

## Expected Runtime

With **deepseek-coder:6.7b** on Intel Arc GPU:

| Step | Time (Spider test ~1000 queries) |
|------|-----------------------------------|
| Data preprocessing | ~2-5 minutes (first time only) |
| Base model (SQL generation) | ~30-60 minutes |
| Error correction (20 triplets) | ~10-15 minutes |
| **Total (first run)** | ~45-80 minutes |

**Note:** Subsequent runs are much faster since data preprocessing is skipped!

## Configuration

The script is pre-configured with sensible defaults, but you can edit `run_complete_pipeline.bat` (or `.sh`) to customize:

```batch
REM Edit these at the top of the script:
set "MODEL=deepseek-coder:6.7b"     # Change model if desired
set "MAX_TRIPLETS=20"                # Increase for more rules (20 is good for testing)
set "K_SHOT=3"                       # Number of examples (1, 3, or 5)
set "TEMPERATURE=0.3"                # LLM temperature for rule generation
```

## Output Files

After completion, you'll have:

```
dataset/process/SPIDER-TEST.../
├── questions.json                              # Generated questions
└── RESULTS_MODEL-deepseek-coder_6.7b.txt      # Predicted queries

results/
└── eval_deepseek-coder_6.7b.txt               # Evaluation results + accuracy

error_correction/rules/
├── triplets.json                               # <query, explanation, rules>
├── clusters.json                               # Clustered similar errors
└── rules.json                                  # Validated correction rules

vector_sql_db/
├── correct/                                    # FAISS index for correct queries
└── incorrect/                                  # FAISS index for incorrect queries

error_correction/
└── pipeline.log                                # Detailed logs
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

```batch
set "MODEL=qwen2.5-coder:7b"
# or
set "MODEL=codellama:13b"
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
A: Yes! Edit the script:
```batch
set "MODEL=gpt-4"
set "OLLAMA_API_KEY=your_openai_key"
set "OLLAMA_BASE_URL="
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

**Ready to go?** Just run `run_complete_pipeline.bat` and let it do the work! 🚀
