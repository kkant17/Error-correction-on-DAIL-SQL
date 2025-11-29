"""
Evaluate SQL predictions using the test-suite-sql-eval framework.
Compares original predictions with corrected predictions to measure improvement.
"""
import json
import argparse
import logging
import subprocess
import os
from typing import Dict, Tuple
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_evaluation(
    gold_file: str,
    predictions_file: str,
    tables_file: str,
    db_dir: str = "test-suite-sql-eval/database",
    etype: str = "exec"
) -> Dict:
    """
    Run evaluation using test-suite-sql-eval.
    
    Args:
        gold_file: Path to gold SQL file
        predictions_file: Path to predictions file
        tables_file: Path to tables.json
        output_name: Name for output file
        
    Returns:
        Dictionary with evaluation metrics
    """
    logger.info(f"Running evaluation on {predictions_file}...")
    
    # Run evaluation script
    eval_script = "test-suite-sql-eval/evaluation.py"
    
    if not os.path.exists(eval_script):
        logger.error(f"Evaluation script not found: {eval_script}")
        return {}
    
    cmd = [
        "python", eval_script,
        "--gold", gold_file,
        "--pred", predictions_file,
        "--db", db_dir,
        "--table", tables_file,
        "--etype", etype
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            logger.error(f"Evaluation failed: {result.stderr}")
            return {}

        logger.info(f"Evaluation output:\n{result.stdout}")

        # Parse stdout into structured metrics (exec/exact for the 'all' level)
        parsed = parse_evaluation_stdout(result.stdout, etype=etype)
        if parsed:
            return parsed

        # Fallback: return raw output
        return {"output": result.stdout}

    except subprocess.TimeoutExpired:
        logger.error("Evaluation timed out (>1 hour)")
        return {}
    except Exception as e:
        logger.error(f"Error running evaluation: {e}")
        return {}


def parse_evaluation_stdout(stdout: str, etype: str = "exec") -> Dict:
    """
    Parse the evaluation script stdout to extract structured metrics.

    We look for the header line containing levels (easy, medium, hard, extra, all[, joint_all]),
    then find the lines named 'execution' and/or 'exact match' and extract the value under the
    'all' column.
    """
    lines = [l.rstrip() for l in stdout.splitlines() if l.strip()]
    if not lines:
        return {}

    # Find header line that contains the level names
    header_idx = None
    header_tokens = []
    for i, line in enumerate(lines):
        if 'easy' in line and 'all' in line:
            # split by whitespace to get tokens
            toks = re.split(r"\s+", line.strip())
            # header may have an empty first token (row name), remove it if present
            if toks[0] == '':
                toks = toks[1:]
            header_idx = i
            header_tokens = toks
            break

    if header_idx is None or not header_tokens:
        return {}

    # Determine index of 'all' within header tokens
    try:
        all_idx = header_tokens.index('all')
    except ValueError:
        return {}

    # Search for execution / exact match lines after header
    exec_value = None
    exact_value = None
    for line in lines[header_idx + 1:]:
        toks = re.split(r"\s+", line.strip())
        if not toks:
            continue
        label = toks[0].lower()
        values = toks[1:]
        # Sometimes the first column may be aligned and present; ensure lengths
        if label.startswith('execution') or label == 'execution':
            if len(values) > all_idx:
                try:
                    exec_value = float(values[all_idx])
                except Exception:
                    pass
        if 'exact' in label and 'match' in line.lower() or label.startswith('exact'):
            # exact match line
            if len(values) > all_idx:
                try:
                    exact_value = float(values[all_idx])
                except Exception:
                    pass

    parsed = {}
    if etype in ["all", "exec"] and exec_value is not None:
        parsed['execution_all'] = exec_value
    if etype in ["all", "match"] and exact_value is not None:
        parsed['exact_all'] = exact_value

    # Also include the raw stdout for reference
    parsed['raw_output'] = stdout

    return parsed


def compare_metrics(
    original_metrics: Dict,
    corrected_metrics: Dict
) -> None:
    """
    Compare metrics between original and corrected predictions.
    
    Args:
        original_metrics: Metrics from original predictions
        corrected_metrics: Metrics from corrected predictions
    """
    logger.info("\n" + "="*70)
    logger.info("COMPARISON: Original vs Corrected Predictions")
    logger.info("="*70)
    
    # Extract key metrics if available
    print(f"\nOriginal Metrics:\n{json.dumps(original_metrics, indent=2)}")
    print(f"\nCorrected Metrics:\n{json.dumps(corrected_metrics, indent=2)}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate original vs corrected SQL predictions"
    )
    parser.add_argument(
        "--gold_file",
        type=str,
        required=True,
        help="Path to gold SQL file"
    )
    parser.add_argument(
        "--original_predictions",
        type=str,
        required=True,
        help="Path to original predictions file"
    )
    parser.add_argument(
        "--corrected_predictions",
        type=str,
        required=True,
        help="Path to corrected predictions file"
    )
    parser.add_argument(
        "--tables_file",
        type=str,
        required=True,
        help="Path to tables.json"
    )
    parser.add_argument(
        "--db_dir",
        type=str,
        default="test-suite-sql-eval/database",
        help="Path to directory that contains databases/test suites (default: test-suite-sql-eval/database)"
    )
    parser.add_argument(
        "--etype",
        type=str,
        default="exec",
        choices=("all", "exec", "match"),
        help="Evaluation type passed to evaluation script (default: exec)"
    )
    
    args = parser.parse_args()
    
    logger.info("="*70)
    logger.info("SQL Prediction Evaluation and Comparison")
    logger.info("="*70)
    
    # Evaluate original predictions
    logger.info("\n[1/2] Evaluating ORIGINAL predictions...")
    original_metrics = run_evaluation(
        args.gold_file,
        args.original_predictions,
        args.tables_file,
        db_dir=args.db_dir,
        etype=args.etype
    )
    
    # Evaluate corrected predictions
    logger.info("\n[2/2] Evaluating CORRECTED predictions...")
    corrected_metrics = run_evaluation(
        args.gold_file,
        args.corrected_predictions,
        args.tables_file,
        db_dir=args.db_dir,
        etype=args.etype
    )
    
    # Compare metrics
    compare_metrics(original_metrics, corrected_metrics)
    
    logger.info("\n" + "="*70)
    logger.info("Evaluation complete!")
    logger.info("="*70)


if __name__ == "__main__":
    main()
