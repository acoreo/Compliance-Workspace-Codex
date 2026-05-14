@echo off
setlocal

:: pull_fast_model.bat - Emergency Dell-side model pull into the USB Ollama store.
:: Preferred workflow: run Shared\cdw\scripts\mac\pull_fast_model_mac.sh on the Mac instead.
:: Default candidate: llama3.2:3b (~2 GB in Ollama library).

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"

set "OLLAMA=%USB%\Shared\bin\ollama.exe"
set "OLLAMA_MODELS=%USB%\Shared\models\ollama_data"
set "OLLAMA_HOST=127.0.0.1:11434"

if "%~1"=="" (
    set "MODEL=llama3.2:3b"
) else (
    set "MODEL=%~1"
)

echo ============================================================
echo   CDW Pull Fast Model
echo   USB root    : %USB%
echo   Model store : %OLLAMA_MODELS%
echo   Model       : %MODEL%
echo ============================================================
echo.

echo WARNING: This downloads a model from the Dell.
echo Preferred project workflow is Mac-side download, then run from USB on Dell.
echo To proceed anyway, set CDW_ALLOW_DELL_DOWNLOAD=1 and rerun this script.
echo.

if not "%CDW_ALLOW_DELL_DOWNLOAD%"=="1" (
    echo Blocked by default to avoid surprise Dell network downloads.
    echo Mac-side command:
    echo   /Volumes/BK-1/USB-Uncensored-LLM/Shared/cdw/scripts/mac/pull_fast_model_mac.sh
    pause
    exit /b 2
)

if not exist "%OLLAMA%" (
    echo ERROR: ollama.exe not found at:
    echo        %OLLAMA%
    pause
    exit /b 1
)

if not exist "%OLLAMA_MODELS%" (
    echo ERROR: Ollama model store not found at:
    echo        %OLLAMA_MODELS%
    echo        Re-sync the USB from the Mac using setup_usb.sh.
    pause
    exit /b 1
)

echo Pulling %MODEL% into the USB model store...
echo This requires internet access on the Dell the first time.
echo.
"%OLLAMA%" pull "%MODEL%"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo ERROR: ollama pull failed with exit code %RC%.
    pause
    exit /b %RC%
)

echo Model pull complete. Current models:
"%OLLAMA%" list
pause
exit /b 0
