@echo off
REM Complete pipeline: Base Model + Error Correction
REM For deepseek-coder:6.7b on Ollama with Intel Arc GPU

echo =====================================================
echo Complete Pipeline: DAIL-SQL + Error Correction
echo Model: deepseek-coder:6.7b (Ollama)
echo =====================================================

REM ============================================================
REM CONFIGURATION - Edit these for your setup
REM ============================================================

set "MODEL=deepseek-coder:6.7b"
set "OLLAMA_BASE_URL=http://localhost:11434/v1"
set "OLLAMA_API_KEY=ollama"

REM Create safe filename version (replace : with _)
set "MODEL_FILE=%MODEL::=_%"

REM Dataset configuration
set "DATA_TYPE=spider"
set "SPLIT=test"
set "K_SHOT=3"
set "PROMPT_REPR=SQL"
set "EXAMPLE_TYPE=QA"
set "SELECTOR_TYPE=EUCDISQUESTIONMASK"
set "MAX_SEQ_LEN=4096"
set "MAX_ANS_LEN=200"

REM Error correction configuration
set "MAX_TRIPLETS=20"
set "TEMPERATURE=0.3"

REM ============================================================
REM STEP 0: Prerequisites Check
REM ============================================================

echo.
echo [Step 0] Checking prerequisites...
echo =====================================================

REM Check if Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Ollama is not running!
    echo.
    echo Please start Ollama in another terminal:
    echo   ollama serve
    echo.
    echo Then press any key to continue...
    pause >nul
    goto :check_ollama_again
)

:check_ollama_again
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo Still not running. Please start Ollama and try again.
    pause
    exit /b 1
)

echo ✓ Ollama is running

REM Check if model is available
echo.
echo Checking if model is available...
ollama list | findstr /C:"deepseek-coder" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Model not found. Pulling deepseek-coder:6.7b...
    echo This may take a while (4-6 GB download)...
    ollama pull deepseek-coder:6.7b
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to pull model
        pause
        exit /b 1
    )
) else (
    echo ✓ Model available
)

REM Check if Intel Arc test passed (optional)
echo.
set /p RUN_ARC_TEST="Run Intel Arc compatibility test? (y/n): "
if /i "%RUN_ARC_TEST%"=="y" (
    python error_correction\test_intel_arc.py
    echo.
    echo Press any key to continue with the pipeline...
    pause >nul
)

REM ============================================================
REM STEP 1: Data Preprocessing (if not already done)
REM ============================================================

echo.
echo [Step 1] Data Preprocessing
echo =====================================================

if not exist "dataset\process\SPIDER-%SPLIT%_%PROMPT_REPR%_%K_SHOT%-SHOT_%SELECTOR_TYPE%_%EXAMPLE_TYPE%-EXAMPLE_CTX-%MAX_ANS_LEN%_ANS-%MAX_SEQ_LEN%\questions.json" (
    echo Running data preprocessing...

    if not exist "dataset\spider\train_spider_processed.json" (
        echo Preprocessing training data...
        python data_preprocess.py
        if errorlevel 1 (
            echo ERROR: Data preprocessing failed
            pause
            exit /b 1
        )
    ) else (
        echo ✓ Data already preprocessed
    )

    REM Generate questions
    echo.
    echo Generating questions with %K_SHOT%-shot examples...
    python generate_question.py ^
        --data_type %DATA_TYPE% ^
        --split %SPLIT% ^
        --tokenizer %MODEL% ^
        --max_seq_len %MAX_SEQ_LEN% ^
        --max_ans_len %MAX_ANS_LEN% ^
        --prompt_repr %PROMPT_REPR% ^
        --k_shot %K_SHOT% ^
        --example_type %EXAMPLE_TYPE% ^
        --selector_type %SELECTOR_TYPE%

    if errorlevel 1 (
        echo ERROR: Question generation failed
        pause
        exit /b 1
    )
) else (
    echo ✓ Questions already generated
)

REM ============================================================
REM STEP 2: Run Base Model
REM ============================================================

echo.
echo [Step 2] Running Base DAIL-SQL Model
echo =====================================================
echo Model: %MODEL%
echo This will take some time depending on dataset size...
echo.

REM Set the dataset directory
set "DATASET_DIR=dataset\process\SPIDER-%SPLIT%_%PROMPT_REPR%_%K_SHOT%-SHOT_%SELECTOR_TYPE%_%EXAMPLE_TYPE%-EXAMPLE_CTX-%MAX_ANS_LEN%_ANS-%MAX_SEQ_LEN%"

REM Create results directory
if not exist "results" mkdir results

REM Check if results already exist
if exist "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" (
    echo.
    echo Results file already exists: %DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt
    set /p RERUN="Re-run base model? (y/n): "
    if /i not "%RERUN%"=="y" (
        echo Skipping base model run, using existing results
        goto :error_correction
    )
)

echo Running base model with Ollama...
python ask_llm.py ^
    --model %MODEL% ^
    --question %DATASET_DIR% ^
    --openai_api_key %OLLAMA_API_KEY% ^
    --openai_api_base %OLLAMA_BASE_URL% ^
    --temperature 0.0 ^
    --n 1

if errorlevel 1 (
    echo.
    echo ERROR: Base model run failed
    pause
    exit /b 1
)

echo.
echo ✓ Base model completed successfully!
echo Results saved to: %DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt
echo Evaluation saved to: results\eval_%MODEL_FILE%.txt

REM ============================================================
REM STEP 3: Run Error Correction Pipeline
REM ============================================================

:error_correction
echo.
echo [Step 3] Running Error Correction Pipeline
echo =====================================================
echo Processing up to %MAX_TRIPLETS% error triplets...
echo.

REM Check if results exist
if not exist "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" (
    echo ERROR: Results file not found. Please run base model first.
    pause
    exit /b 1
)

if not exist "results\eval_%MODEL_FILE%.txt" (
    echo ERROR: Evaluation file not found. Please run base model first.
    pause
    exit /b 1
)

echo Running error correction pipeline...
python error_correction\pipeline.py ^
    --eval_results results\eval_%MODEL_FILE%.txt ^
    --predictions_file %DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt ^
    --questions_file %DATASET_DIR%\questions.json ^
    --model %MODEL% ^
    --openai_api_key %OLLAMA_API_KEY% ^
    --openai_api_base %OLLAMA_BASE_URL% ^
    --temperature %TEMPERATURE% ^
    --max_triplets %MAX_TRIPLETS%

if errorlevel 1 (
    echo.
    echo ERROR: Error correction pipeline failed
    echo Check logs at: error_correction\pipeline.log
    pause
    exit /b 1
)

REM ============================================================
REM STEP 4: Display Results
REM ============================================================

echo.
echo =====================================================
echo Pipeline Completed Successfully!
echo =====================================================
echo.

echo Base Model Results:
echo   - Predictions: %DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt
echo   - Evaluation: results\eval_%MODEL_FILE%.txt
echo.

echo Error Correction Results:
echo   - Triplets: error_correction\rules\triplets.json
echo   - Clusters: error_correction\rules\clusters.json
echo   - Rules: error_correction\rules\rules.json
echo.

echo Vector Databases:
echo   - Correct queries: vector_sql_db\correct\
echo   - Incorrect queries: vector_sql_db\incorrect\
echo.

echo Logs:
echo   - Pipeline log: error_correction\pipeline.log
echo.

REM Display summary statistics
if exist "error_correction\rules\rules.json" (
    echo =====================================================
    echo Summary Statistics
    echo =====================================================

    for /f %%i in ('python -c "import json; print(len(json.load(open('error_correction/rules/rules.json'))))" 2^>nul') do set NUM_RULES=%%i
    for /f %%i in ('python -c "import json; print(len(json.load(open('error_correction/rules/triplets.json'))))" 2^>nul') do set NUM_TRIPLETS=%%i
    for /f %%i in ('python -c "import json; print(len(json.load(open('error_correction/rules/clusters.json'))))" 2^>nul') do set NUM_CLUSTERS=%%i

    echo Total Triplets Generated: %NUM_TRIPLETS%
    echo Total Clusters Created: %NUM_CLUSTERS%
    echo Total Validated Rules: %NUM_RULES%
    echo.
)

REM Display base model accuracy
echo Base Model Accuracy:
findstr /C:"Final Execution Accuracy" results\eval_%MODEL_FILE%.txt

echo.
echo =====================================================
echo Next Steps:
echo =====================================================
echo.
echo 1. Review error triplets:
echo    type error_correction\rules\triplets.json
echo.
echo 2. Examine generated rules:
echo    type error_correction\rules\rules.json
echo.
echo 3. View detailed logs:
echo    type error_correction\pipeline.log
echo.
echo 4. Run with more triplets (remove --max_triplets limit):
echo    Edit this script and set MAX_TRIPLETS=999999
echo.

pause
