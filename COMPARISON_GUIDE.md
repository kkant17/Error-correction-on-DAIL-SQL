# Comparison Guide: Base Model vs Error Correction

This guide explains how to run the base model twice - once without error correction and once with error correction analysis - and compare the results.

## Understanding the Current Pipeline

**Important Note:** The current error correction pipeline:
- ✅ **Analyzes errors** and generates correction rules
- ✅ **Identifies patterns** in incorrect queries
- ✅ **Provides explanations** for why queries are wrong
- ⚠️ **Does NOT yet apply corrections** to fix queries automatically

This means both runs will have the **same accuracy** for now. The value is in the **analysis and rules** generated, which you can use to:
1. Understand what types of errors your model makes
2. Get correction rules to manually review or apply
3. Prepare for future automated correction (when transformation is implemented)

## Quick Start

### Run the Comparison Pipeline

```batch
run_comparison_pipeline.bat
```

This single script will:
1. **Run #1**: Base model without error correction
2. **Run #2**: Same predictions with error correction analysis
3. Store results separately for comparison
4. Generate a comparison report

### View the Comparison Report

```batch
python compare_results.py
```

## File Organization

After running the comparison pipeline, your results will be organized like this:

```
results/
├── base_only/                                    # Run #1: No error correction
│   └── eval_deepseek-coder_6.7b.txt            # Evaluation results
│
└── with_error_correction/                       # Run #2: With error correction
    ├── eval_deepseek-coder_6.7b.txt            # Same evaluation
    └── rules/                                   # Error correction artifacts
        ├── triplets.json                        # <query, explanation, rules>
        ├── clusters.json                        # Grouped similar errors
        └── rules.json                           # Validated correction rules

dataset/process/.../
├── RESULTS_MODEL-deepseek-coder_6.7b_base_only.txt         # Run #1 predictions
└── RESULTS_MODEL-deepseek-coder_6.7b_with_correction.txt   # Run #2 predictions (same for now)
```

## What You Get

### Run #1: Base Model Only

- Pure baseline performance
- No error analysis
- Clean results for comparison

**Output:**
- Predictions file
- Evaluation with accuracy
- No additional analysis

### Run #2: With Error Correction

- Same predictions (for now)
- Detailed error analysis
- Correction rules generated

**Output:**
- Predictions file (identical to Run #1 currently)
- Evaluation (same accuracy for now)
- **Error Triplets**: `<query, explanation, rules>` for each error
- **Rules**: Regex patterns + corrections for each error type
- **Clusters**: Grouped similar error patterns

## Comparison Report Example

```
======================================================================
ERROR CORRECTION PIPELINE - COMPARISON REPORT
======================================================================

======================================================================
ACCURACY COMPARISON
======================================================================

Base Model (No Error Correction):
  - Accuracy: 68.50%
  - Correct: 685/1000
  - Incorrect: 315

With Error Correction Analysis:
  - Accuracy: 68.50%
  - Correct: 685/1000
  - Incorrect: 315

NOTE: Accuracy is the same because error correction currently
      generates rules but does not apply them. The predictions
      are identical in both runs.

      The error correction pipeline provides:
      - Analysis of error patterns
      - Correction rules for future use
      - Insights into model weaknesses

======================================================================
ERROR CORRECTION ANALYSIS
======================================================================

Triplets Analyzed: 20
Rules Generated: 18

Error Type Distribution:
  - JOIN_ERROR: 6 (33.3%)
  - AGGREGATION_ERROR: 4 (22.2%)
  - FILTER_ERROR: 3 (16.7%)
  - COLUMN_SELECTION: 3 (16.7%)
  - SUBQUERY_ERROR: 2 (11.1%)

======================================================================
SAMPLE CORRECTION RULES
======================================================================

Rule 1:
  Type: JOIN_ERROR
  Pattern: SELECT.*FROM\s+(\w+)\s+WHERE.*\1\.(\w+)\s*=\s*\d+
  Correction: Add JOIN clause to link tables properly before filtering...

Rule 2:
  Type: AGGREGATION_ERROR
  Pattern: SELECT\s+COUNT\(\*\).*GROUP BY.*HAVING.*
  Correction: Replace HAVING with WHERE for non-aggregated conditions...
```

## Use Cases

### 1. Error Pattern Analysis

**Goal:** Understand what types of errors your model makes

**Steps:**
1. Run comparison pipeline
2. Review error type distribution in report
3. Examine sample triplets for each error type

**Example Insights:**
```
- 33% JOIN errors → Model struggles with multi-table queries
- 22% AGGREGATION errors → Confusion with GROUP BY/HAVING
- 17% FILTER errors → WHERE clause conditions are problematic
```

### 2. Model Weakness Identification

**Goal:** Find specific areas where model needs improvement

**Steps:**
1. Open `results/with_error_correction/rules/triplets.json`
2. Read LLM explanations for each error
3. Group by database or question type

**Example:**
```json
{
  "db_id": "concert_singer",
  "question": "What are the names of singers who participated in concerts?",
  "explanation": "Missing JOIN between singer and concert tables...",
  "error_type": "JOIN_ERROR"
}
```

**Insight:** Model needs more JOIN examples in few-shot prompts

### 3. Manual Query Correction

**Goal:** Use rules to manually fix some queries

**Steps:**
1. Review rules in `rules.json`
2. Find queries matching patterns
3. Apply corrections manually
4. Test improved accuracy

**Example:**
```json
{
  "pattern": "SELECT name FROM users WHERE user_id = \\d+",
  "correction": "Add JOIN between users and referenced table",
  "error_type": "JOIN_ERROR"
}
```

### 4. Prompt Engineering

**Goal:** Improve base model by updating prompts

**Steps:**
1. Identify most common error types
2. Add few-shot examples targeting those errors
3. Re-run base model
4. Compare new results

## Advanced Workflow

### Step 1: Run Multiple Experiments

```batch
REM Experiment 1: 3-shot
set "K_SHOT=3"
run_comparison_pipeline.bat

REM Move results
move results results_3shot

REM Experiment 2: 5-shot
set "K_SHOT=5"
run_comparison_pipeline.bat

REM Move results
move results results_5shot
```

### Step 2: Compare Experiments

```python
# compare_experiments.py
import json

exp1_rules = json.load(open('results_3shot/with_error_correction/rules/rules.json'))
exp2_rules = json.load(open('results_5shot/with_error_correction/rules/rules.json'))

print(f"3-shot errors: {len(exp1_rules)}")
print(f"5-shot errors: {len(exp2_rules)}")
print(f"Improvement: {len(exp1_rules) - len(exp2_rules)} fewer errors")
```

### Step 3: Analyze Trends

Look for:
- Error types that persist across configurations
- Error types that improve with more examples
- Database-specific errors

## Future: When Transformation is Implemented

Once SQL transformation is implemented (applying rules to fix queries), you'll be able to:

### Run #1: Base Model
```
Accuracy: 68.50%
No corrections applied
```

### Run #2: With Error Correction
```
Accuracy: 75.30% (+6.8%)
Rules applied to fix:
- 15 JOIN errors
- 8 AGGREGATION errors
- 10 FILTER errors
```

**This will allow real performance comparison!**

## Configuration Options

Edit `run_comparison_pipeline.bat` to customize:

```batch
REM Process more errors for better analysis
set "MAX_TRIPLETS=100"

REM Use different model
set "MODEL=qwen2.5-coder:7b"

REM Adjust few-shot examples
set "K_SHOT=5"

REM Different dataset
set "SPLIT=train"
```

## Troubleshooting

### Issue: "Accuracy is the same in both runs"

**This is expected!** The current implementation:
- Generates correction rules
- Does NOT apply them automatically
- Predictions are identical

**Solution:** Use the generated rules for manual analysis or wait for transformation feature.

### Issue: "Not enough triplets generated"

**Cause:** Model is very accurate, few errors to analyze

**Solution:**
- Increase `MAX_TRIPLETS` (e.g., 100)
- Use harder dataset split
- Try smaller/weaker model to generate more errors

### Issue: "Want to actually apply corrections"

**Status:** SQL transformation is not yet implemented

**Workaround:**
1. Review generated rules manually
2. Apply corrections by hand
3. Contribute implementation (see `rule_applicator.py`)

## Contributing: Implementing Transformation

Want to make error correction actually fix queries? Here's how:

### 1. Edit `error_correction/rule_engine/rule_applicator.py`

Current:
```python
def apply_rule(self, query: str, rule: Rule) -> Tuple[bool, Optional[str]]:
    # Pattern matches but no transformation yet
    if self.matches_pattern(query, rule.pattern):
        return True, query  # Returns original query
```

Implement:
```python
def apply_rule(self, query: str, rule: Rule) -> Tuple[bool, Optional[str]]:
    if self.matches_pattern(query, rule.pattern):
        # Actually transform the query
        corrected = self._apply_transformation(query, rule)
        return True, corrected
```

### 2. Test with small dataset

```python
# test_transformation.py
from error_correction.rule_engine import RuleApplicator, Rule

rule = Rule(
    pattern=r"SELECT name FROM users WHERE user_id = \d+",
    correction="Add JOIN with orders table",
    error_type="JOIN_ERROR"
)

incorrect = "SELECT name FROM users WHERE user_id = 5"
correct = "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.id = 5"

applicator = RuleApplicator()
success, result = applicator.apply_rule(incorrect, rule)

assert result == correct, "Transformation failed"
```

### 3. Integrate with pipeline

Once transformation works, the comparison will show:
- Different predictions in Run #2
- Improved accuracy
- Real performance gains!

## Summary

| Aspect | Current State | Future State |
|--------|---------------|--------------|
| **Predictions** | Same in both runs | Different (corrected in Run #2) |
| **Accuracy** | Same (no changes applied) | Higher in Run #2 |
| **Value** | Error analysis + rules | Error analysis + actual improvement |
| **Use Case** | Understanding errors | Fixing errors automatically |

The comparison pipeline is ready to go! Start with:

```batch
run_comparison_pipeline.bat
python compare_results.py
```

Then review the generated rules to understand your model's weaknesses!
