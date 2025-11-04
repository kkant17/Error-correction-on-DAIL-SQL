#!/bin/bash
# Setup script for Error Correction Pipeline

echo "====================================================="
echo "Error Correction Pipeline Setup"
echo "====================================================="

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "Error: Python is not installed"
    exit 1
fi

echo "Python version: $(python --version)"

# Install requirements
echo ""
echo "Installing additional requirements..."
pip install -r error_correction/requirements.txt

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p vector_sql_db/correct
mkdir -p vector_sql_db/incorrect
mkdir -p error_correction/rules
mkdir -p results

echo ""
echo "Directory structure:"
tree -L 2 error_correction/ 2>/dev/null || ls -R error_correction/

# Check if CUDA is available
echo ""
echo "Checking for GPU support..."
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"

echo ""
echo "====================================================="
echo "Setup completed successfully!"
echo "====================================================="
echo ""
echo "Next steps:"
echo "1. Run base DAIL-SQL to generate predictions and evaluations"
echo "2. Run: python error_correction/pipeline.py --help"
echo ""
