#!/bin/bash
# Complete pipeline: Base Model + Error Correction
# For deepseek-coder:6.7b on Ollama with Intel Arc GPU

echo "====================================================="
echo "Complete Pipeline: DAIL-SQL + Error Correction"
echo "Model: deepseek-coder:6.7b (Ollama)"
echo "====================================================="

# ============================================================
# CONFIGURATION - Edit these for your setup
# ============================================================

MODEL="deepseek-coder:6.7b"
OLLAMA_BASE_URL="http://localhost:11434/v1"
OLLAMA_API_KEY="ollama"

# Dataset configuration
DATA_TYPE="spider"
SPLIT="test"
K_SHOT=3
PROMPT_REPR="SQL"
EXAMPLE_TYPE="QA"
SELECTOR_TYPE="EUCDISQUESTIONMASK"
MAX_SEQ_LEN=4096
MAX_ANS_LEN=200

# Error correction configuration
MAX_TRIPLETS=20
TEMPERATURE=0.3

# ============================================================
# STEP 0: Prerequisites Check
# ============================================================

echo ""
echo "[Step 0] Checking prerequisites..."
echo "====================================================="

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Ollama is not running!"
    echo ""
    echo "Please start Ollama in another terminal:"
    echo "  ollama serve"
    echo ""
    read -p "Press enter when Ollama is running..."

    # Check again
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Still not running. Please start Ollama and try again."
        exit 1
    fi
fi

echo "✓ Ollama is running"

# Check if model is available
echo ""
echo "Checking if model '$MODEL' is available..."
if ! ollama list | grep -q "deepseek-coder"; then
    echo ""
    echo "Model not found. Pulling $MODEL..."
    echo "This may take a while (4-6 GB download)..."
    if ! ollama pull $MODEL; then
        echo ""
        echo "ERROR: Failed to pull model"
        exit 1
    fi
else
    echo "✓ Model available"
fi

# Check if Intel Arc test passed (optional)
echo ""
read -p "Run Intel Arc compatibility test? (y/n): " RUN_ARC_TEST
if [[ $RUN_ARC_TEST =~ ^[Yy]$ ]]; then
    python error_correction/test_intel_arc.py
    echo ""
    read -p "Press enter to continue with the pipeline..."
fi

# ============================================================
# STEP 1: Data Preprocessing (if not already done)
# ============================================================

DATASET_DIR="dataset/process/SPIDER-${SPLIT}_${PROMPT_REPR}_${K_SHOT}-SHOT_${SELECTOR_TYPE}_${EXAMPLE_TYPE}-EXAMPLE_CTX-${MAX_ANS_LEN}_ANS-${MAX_SEQ_LEN}"

echo ""
echo "[Step 1] Data Preprocessing"
echo "====================================================="

if [ ! -f "$DATASET_DIR/questions.json" ]; then
    echo "Running data preprocessing..."

    if [ ! -f "dataset/spider/train_spider_processed.json" ]; then
        echo "Preprocessing training data..."
        python data_preprocess.py
        if [ $? -ne 0 ]; then
            echo "ERROR: Data preprocessing failed"
            exit 1
        fi
    else
        echo "✓ Data already preprocessed"
    fi

    # Generate questions
    echo ""
    echo "Generating questions with ${K_SHOT}-shot examples..."
    python generate_question.py \
        --data_type $DATA_TYPE \
        --split $SPLIT \
        --tokenizer $MODEL \
        --max_seq_len $MAX_SEQ_LEN \
        --max_ans_len $MAX_ANS_LEN \
        --prompt_repr $PROMPT_REPR \
        --k_shot $K_SHOT \
        --example_type $EXAMPLE_TYPE \
        --selector_type $SELECTOR_TYPE

    if [ $? -ne 0 ]; then
        echo "ERROR: Question generation failed"
        exit 1
    fi
else
    echo "✓ Questions already generated"
fi

# ============================================================
# STEP 2: Run Base Model
# ============================================================

echo ""
echo "[Step 2] Running Base DAIL-SQL Model"
echo "====================================================="
echo "Model: $MODEL"
echo "This will take some time depending on dataset size..."
echo ""

# Create results directory
mkdir -p results

# Check if results already exist
MODEL_FILE=${MODEL//:/_}
if [ -f "$DATASET_DIR/RESULTS_MODEL-${MODEL_FILE}.txt" ]; then
    echo ""
    echo "Results file already exists: $DATASET_DIR/RESULTS_MODEL-${MODEL_FILE}.txt"
    read -p "Re-run base model? (y/n): " RERUN
    if [[ ! $RERUN =~ ^[Yy]$ ]]; then
        echo "Skipping base model run, using existing results"
        skip_base=true
    fi
fi

if [ -z "$skip_base" ]; then
    echo "Running base model with Ollama..."
    python ask_llm.py \
        --model $MODEL \
        --question $DATASET_DIR \
        --openai_api_key $OLLAMA_API_KEY \
        --openai_api_base $OLLAMA_BASE_URL \
        --temperature 0.0 \
        --n 1

    if [ $? -ne 0 ]; then
        echo ""
        echo "ERROR: Base model run failed"
        exit 1
    fi

    echo ""
    echo "✓ Base model completed successfully!"
    echo "Results saved to: $DATASET_DIR/RESULTS_MODEL-${MODEL_FILE}.txt"
    echo "Evaluation saved to: results/eval_${MODEL_FILE}.txt"
fi

# ============================================================
# STEP 3: Run Error Correction Pipeline
# ============================================================

echo ""
echo "[Step 3] Running Error Correction Pipeline"
echo "====================================================="
echo "Processing up to $MAX_TRIPLETS error triplets..."
echo ""

# Check if results exist
if [ ! -f "$DATASET_DIR/RESULTS_MODEL-${MODEL_FILE}.txt" ]; then
    echo "ERROR: Results file not found. Please run base model first."
    exit 1
fi

if [ ! -f "results/eval_${MODEL_FILE}.txt" ]; then
    echo "ERROR: Evaluation file not found. Please run base model first."
    exit 1
fi

echo "Running error correction pipeline..."
python error_correction/pipeline.py \
    --eval_results results/eval_${MODEL_FILE}.txt \
    --predictions_file $DATASET_DIR/RESULTS_MODEL-${MODEL_FILE}.txt \
    --questions_file $DATASET_DIR/questions.json \
    --model $MODEL \
    --openai_api_key $OLLAMA_API_KEY \
    --openai_api_base $OLLAMA_BASE_URL \
    --temperature $TEMPERATURE \
    --max_triplets $MAX_TRIPLETS

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Error correction pipeline failed"
    echo "Check logs at: error_correction/pipeline.log"
    exit 1
fi

# ============================================================
# STEP 4: Display Results
# ============================================================

echo ""
echo "====================================================="
echo "Pipeline Completed Successfully!"
echo "====================================================="
echo ""

echo "Base Model Results:"
echo "  - Predictions: $DATASET_DIR/RESULTS_MODEL-${MODEL_FILE}.txt"
echo "  - Evaluation: results/eval_${MODEL_FILE}.txt"
echo ""

echo "Error Correction Results:"
echo "  - Triplets: error_correction/rules/triplets.json"
echo "  - Clusters: error_correction/rules/clusters.json"
echo "  - Rules: error_correction/rules/rules.json"
echo ""

echo "Vector Databases:"
echo "  - Correct queries: vector_sql_db/correct/"
echo "  - Incorrect queries: vector_sql_db/incorrect/"
echo ""

echo "Logs:"
echo "  - Pipeline log: error_correction/pipeline.log"
echo ""

# Display summary statistics
if [ -f "error_correction/rules/rules.json" ]; then
    echo "====================================================="
    echo "Summary Statistics"
    echo "====================================================="

    NUM_RULES=$(python -c "import json; print(len(json.load(open('error_correction/rules/rules.json'))))" 2>/dev/null || echo "0")
    NUM_TRIPLETS=$(python -c "import json; print(len(json.load(open('error_correction/rules/triplets.json'))))" 2>/dev/null || echo "0")
    NUM_CLUSTERS=$(python -c "import json; print(len(json.load(open('error_correction/rules/clusters.json'))))" 2>/dev/null || echo "0")

    echo "Total Triplets Generated: $NUM_TRIPLETS"
    echo "Total Clusters Created: $NUM_CLUSTERS"
    echo "Total Validated Rules: $NUM_RULES"
    echo ""
fi

# Display base model accuracy
echo "Base Model Accuracy:"
grep "Final Execution Accuracy" results/eval_${MODEL_FILE}.txt

echo ""
echo "====================================================="
echo "Next Steps:"
echo "====================================================="
echo ""
echo "1. Review error triplets:"
echo "   cat error_correction/rules/triplets.json | jq ."
echo ""
echo "2. Examine generated rules:"
echo "   cat error_correction/rules/rules.json | jq ."
echo ""
echo "3. View detailed logs:"
echo "   tail -100 error_correction/pipeline.log"
echo ""
echo "4. Run with more triplets (remove --max_triplets limit):"
echo "   Edit this script and set MAX_TRIPLETS=999999"
echo ""
