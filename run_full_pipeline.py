#!/usr/bin/env python3
"""
Full Pipeline Wrapper Script

Runs three independent scripts in sequence:
1. ask_llm.py - Generate SQL predictions (optional)
2. eval/evaluation.py - Evaluate and save correct/incorrect JSON
3. error_correction/pipeline.py - Run error correction

Each script can also be run independently:
    python ask_llm.py --question ... --model ...
    python eval/evaluation.py --gold ... --pred ... --save_correct ... --save_incorrect ...
    python -m error_correction.pipeline --correct ... --incorrect ... --model ...

Usage:
    # Full pipeline including base model generation
    python run_full_pipeline.py --model codellama:7b --run_base_model
    
    # Skip base model (use existing predictions)
    python run_full_pipeline.py --model codellama:7b --max_queries 60
    
    # Skip base eval (use existing JSON files)
    python run_full_pipeline.py --model codellama:7b --skip_base_eval
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*80}")
    print(f"[STEP] {description}")
    print(f"{'='*80}")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"[ERROR] Command failed with return code {result.returncode}")
        return False
    return True


def get_model_safe_name(model: str) -> str:
    """Convert model name to safe filename."""
    return model.replace(":", "_").replace("/", "_")


def get_predictions_file_path(question_dir: str, model: str) -> str:
    """Get the path to predictions file based on model name."""
    safe_model = get_model_safe_name(model)
    return os.path.join(question_dir, f"RESULTS_MODEL-{safe_model}.txt")


def main():
    parser = argparse.ArgumentParser(
        description="Full Pipeline: ask_llm.py → evaluation.py → pipeline.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The three scripts can also be run independently:

  1. Generate predictions:
     python ask_llm.py --question dataset/process/DAIL_SPIDER_DEV --model codellama:7b ...

  2. Evaluate and save JSON:
     python eval/evaluation.py --gold dataset/spider/dev_gold.sql --pred PREDICTIONS.txt \\
         --save_correct results/correct_predictions.json \\
         --save_incorrect results/incorrect_predictions.json

  3. Run error correction:
     python -m error_correction.pipeline \\
         --correct results/correct_predictions.json \\
         --incorrect results/incorrect_predictions.json \\
         --model codellama:7b
        """
    )
    
    # Model settings
    parser.add_argument('--model', type=str, required=True, help='LLM model name (required)')
    parser.add_argument('--max_queries', type=int, default=None, help='Max queries for error correction (default: all)')
    parser.add_argument('--temperature', type=float, default=0.0, help='Temperature for base model')
    
    # File paths
    parser.add_argument('--question_dir', type=str, default='dataset/process/SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096')
    parser.add_argument('--gold', type=str, default='dataset/spider/dev_gold.sql')
    parser.add_argument('--pred', type=str, default=None, help='Predictions file (auto-detected)')
    parser.add_argument('--db', type=str, default='dataset/spider/database')
    parser.add_argument('--table', type=str, default='dataset/spider/tables.json')
    parser.add_argument('--spider_dev', type=str, default='dataset/spider/dev.json')
    parser.add_argument('--output_dir', type=str, default='results')
    
    # Control flags
    parser.add_argument('--run_base_model', action='store_true', help='Run base model (Step 1)')
    parser.add_argument('--skip_base_eval', action='store_true', help='Skip evaluation (use existing JSON)')
    parser.add_argument('--skip_error_correction', action='store_true', help='Skip error correction')
    
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Auto-detect predictions file
    if args.pred is None:
        args.pred = get_predictions_file_path(args.question_dir, args.model)
    
    correct_file = os.path.join(args.output_dir, "correct_predictions.json")
    incorrect_file = os.path.join(args.output_dir, "incorrect_predictions.json")
    
    print("\n" + "="*80)
    print("FULL PIPELINE")
    print("="*80)
    print(f"Model: {args.model}")
    print(f"Max queries: {args.max_queries}")
    
    # =========================================================================
    # STEP 1: ask_llm.py (optional)
    # =========================================================================
    if args.run_base_model:
        # Determine API settings
        if args.model in ["codellama:7b", "deepseek-coder:6.7b", "llama3.1:8b"]:
            api_base = "http://localhost:11434/v1"
            api_key = "ollama"
        else:
            api_base = ""
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                print("[ERROR] OPENAI_API_KEY not set")
                sys.exit(1)

        cmd = [
            sys.executable, "ask_llm.py",
            "--question", args.question_dir,
            "--model", args.model,
            "--openai_api_key", api_key,
            "--temperature", str(args.temperature),
            "--db_dir", args.db
        ]
        if api_base:
            cmd.extend(["--openai_api_base", api_base])

        if not run_command(cmd, "Step 1: Generate predictions (ask_llm.py)"):
            sys.exit(1)

        args.pred = get_predictions_file_path(args.question_dir, args.model)

        # ask_llm.py creates baseline evaluation text file
        safe_model = get_model_safe_name(args.model)
        eval_txt_file = os.path.join(args.output_dir, f"eval_{safe_model}.txt")
        if os.path.exists(eval_txt_file):
            print(f"\n[INFO] Baseline evaluation text file created: {eval_txt_file}")
    
    elif not args.skip_base_eval and not os.path.exists(args.pred):
        print(f"[ERROR] Predictions file not found: {args.pred}")
        print("Run with --run_base_model to generate predictions")
        sys.exit(1)
    
    # =========================================================================
    # STEP 2: eval/evaluation.py
    # =========================================================================
    if not args.skip_base_eval:
        cmd = [
            sys.executable, "eval/evaluation.py",
            "--gold", args.gold,
            "--pred", args.pred,
            "--db", args.db,
            "--table", args.table,
            "--etype", "all",
            "--save_correct", correct_file,
            "--save_incorrect", incorrect_file,
            "--spider_dev", args.spider_dev
        ]

        if not run_command(cmd, "Step 2: Evaluate predictions (eval/evaluation.py)"):
            sys.exit(1)

        # Ensure baseline evaluation text file exists for comparison
        safe_model = get_model_safe_name(args.model)
        eval_txt_file = os.path.join(args.output_dir, f"eval_{safe_model}.txt")

        # If ask_llm.py didn't create it (when --run_base_model wasn't used),
        # the eval text file won't exist. In this case, we note that it should
        # be generated by running ask_llm.py with --run_base_model
        if not os.path.exists(eval_txt_file):
            print(f"\n[INFO] Baseline evaluation text file not found: {eval_txt_file}")
            print("[INFO] To generate baseline eval file, run with --run_base_model")
            print(f"[INFO] Or manually run: python ask_llm.py --model {args.model} ...")

    elif not os.path.exists(correct_file) or not os.path.exists(incorrect_file):
        print("[INFO] JSON files don't exist - will use pre-populated vector DBs")
        use_skip_json = True
    else:
        use_skip_json = False
    
    if args.skip_error_correction:
        print("\n[DONE] Skipping error correction")
        sys.exit(0)
    
    # =========================================================================
    # STEP 3: error_correction/pipeline.py
    # =========================================================================
    cmd = [
        sys.executable, "-m", "error_correction.pipeline",
        "--model", args.model,
        "--db_dir", args.db
    ]
    
    # Use --skip_json if we're skipping base eval and JSON files don't exist
    if args.skip_base_eval and use_skip_json:
        cmd.append("--skip_json")
    else:
        cmd.extend(["--correct", correct_file, "--incorrect", incorrect_file])
    
    if args.max_queries:
        cmd.extend(["--max_queries", str(args.max_queries)])
    
    if not run_command(cmd, "Step 3: Error correction (error_correction/pipeline.py)"):
        sys.exit(1)
    
    print("\n" + "="*80)
    print("PIPELINE COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()
