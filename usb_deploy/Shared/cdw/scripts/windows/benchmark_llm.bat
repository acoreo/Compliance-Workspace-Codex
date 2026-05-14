@echo off
setlocal

:: benchmark_llm.bat - Run the CDW Ollama benchmark from any USB drive letter.
:: This script resolves paths relative to itself:
::   <USB root>\Shared\cdw\scripts\windows\benchmark_llm.bat

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"

set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "OLLAMA=%USB%\Shared\bin\ollama.exe"
set "OLLAMA_MODELS=%USB%\Shared\models\ollama_data"
set "OLLAMA_HOST=127.0.0.1:11434"
set "BENCH=%USB%\Shared\cdw\projects\cdw\compliance_workspace\tools\benchmark_llm.py"

if "%~1"=="" (
    set "BENCH_ARGS=nemomix-local"
) else (
    set "BENCH_ARGS=%*"
)

echo ============================================================
echo   CDW LLM Benchmark
echo   USB root : %USB%
echo   Args     : %BENCH_ARGS%
echo   Store    : %OLLAMA_MODELS%
echo ============================================================
echo.

if not exist "%PYTHON%" (
    echo ERROR: Python not found at:
    echo        %PYTHON%
    pause
    exit /b 1
)

if not exist "%OLLAMA%" (
    echo ERROR: ollama.exe not found at:
    echo        %OLLAMA%
    pause
    exit /b 1
)

if not exist "%BENCH%" (
    echo ERROR: benchmark_llm.py not found at:
    echo        %BENCH%
    echo        Re-sync the USB from the Mac using setup_usb.sh.
    pause
    exit /b 1
)

curl -s -o NUL -w "%%{http_code}" "http://127.0.0.1:11434" 2>nul | findstr /C:"200" >nul
if errorlevel 1 (
    echo ERROR: Ollama is not running at http://127.0.0.1:11434.
    echo        Open another Command Prompt and run:
    echo        %SCRIPT_DIR%start_ollama.bat
    pause
    exit /b 1
)

"%PYTHON%" "%BENCH%" --ollama-bin "%OLLAMA%" %BENCH_ARGS%
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo Benchmark failed with exit code %RC%.
)
pause
exit /b %RC%
