@echo off
REM Incremental Error Correction Pipeline Runner
REM Processes queries one-by-one with online learning

echo ========================================
echo Incremental Error Correction Pipeline
echo ========================================

REM Check if OpenAI API key is set
if "%OPENAI_API_KEY%"=="" (
    echo ERROR: OPENAI_API_KEY environment variable not set
    echo Please set it with: set OPENAI_API_KEY=your_key_here
    exit /b 1
)

REM Default paths (modify as needed)
set EVAL_RESULTS=results\eval.txt
set PREDICTIONS=results\predict.txt
set QUESTIONS=dataset\dev.json
set DB_ID=spider
set MODEL=gpt-4
set OUTPUT=results\corrected_predictions.txt

echo.
echo Configuration:
echo   Eval Results: %EVAL_RESULTS%
echo   Predictions:  %PREDICTIONS%
echo   Questions:    %QUESTIONS%
echo   Database:     %DB_ID%
echo   Model:        %MODEL%
echo   Output:       %OUTPUT%
echo.

REM Run incremental pipeline with transformation enabled
python run_incremental_pipeline.py ^
    --eval_results %EVAL_RESULTS% ^
    --predictions_file %PREDICTIONS% ^
    --questions_file %QUESTIONS% ^
    --db_id %DB_ID% ^
    --model %MODEL% ^
    --openai_api_key %OPENAI_API_KEY% ^
    --enable_transformation ^
    --output_file %OUTPUT%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Pipeline completed successfully!
    echo ========================================
    echo.
    echo Results saved to:
    echo   - error_correction\rules\triplets.json
    echo   - error_correction\rules\clusters.json
    echo   - error_correction\rules\rules.json
    echo   - error_correction\rules\incremental_metrics.json
    echo   - error_correction\rules\pipeline_summary.json
    echo   - %OUTPUT%
    echo.
) else (
    echo.
    echo ========================================
    echo Pipeline failed with error code %ERRORLEVEL%
    echo Check incremental_pipeline.log for details
    echo ========================================
    exit /b %ERRORLEVEL%
)
