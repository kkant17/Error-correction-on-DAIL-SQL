"""
Test script to verify Intel Arc GPU compatibility for error correction pipeline
"""
import sys
import torch
import numpy as np


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_pytorch():
    """Test PyTorch installation"""
    print_section("PyTorch Installation")
    print(f"PyTorch version: {torch.__version__}")
    print(f"✅ PyTorch installed")


def test_intel_arc():
    """Test Intel Arc GPU detection"""
    print_section("Intel Arc GPU Detection")

    # Check for Intel Extension for PyTorch
    try:
        import intel_extension_for_pytorch as ipex
        print(f"✅ Intel Extension for PyTorch installed: {ipex.__version__}")
        ipex_available = True
    except ImportError:
        print("⚠️  Intel Extension for PyTorch NOT installed")
        print("   Embeddings will run on CPU (still works fine!)")
        ipex_available = False

    # Check for XPU device
    if hasattr(torch, 'xpu'):
        try:
            if torch.xpu.is_available():
                print(f"✅ Intel Arc GPU detected!")
                print(f"   Device count: {torch.xpu.device_count()}")
                for i in range(torch.xpu.device_count()):
                    print(f"   Device {i}: {torch.xpu.get_device_name(i)}")
                return True
            else:
                print("❌ XPU available but no Intel Arc GPU detected")
                return False
        except Exception as e:
            print(f"❌ Error checking XPU: {e}")
            return False
    else:
        if ipex_available:
            print("⚠️  torch.xpu not available (might need driver update)")
        else:
            print("ℹ️  XPU not available (ipex not installed)")
        return False


def test_fallback_devices():
    """Test fallback devices"""
    print_section("Available Devices")

    # Check CUDA
    if torch.cuda.is_available():
        print(f"✅ CUDA available: {torch.cuda.get_device_name(0)}")
    else:
        print("ℹ️  CUDA not available")

    # CPU is always available
    print("✅ CPU available")


def test_embedder():
    """Test the SQL embedder with device detection"""
    print_section("Testing SQL Embedder")

    try:
        # Import after we've checked dependencies
        from error_correction.vector_store import SQLEmbedder

        print("Initializing SQLEmbedder (auto-detect device)...")
        embedder = SQLEmbedder()

        print(f"✅ Embedder initialized")
        print(f"   Device: {embedder.device}")
        print(f"   Model: {embedder.model_name}")

        # Test embedding generation
        print("\nTesting embedding generation...")
        test_query = "SELECT name, age FROM users WHERE age > 18"
        embedding = embedder.embed_query(test_query)

        print(f"✅ Embedding generated successfully")
        print(f"   Shape: {embedding.shape}")
        print(f"   Dtype: {embedding.dtype}")

        # Test batch embedding
        print("\nTesting batch embedding...")
        test_queries = [
            "SELECT * FROM users",
            "SELECT COUNT(*) FROM orders",
            "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id"
        ]
        batch_embeddings = embedder.embed_batch(test_queries, batch_size=2)

        print(f"✅ Batch embedding successful")
        print(f"   Shape: {batch_embeddings.shape}")
        print(f"   Expected: ({len(test_queries)}, {embedder.model.config.hidden_size})")

        return True

    except Exception as e:
        print(f"❌ Error testing embedder: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_transformers():
    """Test transformers library"""
    print_section("Transformers Library")

    try:
        import transformers
        print(f"✅ Transformers installed: {transformers.__version__}")
        return True
    except ImportError:
        print("❌ Transformers not installed")
        print("   Install with: pip install transformers")
        return False


def test_faiss():
    """Test FAISS library"""
    print_section("FAISS Vector Database")

    try:
        import faiss
        print(f"✅ FAISS installed: {faiss.__version__}")

        # Test basic FAISS operations
        dimension = 768
        index = faiss.IndexFlatL2(dimension)

        # Add some random vectors
        vectors = np.random.rand(10, dimension).astype('float32')
        index.add(vectors)

        print(f"✅ FAISS basic test passed")
        print(f"   Index size: {index.ntotal}")
        return True

    except ImportError:
        print("❌ FAISS not installed")
        print("   Install with: pip install faiss-cpu")
        return False
    except Exception as e:
        print(f"❌ Error testing FAISS: {e}")
        return False


def print_recommendations(has_intel_arc):
    """Print recommendations based on detected hardware"""
    print_section("Recommendations")

    if has_intel_arc:
        print("✅ Your system is configured for Intel Arc GPU!")
        print("\nRecommended configuration:")
        print("  - LLM: Use ipex-llm via Ollama on Intel Arc (you're already doing this)")
        print("  - Embeddings: Auto-detect will use Intel Arc (XPU)")
        print("  - Vector DB: Will use CPU (optimal)")
        print("\nTo run the pipeline:")
        print("  python error_correction/pipeline.py \\")
        print("    --model qwen2.5:7b \\")
        print("    --openai_api_key ollama \\")
        print("    --openai_api_base http://localhost:11434/v1 \\")
        print("    --eval_results results/eval_model.txt \\")
        print("    --predictions_file .../RESULTS_MODEL-model.txt \\")
        print("    --questions_file .../questions.json")
    else:
        print("ℹ️  Intel Arc GPU not detected or not available")
        print("\nThis is OK! The pipeline will work with CPU embeddings:")
        print("  - LLM: Still uses ipex-llm via Ollama (fast)")
        print("  - Embeddings: Will use CPU (slightly slower but stable)")
        print("  - Vector DB: Will use CPU (optimal)")
        print("\nTo force CPU embeddings (recommended without Arc):")
        print("  export EMBEDDING_DEVICE=cpu")
        print("  python error_correction/pipeline.py ...")

    print("\nFor more details, see:")
    print("  - error_correction/INTEL_ARC_SETUP.md")
    print("  - error_correction/README.md")


def main():
    """Run all tests"""
    print("="*60)
    print("  Intel Arc GPU Compatibility Test")
    print("  Error Correction Pipeline for DAIL-SQL")
    print("="*60)

    results = {}

    # Run tests
    test_pytorch()
    results['intel_arc'] = test_intel_arc()
    test_fallback_devices()
    results['transformers'] = test_transformers()
    results['faiss'] = test_faiss()

    # Test embedder if dependencies available
    if results['transformers']:
        results['embedder'] = test_embedder()
    else:
        results['embedder'] = False
        print_section("Testing SQL Embedder")
        print("⚠️  Skipped (transformers not installed)")

    # Print summary
    print_section("Test Summary")
    print(f"PyTorch: ✅")
    print(f"Intel Arc GPU: {'✅' if results['intel_arc'] else '⚠️  (will use CPU)'}")
    print(f"Transformers: {'✅' if results['transformers'] else '❌'}")
    print(f"FAISS: {'✅' if results['faiss'] else '❌'}")
    print(f"SQL Embedder: {'✅' if results['embedder'] else '⚠️  (needs setup)'}")

    all_pass = all([
        results['transformers'],
        results['faiss'],
    ])

    if all_pass and results['embedder']:
        print("\n✅ All systems ready! Pipeline is fully operational.")
    elif all_pass:
        print("\n⚠️  Basic dependencies OK, but embedder needs attention.")
        print("   Run: pip install -r error_correction/requirements.txt")
    else:
        print("\n❌ Some dependencies missing. Please install:")
        if not results['transformers']:
            print("   - pip install transformers torch")
        if not results['faiss']:
            print("   - pip install faiss-cpu")

    # Print recommendations
    print_recommendations(results['intel_arc'])

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
