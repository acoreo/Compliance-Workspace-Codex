@echo off
setlocal enabledelayedexpansion

:: install_offline.bat — One-time offline setup for CDW on Windows
:: Uses %~d0 to detect the USB drive letter dynamically (works on D:, E:, F:, etc.)

set "USB=%~d0\USB-Uncensored-LLM"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "WHEELS=%USB%\Shared\cdw\wheels"
set "GET_PIP=%USB%\Shared\cdw\get-pip.py"
set "REQS=%USB%\Shared\cdw\requirements\cdw.txt"
set "PTH_FILE=%USB%\Shared\cdw\python\python312._pth"
set "DONE_FLAG=%USB%\Shared\cdw\done.flag"

echo === CDW Offline Install ===
echo USB root: %USB%
echo.

:: Step 1: Verify Python 3.12 embeddable is present
echo [1/4] Checking for Python 3.12 embeddable...
if not exist "%PYTHON%" (
    echo ERROR: Python not found at:
    echo        %PYTHON%
    echo Please ensure the USB was prepared correctly.
    pause
    exit /b 1
)
echo       Found: %PYTHON%

:: Step 2: Enable site-packages in Python embeddable (_pth patch)
echo [2/4] Enabling site-packages in Python embeddable...
if exist "%PTH_FILE%" (
    powershell -Command "(Get-Content '%PTH_FILE%') -replace '#import site','import site' | Set-Content '%PTH_FILE%'"
    echo       Done.
) else (
    echo       WARNING: %PTH_FILE% not found. Pip bootstrap may fail.
)

:: Step 3: Bootstrap pip if not present
echo [3/4] Checking pip...
"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo       pip not found — bootstrapping from get-pip.py...
    if not exist "%GET_PIP%" (
        echo ERROR: get-pip.py not found at:
        echo        %GET_PIP%
        echo Run sync_wheels.sh on Mac first to download it.
        pause
        exit /b 1
    )
    "%PYTHON%" "%GET_PIP%" --no-index --find-links="%WHEELS%"
    if errorlevel 1 (
        echo ERROR: pip bootstrap failed.
        pause
        exit /b 1
    )
) else (
    echo       pip already available.
)

:: Step 4: Install CDW dependencies from offline wheel cache
echo [4/4] Installing CDW dependencies (offline)...
"%PYTHON%" -m pip install --no-index --prefer-binary --find-links="%WHEELS%" -r "%REQS%"
if errorlevel 1 (
    echo ERROR: pip install failed. Check that all required wheels are in:
    echo        %WHEELS%
    pause
    exit /b 1
)

:: Mark install complete so start_cdw.bat skips this next time
echo. > "%DONE_FLAG%"

echo.
echo === Install complete ===
echo Run start_cdw.bat to launch CDW.
pause
