@echo off
setlocal

:: start_ollama.bat - Start Ollama using the CDW model store on the USB.
:: Run this instead of calling ollama.exe serve directly.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"

set "OLLAMA=%USB%\Shared\bin\ollama.exe"
set "OLLAMA_MODELS=%USB%\Shared\models\ollama_data"
set "OLLAMA_HOST=127.0.0.1:11434"

echo ============================================================
echo   CDW Ollama Server
echo   USB root      : %USB%
echo   Ollama binary : %OLLAMA%
echo   Model store   : %OLLAMA_MODELS%
echo   Host          : %OLLAMA_HOST%
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

echo Starting Ollama with the CDW USB model store...
echo Leave this window open while running CDW or benchmark_llm.bat.
echo.
"%OLLAMA%" serve

set "RC=%ERRORLEVEL%"
echo.
echo Ollama exited with code %RC%.
pause
exit /b %RC%
