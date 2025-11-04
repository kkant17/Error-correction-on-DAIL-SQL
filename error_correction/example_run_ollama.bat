@echo off
REM Example script to run error correction pipeline with Ollama (Windows)

REM Configuration
set MODEL=deepseek-coder:6.7b
set OLLAMA_BASE_URL=http://localhost:11434/v1
set OLLAMA_API_KEY=ollama
set DATASET_DIR=.\dataset\process\SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096
set RESULTS_DIR=.\results

echo =====================================================
echo Running Error Correction Pipeline with Ollama
echo Model: %MODEL%
echo =====================================================

REM Check if Ollama is running
echo.
echo Checking Ollama status...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo Error: Ollama is not running!
    echo Please start Ollama first in another terminal:
    echo   ollama serve
    pause
    exit /b 1
)

echo Ollama is running √

REM Check if model is available
echo.
echo Checking if model '%MODEL%' is available...
ollama list | findstr /C:"%MODEL%" >nul
if errorlevel 1 (
    echo Model not found. Pulling %MODEL%...
    ollama pull %MODEL%
) else (
    echo Model available √
)

REM Step 1: Run base DAIL-SQL with Ollama
echo.
echo Step 1: Running base DAIL-SQL model with Ollama...
echo Note: Skip this if you already have predictions and evaluations
set /p RUN_BASE="Run base model? (y/n): "

if /i "%RUN_BASE%"=="y" (
    python ask_llm.py ^
        --model %MODEL% ^
        --question %DATASET_DIR% ^
        --openai_api_key %OLLAMA_API_KEY% ^
        --openai_api_base %OLLAMA_BASE_URL% ^
        --temperature 0.7 ^
        --n 1
)

REM Step 2: Run error correction pipeline
echo.
echo Step 2: Running error correction pipeline with Ollama...

REM For testing with local models, limit to fewer triplets
set MAX_TRIPLETS=10
set TEMPERATURE=0.3

REM Replace colons in model name for file paths
set MODEL_FILE=%MODEL::=_%

python error_correction\pipeline.py ^
    --eval_results %RESULTS_DIR%\eval_%MODEL_FILE%.txt ^
    --predictions_file %DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt ^
    --questions_file %DATASET_DIR%\questions.json ^
    --model %MODEL% ^
    --openai_api_key %OLLAMA_API_KEY% ^
    --openai_api_base %OLLAMA_BASE_URL% ^
    --temperature %TEMPERATURE% ^
    --max_triplets %MAX_TRIPLETS%

REM Check results
echo.
echo =====================================================
echo Pipeline completed!
echo =====================================================
echo.
echo Results saved to:
echo   - error_correction\rules\triplets.json
echo   - error_correction\rules\clusters.json
echo   - error_correction\rules\rules.json
echo.
echo Vector databases created in:
echo   - vector_sql_db\correct\
echo   - vector_sql_db\incorrect\
echo.
echo View logs at:
echo   - error_correction\pipeline.log
echo.

REM Display summary if files exist
if exist "error_correction\rules\rules.json" (
    for /f %%i in ('python -c "import json; print(len(json.load(open('error_correction/rules/rules.json'))))"') do set NUM_RULES=%%i
    echo Total validated rules: %NUM_RULES%
)

if exist "error_correction\rules\triplets.json" (
    for /f %%i in ('python -c "import json; print(len(json.load(open('error_correction/rules/triplets.json'))))"') do set NUM_TRIPLETS=%%i
    echo Total triplets generated: %NUM_TRIPLETS%
)

if exist "error_correction\rules\clusters.json" (
    for /f %%i in ('python -c "import json; print(len(json.load(open('error_correction/rules/clusters.json'))))"') do set NUM_CLUSTERS=%%i
    echo Total clusters created: %NUM_CLUSTERS%
)

echo.
echo =====================================================
echo Tips for using Ollama models:
echo =====================================================
echo.
echo 1. Recommended models for SQL tasks:
echo    - deepseek-coder:6.7b (good for code/SQL)
echo    - codellama:7b (optimized for code)
echo    - mistral:7b (general purpose)
echo    - qwen2.5-coder:7b (good for code)
echo.
echo 2. Pull a model:
echo    ollama pull deepseek-coder:6.7b
echo.
echo 3. List available models:
echo    ollama list
echo.
echo 4. For better GPU performance:
echo    - Ensure CUDA is properly installed
echo    - Check: nvidia-smi
echo.

pause
