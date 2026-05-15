@echo off
setlocal

:: run_reason.bat - Run CDW gap analysis for a scan and standard.
:: Usage: run_reason.bat SCAN_ID STANDARD_ID

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "CDW_SRC=%USB%\Shared\cdw\projects\cdw"
set "CDW_MAIN=%CDW_SRC%\compliance_workspace\main.py"

if "%~1"=="" (
    echo Usage:
    echo   %~nx0 SCAN_ID STANDARD_ID
    echo Example:
    echo   %~nx0 3 CIP-002-5
    pause
    exit /b 2
)

if "%~2"=="" (
    echo Usage:
    echo   %~nx0 SCAN_ID STANDARD_ID
    echo Example:
    echo   %~nx0 3 CIP-002-5
    pause
    exit /b 2
)

if not exist "%PYTHON%" (
    echo ERROR: Python not found at:
    echo        %PYTHON%
    pause
    exit /b 1
)

if not exist "%CDW_MAIN%" (
    echo ERROR: main.py not found at:
    echo        %CDW_MAIN%
    pause
    exit /b 1
)

set "TOP_K=%~3"
if "%TOP_K%"=="" set "TOP_K=2"

set "PYTHONPATH=%CDW_SRC%"
cd /d "%CDW_SRC%"
"%PYTHON%" "%CDW_MAIN%" --reason --scan-id %~1 --standard %~2 --top-k %TOP_K%
pause
