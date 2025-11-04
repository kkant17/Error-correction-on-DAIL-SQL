#!/bin/bash
# Incremental Error Correction Pipeline Runner
# Processes queries one-by-one with online learning

echo "========================================"
echo "Incremental Error Correction Pipeline"
echo "========================================"

# Check if OpenAI API key is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY environment variable not set"
    echo "Please set it with: export OPENAI_API_KEY=your_key_here"
    exit 1
fi

# Default paths (modify as needed)
EVAL_RESULTS=${EVAL_RESULTS:-"results/eval.txt"}
PREDICTIONS=${PREDICTIONS:-"results/predict.txt"}
QUESTIONS=${QUESTIONS:-"dataset/dev.json"}
DB_ID=${DB_ID:-"spider"}
MODEL=${MODEL:-"gpt-4"}
OUTPUT=${OUTPUT:-"results/corrected_predictions.txt"}

echo ""
echo "Configuration:"
echo "  Eval Results: $EVAL_RESULTS"
echo "  Predictions:  $PREDICTIONS"
echo "  Questions:    $QUESTIONS"
echo "  Database:     $DB_ID"
echo "  Model:        $MODEL"
echo "  Output:       $OUTPUT"
echo ""

# Run incremental pipeline with transformation enabled
python run_incremental_pipeline.py \
    --eval_results "$EVAL_RESULTS" \
    --predictions_file "$PREDICTIONS" \
    --questions_file "$QUESTIONS" \
    --db_id "$DB_ID" \
    --model "$MODEL" \
    --openai_api_key "$OPENAI_API_KEY" \
    --enable_transformation \
    --output_file "$OUTPUT"

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "Pipeline completed successfully!"
    echo "========================================"
    echo ""
    echo "Results saved to:"
    echo "  - error_correction/rules/triplets.json"
    echo "  - error_correction/rules/clusters.json"
    echo "  - error_correction/rules/rules.json"
    echo "  - error_correction/rules/incremental_metrics.json"
    echo "  - error_correction/rules/pipeline_summary.json"
    echo "  - $OUTPUT"
    echo ""
else
    echo ""
    echo "========================================"
    echo "Pipeline failed with error code $?"
    echo "Check incremental_pipeline.log for details"
    echo "========================================"
    exit 1
fi
