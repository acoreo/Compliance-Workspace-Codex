@echo off
setlocal

:: benchmark_fast.bat - Benchmark the smaller CDW candidate model.
:: Default candidate: llama3.2:3b. Pass another model name to override.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"
set "LOG_DIR=%USB%\Shared\cdw\run_logs"
set "LOG_APPEND=%LOG_DIR%\benchmark_fast.log"
set "LOG_LATEST=%LOG_DIR%\latest_benchmark_fast.log"
set "RAW_LOG=%LOG_DIR%\benchmark_raw.jsonl"

if "%~1"=="" (
    set "MODEL=llama3.2:3b"
) else (
    set "MODEL=%~1"
)

echo ============================================================
echo   CDW Fast-Model Benchmark
echo   Model: %MODEL%
echo   Calls: warm only
echo ============================================================
echo.

mkdir "%LOG_DIR%" 2>nul
echo Writing console log to:
echo   %LOG_APPEND%
echo   %LOG_LATEST%
echo Writing raw JSONL to:
echo   %RAW_LOG%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "& { & '%SCRIPT_DIR%benchmark_llm.bat' --api ollama --calls warm --max-tokens 400 --raw-log '%RAW_LOG%' '%MODEL%' 2>&1 | Tee-Object -FilePath '%LOG_APPEND%' -Append | Tee-Object -FilePath '%LOG_LATEST%'; exit $LASTEXITCODE }"
exit /b %ERRORLEVEL%
