@echo off
setlocal

:: benchmark_fast.bat - Benchmark the smaller CDW candidate model.
:: Default candidate: llama3.2:3b. Pass another model name to override.

set "SCRIPT_DIR=%~dp0"

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

call "%SCRIPT_DIR%benchmark_llm.bat" --calls warm --max-tokens 400 "%MODEL%"
exit /b %ERRORLEVEL%
