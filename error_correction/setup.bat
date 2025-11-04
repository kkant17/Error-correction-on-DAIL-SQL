@echo off
REM Setup script for Error Correction Pipeline (Windows)

echo =====================================================
echo Error Correction Pipeline Setup
echo =====================================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed
    exit /b 1
)

echo Python version:
python --version

REM Install requirements
echo.
echo Installing additional requirements...
pip install -r error_correction\requirements.txt

REM Create necessary directories
echo.
echo Creating directories...
if not exist "vector_sql_db\correct" mkdir vector_sql_db\correct
if not exist "vector_sql_db\incorrect" mkdir vector_sql_db\incorrect
if not exist "error_correction\rules" mkdir error_correction\rules
if not exist "results" mkdir results

echo.
echo Directory structure created:
dir /s /b error_correction

REM Check if CUDA is available
echo.
echo Checking for GPU support...
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"

echo.
echo =====================================================
echo Setup completed successfully!
echo =====================================================
echo.
echo Next steps:
echo 1. Run base DAIL-SQL to generate predictions and evaluations
echo 2. Run: python error_correction\pipeline.py --help
echo.
pause
