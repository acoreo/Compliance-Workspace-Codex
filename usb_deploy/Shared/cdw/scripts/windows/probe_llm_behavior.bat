@echo off
setlocal

:: probe_llm_behavior.bat - Run safe behavior/boundary probes against a local model.
:: Default model: llama3.2:3b. Pass another model name to override.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"

set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "PROBE=%USB%\Shared\cdw\projects\cdw\compliance_workspace\tools\probe_llm_behavior.py"
set "LOG_DIR=%USB%\Shared\cdw\run_logs"
set "LOG_APPEND=%LOG_DIR%\probe_llm_behavior.log"
set "LOG_LATEST=%LOG_DIR%\latest_probe_llm_behavior.log"
set "RAW_LOG=%LOG_DIR%\behavior_probe_raw.jsonl"

if "%~1"=="" (
    set "MODEL=llama3.2:3b"
) else (
    set "MODEL=%~1"
)

echo ============================================================
echo   CDW LLM Behavior Probe
echo   USB root : %USB%
echo   Model    : %MODEL%
echo ============================================================
echo.

if not exist "%PYTHON%" (
    echo ERROR: Python not found at:
    echo        %PYTHON%
    pause
    exit /b 1
)

if not exist "%PROBE%" (
    echo ERROR: probe_llm_behavior.py not found at:
    echo        %PROBE%
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

mkdir "%LOG_DIR%" 2>nul
echo Writing console log to:
echo   %LOG_APPEND%
echo   %LOG_LATEST%
echo Writing raw JSONL to:
echo   %RAW_LOG%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "& { & '%PYTHON%' '%PROBE%' --raw-log '%RAW_LOG%' '%MODEL%' 2>&1 | Tee-Object -FilePath '%LOG_APPEND%' -Append | Tee-Object -FilePath '%LOG_LATEST%'; exit $LASTEXITCODE }"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo Behavior probe failed with exit code %RC%.
)
pause
exit /b %RC%
