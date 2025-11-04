@echo off
REM Comparison Pipeline: Run base model and analyze with error correction
REM Stores results separately for comparison

echo =====================================================
echo Comparison Pipeline: Base vs Error-Corrected
echo Model: deepseek-coder:6.7b (Ollama)
echo =====================================================

REM ============================================================
REM CONFIGURATION
REM ============================================================

set "MODEL=deepseek-coder:6.7b"
set "OLLAMA_BASE_URL=http://localhost:11434/v1"
set "OLLAMA_API_KEY=ollama"
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

REM Output directories
set "RESULTS_BASE_ONLY=results\base_only"
set "RESULTS_WITH_CORRECTION=results\with_error_correction"

REM ============================================================
REM SETUP
REM ============================================================

echo.
echo Creating result directories...
if not exist "%RESULTS_BASE_ONLY%" mkdir "%RESULTS_BASE_ONLY%"
if not exist "%RESULTS_WITH_CORRECTION%" mkdir "%RESULTS_WITH_CORRECTION%"
if not exist "error_correction\rules" mkdir "error_correction\rules"

echo ✓ Directories created

REM ============================================================
REM STEP 0: Prerequisites Check
REM ============================================================

echo.
echo [Step 0] Checking prerequisites...
echo =====================================================

curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ERROR: Ollama is not running!
    echo Please start Ollama: ollama serve
    pause
    exit /b 1
)
echo ✓ Ollama is running

ollama list | findstr /C:"deepseek-coder" >nul 2>&1
if errorlevel 1 (
    echo Pulling model...
    ollama pull deepseek-coder:6.7b
)
echo ✓ Model available

REM ============================================================
REM STEP 1: Data Preprocessing
REM ============================================================

set "DATASET_DIR=dataset\process\SPIDER-%SPLIT%_%PROMPT_REPR%_%K_SHOT%-SHOT_%SELECTOR_TYPE%_%EXAMPLE_TYPE%-EXAMPLE_CTX-%MAX_ANS_LEN%_ANS-%MAX_SEQ_LEN%"

echo.
echo [Step 1] Data Preprocessing
echo =====================================================

if not exist "%DATASET_DIR%\questions.json" (
    echo Running preprocessing...

    if not exist "dataset\spider\train_spider_processed.json" (
        python data_preprocess.py
        if errorlevel 1 (
            echo ERROR: Preprocessing failed
            pause
            exit /b 1
        )
    )

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
    echo ✓ Data already preprocessed
)

REM ============================================================
REM STEP 2: RUN #1 - Base Model Only (No Error Correction)
REM ============================================================

echo.
echo =====================================================
echo RUN #1: Base Model Only (No Error Correction)
echo =====================================================
echo.

set "BASE_PRED_FILE=%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%_base_only.txt"
set "BASE_EVAL_FILE=%RESULTS_BASE_ONLY%\eval_%MODEL_FILE%.txt"

if exist "%BASE_PRED_FILE%" (
    echo Results already exist: %BASE_PRED_FILE%
    set /p RERUN_BASE="Re-run base model? (y/n): "
    if /i not "%RERUN_BASE%"=="y" (
        echo Skipping base model run
        goto :run_with_correction
    )
)

echo Running base model (no error correction)...
echo This will take 30-60 minutes...
echo.

REM Temporarily move existing results if they exist
if exist "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" (
    move "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt.tmp" >nul 2>&1
)
if exist "results\eval_%MODEL_FILE%.txt" (
    move "results\eval_%MODEL_FILE%.txt" "results\eval_%MODEL_FILE%.txt.tmp" >nul 2>&1
)

python ask_llm.py ^
    --model %MODEL% ^
    --question %DATASET_DIR% ^
    --openai_api_key %OLLAMA_API_KEY% ^
    --openai_api_base %OLLAMA_BASE_URL% ^
    --temperature 0.0 ^
    --n 1

if errorlevel 1 (
    echo ERROR: Base model run failed
    pause
    exit /b 1
)

REM Copy results to base_only directory
copy "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" "%BASE_PRED_FILE%" >nul
copy "results\eval_%MODEL_FILE%.txt" "%BASE_EVAL_FILE%" >nul

echo ✓ Base model completed
echo   Results: %BASE_PRED_FILE%
echo   Evaluation: %BASE_EVAL_FILE%
echo.

REM Display base accuracy
echo Base Model Accuracy (No Error Correction):
findstr /C:"Final Execution Accuracy" "%BASE_EVAL_FILE%"
echo.

REM ============================================================
REM STEP 3: RUN #2 - With Error Correction Analysis
REM ============================================================

:run_with_correction
echo.
echo =====================================================
echo RUN #2: Error Correction Analysis
echo =====================================================
echo.

set "CORR_PRED_FILE=%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%_with_correction.txt"
set "CORR_EVAL_FILE=%RESULTS_WITH_CORRECTION%\eval_%MODEL_FILE%.txt"

REM Use the base results for error correction analysis
if not exist "%BASE_PRED_FILE%" (
    echo ERROR: Base results not found. Run base model first.
    pause
    exit /b 1
)

REM Copy base results to standard location for error correction pipeline
copy "%BASE_PRED_FILE%" "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" >nul
copy "%BASE_EVAL_FILE%" "results\eval_%MODEL_FILE%.txt" >nul

echo Running error correction pipeline...
echo Analyzing errors and generating rules...
echo.

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
    echo ERROR: Error correction pipeline failed
    echo Check logs: error_correction\pipeline.log
    pause
    exit /b 1
)

REM Copy results to with_correction directory
copy "%DATASET_DIR%\RESULTS_MODEL-%MODEL_FILE%.txt" "%CORR_PRED_FILE%" >nul
copy "results\eval_%MODEL_FILE%.txt" "%CORR_EVAL_FILE%" >nul

REM Copy error correction artifacts
xcopy "error_correction\rules" "%RESULTS_WITH_CORRECTION%\rules\" /E /I /Y >nul

echo ✓ Error correction analysis completed
echo.

REM ============================================================
REM STEP 4: Display Comparison Results
REM ============================================================

echo.
echo =====================================================
echo COMPARISON RESULTS
echo =====================================================
echo.

echo RUN #1: Base Model Only (No Error Correction)
echo   - Predictions: %BASE_PRED_FILE%
echo   - Evaluation: %BASE_EVAL_FILE%
findstr /C:"Final Execution Accuracy" "%BASE_EVAL_FILE%"
echo.

echo RUN #2: With Error Correction Analysis
echo   - Predictions: %CORR_PRED_FILE%
echo   - Evaluation: %CORR_EVAL_FILE%
echo   - Rules: %RESULTS_WITH_CORRECTION%\rules\rules.json
echo   - Triplets: %RESULTS_WITH_CORRECTION%\rules\triplets.json
echo   - Clusters: %RESULTS_WITH_CORRECTION%\rules\clusters.json
findstr /C:"Final Execution Accuracy" "%CORR_EVAL_FILE%"
echo.

REM Display error correction statistics
if exist "%RESULTS_WITH_CORRECTION%\rules\rules.json" (
    echo Error Correction Statistics:
    for /f %%i in ('python -c "import json; print(len(json.load(open('%RESULTS_WITH_CORRECTION%/rules/rules.json'))))" 2^>nul') do set NUM_RULES=%%i
    for /f %%i in ('python -c "import json; print(len(json.load(open('%RESULTS_WITH_CORRECTION%/rules/triplets.json'))))" 2^>nul') do set NUM_TRIPLETS=%%i
    for /f %%i in ('python -c "import json; print(len(json.load(open('%RESULTS_WITH_CORRECTION%/rules/clusters.json'))))" 2^>nul') do set NUM_CLUSTERS=%%i

    echo   - Triplets analyzed: %NUM_TRIPLETS%
    echo   - Clusters created: %NUM_CLUSTERS%
    echo   - Rules generated: %NUM_RULES%
    echo.
)

echo =====================================================
echo Directory Structure:
echo =====================================================
echo.
echo results\
echo ├── base_only\
echo │   └── eval_%MODEL_FILE%.txt
echo └── with_error_correction\
echo     ├── eval_%MODEL_FILE%.txt
echo     └── rules\
echo         ├── triplets.json
echo         ├── clusters.json
echo         └── rules.json
echo.

echo =====================================================
echo Next Steps:
echo =====================================================
echo.
echo 1. Compare the two evaluations:
echo    fc %BASE_EVAL_FILE% %CORR_EVAL_FILE%
echo.
echo 2. Review generated rules:
echo    type %RESULTS_WITH_CORRECTION%\rules\rules.json
echo.
echo 3. Analyze error patterns:
echo    type %RESULTS_WITH_CORRECTION%\rules\triplets.json
echo.
echo 4. Generate comparison report:
echo    python compare_results.py
echo.
echo NOTE: Error correction currently generates rules but does not
echo       apply them to correct queries. The predictions are the same
echo       in both runs - the difference is in the analysis and rules.
echo.
echo To actually apply corrections, see: error_correction\README.md
echo.

pause
