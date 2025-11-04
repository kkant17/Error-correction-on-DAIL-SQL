"""
Compare results from base model run vs error correction analysis

This script compares the two runs and generates a detailed report.
"""
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple


def parse_eval_file(eval_file: str) -> Tuple[float, int, int, List[Dict]]:
    """
    Parse evaluation file to extract accuracy and error details.

    Returns:
        Tuple of (accuracy, correct_count, total_count, error_list)
    """
    correct = 0
    total = 0
    errors = []

    if not os.path.exists(eval_file):
        return 0.0, 0, 0, []

    with open(eval_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("Question") and "CORRECT" in line:
            parts = line.split()
            idx = int(parts[1])
            correct += 1
            total += 1

        elif line.startswith("Question") and "INCORRECT" in line:
            parts = line.split()
            idx = int(parts[1])

            gold_sql = ""
            pred_sql = ""

            if i + 1 < len(lines) and "Gold:" in lines[i + 1]:
                gold_sql = lines[i + 1].split("Gold:", 1)[1].strip()
            if i + 2 < len(lines) and "Pred:" in lines[i + 2]:
                pred_sql = lines[i + 2].split("Pred:", 1)[1].strip()

            errors.append({
                'index': idx,
                'gold': gold_sql,
                'predicted': pred_sql
            })

            total += 1
            i += 2

        i += 1

    accuracy = (correct / total * 100) if total > 0 else 0.0
    return accuracy, correct, total, errors


def load_rules(rules_file: str) -> List[Dict]:
    """Load error correction rules."""
    if not os.path.exists(rules_file):
        return []

    with open(rules_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_triplets(triplets_file: str) -> List[Dict]:
    """Load error triplets."""
    if not os.path.exists(triplets_file):
        return []

    with open(triplets_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_error_types(rules: List[Dict]) -> Dict[str, int]:
    """Analyze distribution of error types."""
    error_types = defaultdict(int)

    for rule in rules:
        error_type = rule.get('error_type', 'UNKNOWN')
        error_types[error_type] += 1

    return dict(error_types)


def generate_report():
    """Generate comparison report."""

    # File paths
    base_eval = "results/base_only/eval_deepseek-coder_6.7b.txt"
    corr_eval = "results/with_error_correction/eval_deepseek-coder_6.7b.txt"
    rules_file = "results/with_error_correction/rules/rules.json"
    triplets_file = "results/with_error_correction/rules/triplets.json"

    print("=" * 70)
    print("ERROR CORRECTION PIPELINE - COMPARISON REPORT")
    print("=" * 70)
    print()

    # Parse both evaluation files
    print("Loading evaluation results...")
    base_acc, base_correct, base_total, base_errors = parse_eval_file(base_eval)
    corr_acc, corr_correct, corr_total, corr_errors = parse_eval_file(corr_eval)

    # Load error correction artifacts
    print("Loading error correction analysis...")
    rules = load_rules(rules_file)
    triplets = load_triplets(triplets_file)

    print()
    print("=" * 70)
    print("ACCURACY COMPARISON")
    print("=" * 70)
    print()
    print(f"Base Model (No Error Correction):")
    print(f"  - Accuracy: {base_acc:.2f}%")
    print(f"  - Correct: {base_correct}/{base_total}")
    print(f"  - Incorrect: {len(base_errors)}")
    print()
    print(f"With Error Correction Analysis:")
    print(f"  - Accuracy: {corr_acc:.2f}%")
    print(f"  - Correct: {corr_correct}/{corr_total}")
    print(f"  - Incorrect: {len(corr_errors)}")
    print()

    # Note about current implementation
    if base_acc == corr_acc:
        print("NOTE: Accuracy is the same because error correction currently")
        print("      generates rules but does not apply them. The predictions")
        print("      are identical in both runs.")
        print()
        print("      The error correction pipeline provides:")
        print("      - Analysis of error patterns")
        print("      - Correction rules for future use")
        print("      - Insights into model weaknesses")
        print()

    print("=" * 70)
    print("ERROR CORRECTION ANALYSIS")
    print("=" * 70)
    print()
    print(f"Triplets Analyzed: {len(triplets)}")
    print(f"Rules Generated: {len(rules)}")
    print()

    if rules:
        print("Error Type Distribution:")
        error_types = analyze_error_types(rules)
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(rules) * 100)
            print(f"  - {error_type}: {count} ({percentage:.1f}%)")
        print()

    # Sample rules
    if rules:
        print("=" * 70)
        print("SAMPLE CORRECTION RULES")
        print("=" * 70)
        print()

        for i, rule in enumerate(rules[:5], 1):
            print(f"Rule {i}:")
            print(f"  Type: {rule.get('error_type', 'UNKNOWN')}")
            print(f"  Pattern: {rule.get('pattern', 'N/A')[:80]}...")
            print(f"  Correction: {rule.get('correction', 'N/A')[:80]}...")
            print()

    # Sample triplets
    if triplets:
        print("=" * 70)
        print("SAMPLE ERROR TRIPLETS")
        print("=" * 70)
        print()

        for i, triplet in enumerate(triplets[:3], 1):
            print(f"Triplet {i}:")
            print(f"  Database: {triplet.get('db_id', 'N/A')}")
            print(f"  Question: {triplet.get('question', 'N/A')[:60]}...")
            print(f"  Incorrect: {triplet.get('incorrect_query', 'N/A')[:60]}...")
            print(f"  Correct: {triplet.get('correct_query', 'N/A')[:60]}...")
            print(f"  Explanation: {triplet.get('explanation', 'N/A')[:80]}...")
            print(f"  Rules: {len(triplet.get('rules', []))}")
            print()

    print("=" * 70)
    print("FILES GENERATED")
    print("=" * 70)
    print()
    print("Base Model Only:")
    print(f"  - {base_eval}")
    print()
    print("With Error Correction:")
    print(f"  - {corr_eval}")
    print(f"  - {rules_file}")
    print(f"  - {triplets_file}")
    print()

    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print()
    print("1. Review the generated rules to understand error patterns")
    print("2. Examine triplets to see LLM's error explanations")
    print("3. Implement SQL transformation to apply rules (see TODO)")
    print("4. Re-run with corrected queries to measure improvement")
    print()
    print("For implementation details:")
    print("  - See: error_correction/README.md")
    print("  - See: error_correction/rule_engine/rule_applicator.py")
    print()


if __name__ == "__main__":
    try:
        generate_report()
    except FileNotFoundError as e:
        print(f"Error: Required file not found: {e}")
        print()
        print("Please run the comparison pipeline first:")
        print("  run_comparison_pipeline.bat")
        sys.exit(1)
    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
