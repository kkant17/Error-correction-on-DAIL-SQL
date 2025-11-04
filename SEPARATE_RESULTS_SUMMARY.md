# Running Model With Separate Results - Summary

## What You Asked For

You wanted to run the model twice and store results separately:
1. **Run #1**: Without error correction
2. **Run #2**: With error correction

So you can compare them.

## What I Created

### 1. Comparison Pipeline Script ⭐

**File:** `run_comparison_pipeline.bat`

**What it does:**
- Runs the base model once
- Stores results in two separate directories:
  - `results/base_only/` - Clean baseline
  - `results/with_error_correction/` - With analysis and rules
- Automatically generates a comparison report

**Run it:**
```batch
run_comparison_pipeline.bat
```

### 2. Comparison Report Script

**File:** `compare_results.py`

**What it does:**
- Compares the two runs
- Shows error type distribution
- Displays sample rules and triplets
- Generates detailed analysis report

**Run it after pipeline completes:**
```batch
python compare_results.py
```

### 3. Comprehensive Guide

**File:** `COMPARISON_GUIDE.md`

**Contains:**
- Detailed explanation of the comparison workflow
- File organization structure
- Use cases and examples
- Troubleshooting tips
- Future roadmap (when transformation is implemented)

## File Structure After Running

```
results/
├── base_only/                                    ← RUN #1
│   └── eval_deepseek-coder_6.7b.txt            Results without error correction
│
└── with_error_correction/                       ← RUN #2
    ├── eval_deepseek-coder_6.7b.txt            Same results (for now)
    └── rules/                                   ← Error correction analysis
        ├── triplets.json                        Error explanations
        ├── clusters.json                        Grouped errors
        └── rules.json                           Correction rules

dataset/process/.../
├── RESULTS_MODEL-deepseek-coder_6.7b_base_only.txt         ← RUN #1 predictions
└── RESULTS_MODEL-deepseek-coder_6.7b_with_correction.txt   ← RUN #2 predictions
```

## Important: Current vs Future State

### Current State (What You'll Get Now)

**Run #1 and Run #2 have the SAME accuracy** because:
- Error correction generates rules but doesn't apply them yet
- The predictions are identical
- SQL transformation is not implemented

**What you GET:**
- ✅ Error pattern analysis
- ✅ Correction rules for each error type
- ✅ LLM explanations of what went wrong
- ✅ Clustered similar errors
- ✅ Insights into model weaknesses

**Use this for:**
- Understanding what errors your model makes
- Identifying patterns (e.g., "33% are JOIN errors")
- Manual query correction
- Improving few-shot prompts
- Planning better training data

### Future State (After Transformation Implementation)

**Run #2 will have HIGHER accuracy** because:
- Rules will be applied to fix queries automatically
- Predictions will be corrected
- You'll see actual performance improvement

**What you'll GET:**
- ✅ Everything from current state, PLUS
- ✅ Actually corrected queries
- ✅ Improved accuracy (e.g., 68% → 75%)
- ✅ Real performance comparison

## Quick Start

### Step 1: Run the Comparison Pipeline

```batch
run_comparison_pipeline.bat
```

This will:
1. Check prerequisites (Ollama, model)
2. Preprocess data (if needed)
3. Run base model → stores in `base_only/`
4. Run error correction → analyzes and stores in `with_error_correction/`
5. Show comparison summary

**Expected time:** ~1 hour for Spider test set

### Step 2: View the Comparison

```batch
python compare_results.py
```

Output example:
```
======================================================================
ACCURACY COMPARISON
======================================================================

Base Model (No Error Correction):
  - Accuracy: 68.50%
  - Correct: 685/1000
  - Incorrect: 315

With Error Correction Analysis:
  - Accuracy: 68.50%  (same for now - rules not applied yet)
  - Correct: 685/1000
  - Incorrect: 315

======================================================================
ERROR CORRECTION ANALYSIS
======================================================================

Triplets Analyzed: 20
Rules Generated: 18

Error Type Distribution:
  - JOIN_ERROR: 6 (33.3%)
  - AGGREGATION_ERROR: 4 (22.2%)
  - FILTER_ERROR: 3 (16.7%)
  ...
```

### Step 3: Analyze the Results

**View error triplets:**
```batch
type results\with_error_correction\rules\triplets.json
```

Each triplet shows:
- What the incorrect query was
- What the correct query should be
- LLM explanation of the error
- Correction rule(s) to fix it

**View correction rules:**
```batch
type results\with_error_correction\rules\rules.json
```

Each rule contains:
- Regex pattern to identify the error
- Correction description
- Error type classification

## Example Use Cases

### Use Case 1: Understand Model Weaknesses

```batch
REM Run comparison
run_comparison_pipeline.bat

REM View report
python compare_results.py
```

**Output shows:**
```
Error Type Distribution:
  - JOIN_ERROR: 33%    ← Model struggles with multi-table queries!
  - AGGREGATION_ERROR: 22%
  ...
```

**Action:** Add more JOIN examples to your few-shot prompts

### Use Case 2: Manual Query Correction

```python
# Load rules
import json
rules = json.load(open('results/with_error_correction/rules/rules.json'))

# Find JOIN errors
join_rules = [r for r in rules if r['error_type'] == 'JOIN_ERROR']

# Review and apply manually
for rule in join_rules:
    print(f"Pattern: {rule['pattern']}")
    print(f"Fix: {rule['correction']}")
```

### Use Case 3: Compare Different Configurations

```batch
REM Try 3-shot
set K_SHOT=3
run_comparison_pipeline.bat
move results results_3shot

REM Try 5-shot
set K_SHOT=5
run_comparison_pipeline.bat
move results results_5shot

REM Compare which has fewer errors
```

## Configuration

Edit `run_comparison_pipeline.bat` to customize:

```batch
REM Line 14: Change model
set "MODEL=qwen2.5-coder:7b"

REM Line 30: Analyze more errors
set "MAX_TRIPLETS=100"

REM Line 24: Use different few-shot count
set "K_SHOT=5"

REM Line 23: Use different dataset
set "SPLIT=train"
```

## Files You Care About

### For Analysis

1. **`results/with_error_correction/rules/triplets.json`**
   - Most useful for understanding errors
   - Shows LLM explanations
   - Includes question, db, wrong/right queries

2. **`results/with_error_correction/rules/rules.json`**
   - Correction rules to apply
   - Patterns + transformations
   - Error type classifications

3. **`compare_results.py` output**
   - Quick overview
   - Error distribution
   - Sample rules and triplets

### For Comparison

1. **`results/base_only/eval_*.txt`** - Baseline accuracy
2. **`results/with_error_correction/eval_*.txt`** - With analysis (same accuracy for now)

## Troubleshooting

### "Both runs have same accuracy"

✅ **This is expected!** Error correction generates rules but doesn't apply them yet.

**Value is in the analysis, not accuracy improvement (for now).**

### "Not enough triplets generated"

Your model is too good! Options:
- Increase `MAX_TRIPLETS` to 100+
- Use harder dataset
- Try weaker model to generate more errors for analysis

### "Want to apply corrections automatically"

This requires implementing SQL transformation in `rule_applicator.py`.

See [COMPARISON_GUIDE.md](COMPARISON_GUIDE.md) "Contributing: Implementing Transformation" section.

## Next Steps

1. **Run it:**
   ```batch
   run_comparison_pipeline.bat
   ```

2. **Review results:**
   ```batch
   python compare_results.py
   ```

3. **Analyze errors:**
   - Open `triplets.json` to see detailed explanations
   - Look at error type distribution
   - Identify patterns

4. **Take action:**
   - Improve few-shot prompts based on error types
   - Manually correct some queries using rules
   - Plan SQL transformation implementation

5. **Iterate:**
   - Try different configurations
   - Compare results
   - Track improvements

## Summary

| What | File | Purpose |
|------|------|---------|
| **Run pipeline** | `run_comparison_pipeline.bat` | Creates separate results |
| **Compare** | `compare_results.py` | Analyzes differences |
| **Understand** | `COMPARISON_GUIDE.md` | Complete guide |
| **Results #1** | `results/base_only/` | Baseline (no correction) |
| **Results #2** | `results/with_error_correction/` | With analysis |

**Bottom line:** The comparison pipeline is ready to use! It will give you valuable insights into your model's errors, even though the corrections aren't applied yet.

Start with:
```batch
run_comparison_pipeline.bat
```

Then analyze:
```batch
python compare_results.py
```

Happy error hunting! 🔍
