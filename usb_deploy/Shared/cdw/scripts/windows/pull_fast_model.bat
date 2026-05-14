@echo off
setlocal

:: pull_fast_model.bat - Pull a smaller benchmark model into the USB Ollama store.
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
