"""
Configuration override for Intel Arc GPU compatibility using ipex-llm

This file provides Intel Arc-specific settings for the error correction pipeline.
Import this instead of config.py when running on Intel Arc GPU.
"""
from error_correction.config import *  # Import all base config

# Intel Arc GPU Configuration
USE_INTEL_ARC = True  # Set to True when using Intel Arc GPU
INTEL_ARC_DEVICE = "xpu"  # Intel Extension for PyTorch device name

# Embedding Model Configuration for Intel Arc
# Option 1: Run embeddings on CPU (safest, slower)
EMBEDDING_DEVICE = "cpu"

# Option 2: Run embeddings on Intel Arc GPU (faster, needs ipex)
# Uncomment the line below if you have intel_extension_for_pytorch installed
# EMBEDDING_DEVICE = "xpu"

# Batch size for embeddings - reduce if running out of memory
EMBEDDING_BATCH_SIZE = 16  # Reduced from default 32 for Arc compatibility

# For very limited VRAM, further reduce:
# EMBEDDING_BATCH_SIZE = 8

# Intel Arc-specific embedding models (lighter alternatives if needed)
# These are smaller and may work better on Arc GPUs
LIGHTWEIGHT_SQL_MODELS = [
    "microsoft/codebert-base",           # Default, 768-dim
    "huggingface/CodeBERTa-small-v1",   # Smaller, 768-dim
    "bert-base-uncased",                 # General, 768-dim, lighter
]

# Use default CodeBERT unless memory issues
SQL_EMBEDDING_MODEL = LIGHTWEIGHT_SQL_MODELS[0]

# Mixed precision for Intel Arc (if supported)
USE_MIXED_PRECISION = False  # Set to True if ipex supports it

# Memory optimization
CLEAR_CACHE_AFTER_BATCH = True  # Clear cache after each embedding batch

print(f"Intel Arc Configuration Loaded:")
print(f"  - Embedding Device: {EMBEDDING_DEVICE}")
print(f"  - Embedding Model: {SQL_EMBEDDING_MODEL}")
print(f"  - Batch Size: {EMBEDDING_BATCH_SIZE}")
