@echo off
setlocal enabledelayedexpansion

:: start_cdw.bat — CDW daily launcher for Windows
:: Resolves paths relative to this script so any drive letter works.
:: Double-click this file or run it from CMD — no other setup needed after first run.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "OLLAMA=%USB%\Shared\bin\ollama.exe"
set "OLLAMA_MODELS=%USB%\Shared\models\ollama_data"
set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_URL=http://127.0.0.1:11434"
set "CDW_SRC=%USB%\Shared\cdw\projects\cdw"
set "CDW_MAIN=%CDW_SRC%\compliance_workspace\main.py"
set "DONE_FLAG=%USB%\Shared\cdw\done.flag"
set "INSTALL_SCRIPT=%~dp0install_offline.bat"
set "OLLAMA_SCRIPT=%~dp0start_ollama.bat"

echo ============================================================
echo   CDW Launcher
echo   USB root : %USB%
echo ============================================================
echo.

:: Verify Python is present — catch a corrupted or missing install early
if not exist "%PYTHON%" (
    echo ERROR: python.exe not found at:
    echo        %PYTHON%
    echo        The USB may be missing files. Run the offline installer manually:
    echo        %INSTALL_SCRIPT%
    pause
    exit /b 1
)

:: Verify main.py is present
if not exist "%CDW_MAIN%" (
    echo ERROR: CDW source not found at:
    echo        %CDW_MAIN%
    echo        Re-sync the USB from the Mac using setup_usb.sh.
    pause
    exit /b 1
)

:: ── Step 1: Offline install (first run only) ──────────────────────────────────
if not exist "%DONE_FLAG%" (
    echo [1/3] First-time setup — running offline installer...
    call "%INSTALL_SCRIPT%"
    if errorlevel 1 (
        echo ERROR: Installation failed. See messages above.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Offline install already done ^(delete %DONE_FLAG% to re-run^).
)

:: ── Step 2: Start Ollama if not already running ───────────────────────────────
echo.
echo [2/3] Checking Ollama...
curl -s -o NUL -w "%%{http_code}" "%OLLAMA_URL%" 2>nul | findstr /C:"200" >nul
if not errorlevel 1 (
    echo       Ollama already running.
    goto LAUNCH_CDW
)

if not exist "%OLLAMA%" (
    echo ERROR: ollama.exe not found at:
    echo        %OLLAMA%
    echo        Re-sync the USB from the Mac using setup_usb.sh.
    pause
    exit /b 1
)

echo       Starting Ollama (model store: %OLLAMA_MODELS%)...
start "Ollama - CDW" "%OLLAMA_SCRIPT%"

echo       Waiting for Ollama to be ready (up to 60 s)...
set /a WAIT_COUNT=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
curl -s -o NUL -w "%%{http_code}" "%OLLAMA_URL%" 2>nul | findstr /C:"200" >nul
if not errorlevel 1 goto OLLAMA_READY
set /a WAIT_COUNT+=1
if %WAIT_COUNT% geq 30 (
    echo ERROR: Ollama did not respond after 60 seconds.
    echo        Check that ollama.exe is on the USB and the model is imported.
    pause
    exit /b 1
)
goto WAIT_LOOP

:OLLAMA_READY
echo       Ollama is ready.

:: ── Step 3: Launch CDW ────────────────────────────────────────────────────────
:LAUNCH_CDW
echo.
echo [3/3] Starting CDW...
echo       To run a gap analysis instead of the GUI, use:
echo       %PYTHON% %CDW_MAIN% --reason --scan-id 1 --standard MOD-025-2
echo       (add --run-id ^<uuid^> to resume a previous run)
echo.

set "PYTHONPATH=%CDW_SRC%"
cd /d "%CDW_SRC%"
"%PYTHON%" "%CDW_MAIN%" %*

endlocal
