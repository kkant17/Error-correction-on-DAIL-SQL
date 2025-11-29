@echo off
REM Full Pipeline: Base Model Generation + Evaluation + Error Correction
REM 
REM Usage:
REM   run_full_pipeline.bat                           # Use existing predictions
REM   run_full_pipeline.bat --run_base_model          # Generate new predictions first
REM   run_full_pipeline.bat codellama:7b 60           # Custom model and queries
REM   run_full_pipeline.bat codellama:7b 60 --run_base_model
REM
REM Example:
REM   run_full_pipeline.bat codellama:7b 60 --run_base_model

setlocal enabledelayedexpansion

REM Default values
set MODEL=codellama:7b
set MAX_QUERIES=60
set RUN_BASE=

REM Parse arguments
set ARG1=%~1
set ARG2=%~2
set ARG3=%~3

REM Check for --run_base_model flag anywhere
if "%ARG1%"=="--run_base_model" set RUN_BASE=--run_base_model
if "%ARG2%"=="--run_base_model" set RUN_BASE=--run_base_model
if "%ARG3%"=="--run_base_model" set RUN_BASE=--run_base_model

REM Set model and max_queries if provided (and not flags)
if not "%ARG1%"=="" if not "%ARG1%"=="--run_base_model" set MODEL=%ARG1%
if not "%ARG2%"=="" if not "%ARG2%"=="--run_base_model" set MAX_QUERIES=%ARG2%

echo ========================================
echo Full Pipeline: Base Model + Error Correction
echo ========================================
echo Model: %MODEL%
echo Max Queries: %MAX_QUERIES%
echo Run Base Model: %RUN_BASE%
echo.

REM Check if Ollama is running (for local models)
echo Checking Ollama connection...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not running at localhost:11434
    echo Start Ollama first: ollama serve
    echo.
    if not "%RUN_BASE%"=="" (
        echo Cannot run base model without Ollama!
        pause
        exit /b 1
    )
)

REM Run the pipeline
python run_full_pipeline.py --model %MODEL% --max_queries %MAX_QUERIES% %RUN_BASE%

echo.
echo ========================================
echo Pipeline complete!
echo ========================================
pause

