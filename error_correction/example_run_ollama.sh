#!/bin/bash
# Example script to run error correction pipeline with Ollama (local open-source models)

# Configuration
MODEL="deepseek-coder:6.7b"  # or "codellama:7b", "mistral:7b", etc.
OLLAMA_BASE_URL="http://localhost:11434/v1"
OLLAMA_API_KEY="ollama"  # Dummy key for compatibility
DATASET_DIR="./dataset/process/SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096"
RESULTS_DIR="./results"

echo "====================================================="
echo "Running Error Correction Pipeline with Ollama"
echo "Model: $MODEL"
echo "====================================================="

# Check if Ollama is running
echo ""
echo "Checking Ollama status..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Error: Ollama is not running!"
    echo "Please start Ollama first:"
    echo "  ollama serve"
    exit 1
fi

echo "Ollama is running ✓"

# Check if model is available
echo ""
echo "Checking if model '$MODEL' is available..."
if ! ollama list | grep -q "${MODEL%%:*}"; then
    echo "Model not found. Pulling $MODEL..."
    ollama pull $MODEL
else
    echo "Model available ✓"
fi

# Step 1: Run base DAIL-SQL with Ollama (if not already done)
echo ""
echo "Step 1: Running base DAIL-SQL model with Ollama..."
echo "Note: Skip this if you already have predictions and evaluations"
read -p "Run base model? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python ask_llm.py \
        --model $MODEL \
        --question $DATASET_DIR \
        --openai_api_key $OLLAMA_API_KEY \
        --openai_api_base $OLLAMA_BASE_URL \
        --temperature 0.7 \
        --n 1
fi

# Step 2: Run error correction pipeline with Ollama
echo ""
echo "Step 2: Running error correction pipeline with Ollama..."

# For testing with local models, limit to fewer triplets (LLM calls are slower)
MAX_TRIPLETS=10

# Note: Using lower temperature for more consistent rule generation
TEMPERATURE=0.3

python error_correction/pipeline.py \
    --eval_results $RESULTS_DIR/eval_${MODEL//:/_}.txt \
    --predictions_file $DATASET_DIR/RESULTS_MODEL-${MODEL//:/_}.txt \
    --questions_file $DATASET_DIR/questions.json \
    --model $MODEL \
    --openai_api_key $OLLAMA_API_KEY \
    --openai_api_base $OLLAMA_BASE_URL \
    --temperature $TEMPERATURE \
    --max_triplets $MAX_TRIPLETS

# Check results
echo ""
echo "====================================================="
echo "Pipeline completed!"
echo "====================================================="
echo ""
echo "Results saved to:"
echo "  - error_correction/rules/triplets.json"
echo "  - error_correction/rules/clusters.json"
echo "  - error_correction/rules/rules.json"
echo ""
echo "Vector databases created in:"
echo "  - vector_sql_db/correct/"
echo "  - vector_sql_db/incorrect/"
echo ""
echo "View logs at:"
echo "  - error_correction/pipeline.log"
echo ""

# Display summary
if [ -f "error_correction/rules/rules.json" ]; then
    NUM_RULES=$(python -c "import json; print(len(json.load(open('error_correction/rules/rules.json'))))" 2>/dev/null || echo "0")
    echo "Total validated rules: $NUM_RULES"
fi

if [ -f "error_correction/rules/triplets.json" ]; then
    NUM_TRIPLETS=$(python -c "import json; print(len(json.load(open('error_correction/rules/triplets.json'))))" 2>/dev/null || echo "0")
    echo "Total triplets generated: $NUM_TRIPLETS"
fi

if [ -f "error_correction/rules/clusters.json" ]; then
    NUM_CLUSTERS=$(python -c "import json; print(len(json.load(open('error_correction/rules/clusters.json'))))" 2>/dev/null || echo "0")
    echo "Total clusters created: $NUM_CLUSTERS"
fi

echo ""
echo "====================================================="
echo "Tips for using Ollama models:"
echo "====================================================="
echo ""
echo "1. Recommended models for SQL tasks:"
echo "   - deepseek-coder:6.7b (good for code/SQL)"
echo "   - codellama:7b (optimized for code)"
echo "   - mistral:7b (general purpose)"
echo "   - qwen2.5-coder:7b (good for code)"
echo ""
echo "2. Pull a model:"
echo "   ollama pull deepseek-coder:6.7b"
echo ""
echo "3. List available models:"
echo "   ollama list"
echo ""
echo "4. For better GPU performance:"
echo "   - Ensure CUDA is properly installed"
echo "   - Check: nvidia-smi"
echo ""
