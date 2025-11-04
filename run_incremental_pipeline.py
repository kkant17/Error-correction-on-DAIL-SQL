"""
Wrapper script for incremental error correction pipeline.

This script processes queries one-by-one during evaluation,
applying learned corrections in real-time.

Usage:
    python run_incremental_pipeline.py \
        --eval_results results/eval.txt \
        --predictions_file results/predict.txt \
        --questions_file dataset/questions.json \
        --db_id spider \
        --model gpt-4 \
        --openai_api_key YOUR_KEY \
        --enable_transformation
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from error_correction.incremental_pipeline import IncrementalErrorCorrectionPipeline

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('incremental_pipeline.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def parse_eval_results(eval_file: str):
    """
    Parse evaluation results file to get correctness information.

    Expected format:
    query_id\tcorrectness (e.g., "0\t1" for correct, "1\t0" for incorrect)
    """
    correctness = {}
    with open(eval_file, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                query_id = int(parts[0])
                is_correct = parts[1] == '1'
                correctness[query_id] = is_correct
    return correctness


def load_predictions(predictions_file: str):
    """Load predicted SQL queries."""
    with open(predictions_file, 'r') as f:
        predictions = [line.strip() for line in f.readlines()]
    return predictions


def load_questions(questions_file: str):
    """Load questions and gold queries."""
    with open(questions_file, 'r') as f:
        data = json.load(f)
    return data


def run_incremental_pipeline(
    eval_results_file: str,
    predictions_file: str,
    questions_file: str,
    db_id: str,
    model: str,
    openai_api_key: str,
    enable_transformation: bool = False,
    output_file: str = None
):
    """
    Run incremental error correction pipeline.

    Args:
        eval_results_file: Path to evaluation results
        predictions_file: Path to predicted SQL queries
        questions_file: Path to questions with gold SQL
        db_id: Database identifier
        model: LLM model name
        openai_api_key: OpenAI API key
        enable_transformation: Whether to apply transformations
        output_file: Optional output file for corrected predictions
    """
    logger.info(
        f"\n{'='*70}\n"
        f"Starting Incremental Error Correction Pipeline\n"
        f"{'='*70}\n"
        f"Database: {db_id}\n"
        f"Model: {model}\n"
        f"Transformation: {'Enabled' if enable_transformation else 'Disabled'}\n"
        f"{'='*70}"
    )

    # Load data
    logger.info("Loading evaluation data...")
    correctness = parse_eval_results(eval_results_file)
    predictions = load_predictions(predictions_file)
    questions_data = load_questions(questions_file)

    # Initialize pipeline
    pipeline = IncrementalErrorCorrectionPipeline(
        db_id=db_id,
        model=model,
        openai_api_key=openai_api_key,
        enable_transformation=enable_transformation
    )

    # Process queries incrementally
    corrected_predictions = []
    correction_stats = {
        'total': 0,
        'correct': 0,
        'incorrect': 0,
        'corrected': 0,
        'corrections_applied': 0
    }

    logger.info(f"\nProcessing {len(predictions)} queries incrementally...")

    for idx, predicted_query in enumerate(predictions):
        # Get correctness
        is_correct = correctness.get(idx, False)

        # Get question and gold query
        if idx < len(questions_data):
            question = questions_data[idx].get('question', '')
            gold_query = questions_data[idx].get('query', '')
        else:
            logger.warning(f"No question data for query {idx}")
            question = ''
            gold_query = predicted_query

        # Process query through incremental pipeline
        final_query, was_corrected, correction_info = pipeline.process_query(
            predicted_query=predicted_query,
            gold_query=gold_query,
            question=question,
            is_correct=is_correct
        )

        # Track stats
        correction_stats['total'] += 1
        if is_correct:
            correction_stats['correct'] += 1
        else:
            correction_stats['incorrect'] += 1

        if was_corrected:
            correction_stats['corrected'] += 1
            correction_stats['corrections_applied'] += len(correction_info['rules_applied'])

        # Store corrected query
        corrected_predictions.append(final_query)

        # Log progress every 100 queries
        if (idx + 1) % 100 == 0:
            logger.info(
                f"Processed {idx + 1}/{len(predictions)} queries | "
                f"Corrected: {correction_stats['corrected']} | "
                f"Rules Applied: {correction_stats['corrections_applied']}"
            )

    # Finalize pipeline
    logger.info("\nFinalizing pipeline...")
    summary = pipeline.finalize()

    # Print final statistics
    logger.info(
        f"\n{'='*70}\n"
        f"Pipeline Complete!\n"
        f"{'='*70}\n"
        f"Total Queries: {correction_stats['total']}\n"
        f"  Correct: {correction_stats['correct']}\n"
        f"  Incorrect: {correction_stats['incorrect']}\n"
        f"Queries Corrected: {correction_stats['corrected']}\n"
        f"Total Rule Applications: {correction_stats['corrections_applied']}\n"
        f"\n"
        f"Rule Generation:\n"
        f"  Triggers: {summary['rule_generations_triggered']}\n"
        f"  Rules Generated: {summary['total_rules_generated']}\n"
        f"  Clusters Created: {summary['total_clusters_created']}\n"
        f"  Active Rules: {summary['active_rules']}\n"
        f"\n"
        f"Correction Rate: {summary['correction_rate']*100:.2f}%\n"
        f"{'='*70}"
    )

    # Save corrected predictions if requested
    if output_file:
        logger.info(f"\nSaving corrected predictions to {output_file}...")
        with open(output_file, 'w') as f:
            for query in corrected_predictions:
                f.write(query + '\n')
        logger.info(f"Saved {len(corrected_predictions)} corrected queries")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description='Run incremental error correction pipeline'
    )

    parser.add_argument(
        '--eval_results',
        type=str,
        required=True,
        help='Path to evaluation results file'
    )
    parser.add_argument(
        '--predictions_file',
        type=str,
        required=True,
        help='Path to predicted SQL queries file'
    )
    parser.add_argument(
        '--questions_file',
        type=str,
        required=True,
        help='Path to questions JSON file'
    )
    parser.add_argument(
        '--db_id',
        type=str,
        default='spider',
        help='Database identifier (default: spider)'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='gpt-4',
        help='LLM model for rule generation (default: gpt-4)'
    )
    parser.add_argument(
        '--openai_api_key',
        type=str,
        default=None,
        help='OpenAI API key'
    )
    parser.add_argument(
        '--enable_transformation',
        action='store_true',
        help='Enable query transformation (default: disabled)'
    )
    parser.add_argument(
        '--output_file',
        type=str,
        default=None,
        help='Output file for corrected predictions (optional)'
    )

    args = parser.parse_args()

    # Run pipeline
    try:
        summary = run_incremental_pipeline(
            eval_results_file=args.eval_results,
            predictions_file=args.predictions_file,
            questions_file=args.questions_file,
            db_id=args.db_id,
            model=args.model,
            openai_api_key=args.openai_api_key,
            enable_transformation=args.enable_transformation,
            output_file=args.output_file
        )

        logger.info("\nPipeline completed successfully!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
