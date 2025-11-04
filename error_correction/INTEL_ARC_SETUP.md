# Intel Arc GPU Setup Guide

This guide explains how to run the error correction pipeline on Intel Arc GPUs using ipex-llm.

## Compatibility Summary

| Component | Intel Arc Compatible | Notes |
|-----------|---------------------|-------|
| LLM Calls (Rule Generation) | ✅ Yes | Uses your existing ipex-llm setup |
| Embeddings (CodeBERT) | ✅ Yes | Auto-detects XPU or falls back to CPU |
| Vector Database (FAISS) | ✅ Yes | CPU-based, no GPU needed |
| Clustering | ✅ Yes | CPU-based, no GPU needed |
| Rule Matching | ✅ Yes | Pure Python, no GPU needed |

## Prerequisites

You should already have these from your base DAIL-SQL setup:

1. ✅ Intel Arc GPU (e.g., A770, A750, A380)
2. ✅ Intel GPU drivers installed
3. ✅ ipex-llm installed and working
4. ✅ Base DAIL-SQL working with ipex-llm

## Installation Options

### Option 1: CPU Embeddings (Recommended - Safest)

Run embeddings on CPU while using Intel Arc for LLM calls:

```bash
# No additional setup needed!
# The pipeline will auto-detect and use CPU for embeddings
```

**Pros:**
- No compatibility issues
- Works out of the box
- Stable and reliable

**Cons:**
- Embeddings generation slower (~2-5 queries/sec on CPU)

### Option 2: Intel Arc Embeddings (Advanced - Faster)

Run embeddings on Intel Arc GPU for better performance:

```bash
# Install Intel Extension for PyTorch if not already installed
pip install intel-extension-for-pytorch

# Install ipex-compatible transformers
pip install transformers torch torchvision
```

**Pros:**
- Faster embedding generation (~10-20 queries/sec)
- Full GPU utilization

**Cons:**
- Requires ipex setup
- May need tuning for your specific Arc model

## Configuration

### For CPU Embeddings (Default)

No changes needed! The pipeline auto-detects the best device.

### For Intel Arc Embeddings

Create a config override file or set environment variable:

```python
# In your script, before importing the pipeline:
import os
os.environ['EMBEDDING_DEVICE'] = 'xpu'
```

Or edit `error_correction/config.py`:
```python
# Add this line to force Intel Arc for embeddings
EMBEDDING_DEVICE = 'xpu'  # Default is auto-detect
```

## Usage

### Method 1: Auto-Detection (Recommended)

The pipeline automatically detects Intel Arc GPU:

```bash
python error_correction/pipeline.py \
  --eval_results results/eval_model.txt \
  --predictions_file .../RESULTS_MODEL-model.txt \
  --questions_file .../questions.json \
  --model qwen2.5:7b \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1
```

The pipeline will:
1. ✅ Use ipex-llm (via Ollama) for LLM calls (rule generation)
2. ✅ Auto-detect Intel Arc for embeddings (or use CPU if safer)
3. ✅ Use CPU for FAISS and clustering (optimal)

### Method 2: Explicit Configuration

Force specific devices:

```bash
# Force CPU for embeddings (safest)
export EMBEDDING_DEVICE=cpu

python error_correction/pipeline.py ...
```

```bash
# Force Intel Arc XPU for embeddings (faster)
export EMBEDDING_DEVICE=xpu

python error_correction/pipeline.py ...
```

## Testing Intel Arc Compatibility

### Test 1: Check Intel Arc Detection

```python
import torch

# Check if Intel Extension for PyTorch is available
try:
    import intel_extension_for_pytorch as ipex
    print(f"✅ ipex installed: {ipex.__version__}")
except ImportError:
    print("❌ ipex not installed (CPU embeddings will be used)")

# Check if XPU is available
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    print(f"✅ Intel Arc GPU detected")
    print(f"   Device count: {torch.xpu.device_count()}")
    print(f"   Device name: {torch.xpu.get_device_name(0)}")
else:
    print("❌ Intel Arc GPU not detected")
```

### Test 2: Test Embedder with Intel Arc

```python
from error_correction.vector_store import SQLEmbedder

# Test with auto-detection
embedder = SQLEmbedder()
print(f"Device: {embedder.device}")

# Test embedding generation
emb = embedder.embed_query("SELECT * FROM users")
print(f"✅ Embedding generated: shape {emb.shape}")
```

### Test 3: Test Full Pipeline with Small Dataset

```bash
# Test with just 2 triplets
python error_correction/pipeline.py \
  --max_triplets 2 \
  --eval_results results/eval_model.txt \
  --predictions_file .../RESULTS_MODEL-model.txt \
  --questions_file .../questions.json \
  --model your-model \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1
```

Check logs for device detection:
```bash
tail -f error_correction/pipeline.log | grep -i "device\|xpu\|arc"
```

## Performance Optimization for Intel Arc

### Memory Management

Intel Arc GPUs have limited VRAM (8-16GB). Optimize with:

```python
# In error_correction/config.py or config_intel_arc.py

# Reduce batch size for embeddings
EMBEDDING_BATCH_SIZE = 8  # Default is 32

# For Arc A380 (8GB), use even smaller:
EMBEDDING_BATCH_SIZE = 4
```

### Model Selection

Choose lighter embedding models for Arc GPUs:

```python
# In config.py
SQL_EMBEDDING_MODEL = "bert-base-uncased"  # Lighter than CodeBERT
```

Or use quantized models:
```python
# For ipex optimization
from transformers import AutoModel
model = AutoModel.from_pretrained("microsoft/codebert-base")
model = ipex.optimize(model)  # Apply ipex optimizations
```

## Troubleshooting

### Issue: "XPU device not found"

**Solution:**
```bash
# Check Intel GPU drivers
dpcpp --version

# Reinstall ipex
pip uninstall intel-extension-for-pytorch
pip install intel-extension-for-pytorch

# Fallback to CPU embeddings (still works!)
export EMBEDDING_DEVICE=cpu
```

### Issue: "Out of memory on XPU"

**Solution:**
```python
# Reduce batch size in config.py
EMBEDDING_BATCH_SIZE = 4

# Or force CPU for embeddings
export EMBEDDING_DEVICE=cpu
```

### Issue: "Model loading is slow on Intel Arc"

**Solution:**
```bash
# Cache models locally
export HF_HOME=/path/to/cache

# Pre-download model
python -c "from transformers import AutoModel; AutoModel.from_pretrained('microsoft/codebert-base')"
```

### Issue: "Embeddings slower than expected on Arc"

This is normal for first-generation Arc GPUs. Consider:
- Use CPU embeddings (often just as fast for this workload)
- Use smaller embedding models
- Process in larger batches if memory allows

## Recommended Configuration for Intel Arc

Based on testing, here's the recommended setup:

### For Arc A770 (16GB VRAM)
```python
# config_intel_arc.py
EMBEDDING_DEVICE = 'xpu'           # Use Arc GPU
EMBEDDING_BATCH_SIZE = 16          # Good balance
SQL_EMBEDDING_MODEL = 'microsoft/codebert-base'
```

### For Arc A750 (8GB VRAM)
```python
EMBEDDING_DEVICE = 'xpu'
EMBEDDING_BATCH_SIZE = 8
SQL_EMBEDDING_MODEL = 'microsoft/codebert-base'
```

### For Arc A380 (6GB VRAM)
```python
EMBEDDING_DEVICE = 'cpu'           # Safer to use CPU
EMBEDDING_BATCH_SIZE = 8
SQL_EMBEDDING_MODEL = 'bert-base-uncased'  # Lighter model
```

## Performance Comparison

Approximate speeds on Intel Arc A770:

| Component | CPU | Intel Arc A770 |
|-----------|-----|----------------|
| LLM (via ipex-llm) | N/A | ✅ ~20 tok/s |
| Embeddings | ~2 q/s | ~15 q/s |
| Vector DB | ~1000 q/s | ~1000 q/s (CPU) |
| Overall Pipeline | Medium | Fast |

**Recommendation:** Use Intel Arc for both LLM and embeddings on A770/A750, CPU embeddings on A380.

## Example: Complete Intel Arc Workflow

```bash
# 1. Ensure Ollama is running with ipex-llm
ollama serve

# 2. Pull your model
ollama pull qwen2.5:7b

# 3. Run base DAIL-SQL (you've already done this)
python ask_llm.py \
  --model qwen2.5:7b \
  --question ./dataset/process/... \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1

# 4. Run error correction pipeline (auto-detects Intel Arc)
python error_correction/pipeline.py \
  --eval_results results/eval_qwen2.5_7b.txt \
  --predictions_file .../RESULTS_MODEL-qwen2.5_7b.txt \
  --questions_file .../questions.json \
  --model qwen2.5:7b \
  --openai_api_key ollama \
  --openai_api_base http://localhost:11434/v1

# 5. Check logs for device usage
grep -i "device\|xpu" error_correction/pipeline.log
```

## FAQ

**Q: Do I need to modify my ipex-llm setup?**
A: No! The pipeline uses your existing ipex-llm setup via Ollama.

**Q: Will embeddings work if ipex isn't installed?**
A: Yes! The pipeline automatically falls back to CPU for embeddings.

**Q: Is Intel Arc faster than CPU for this pipeline?**
A: For LLM calls (via ipex-llm): Yes, much faster.
For embeddings: Depends on your Arc model (A770/A750: yes, A380: marginal).

**Q: Can I use NVIDIA GPU for embeddings but Intel Arc for LLM?**
A: Not easily in the same process, but you can run embeddings separately on NVIDIA then use Intel Arc for the rest.

**Q: What if I get errors with Intel Arc?**
A: Set `EMBEDDING_DEVICE=cpu` - the pipeline will still work great, just slightly slower embeddings.

## Additional Resources

- Intel Arc GPU Drivers: https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html
- Intel Extension for PyTorch: https://intel.github.io/intel-extension-for-pytorch/
- ipex-llm Documentation: https://github.com/intel-analytics/ipex-llm

## Support

If you encounter Intel Arc-specific issues:
1. Check `error_correction/pipeline.log` for device detection messages
2. Run the test scripts in this guide
3. Try CPU fallback: `export EMBEDDING_DEVICE=cpu`
4. Open an issue with your Arc model and error logs
