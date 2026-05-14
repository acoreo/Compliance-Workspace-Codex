@echo off
setlocal

:: list_scans.bat - Show recent CDW evidence scan IDs.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "CDW_SRC=%USB%\Shared\cdw\projects\cdw"
set "TOOL=%CDW_SRC%\compliance_workspace\tools\list_scans.py"

if not exist "%PYTHON%" (
    echo ERROR: Python not found at:
    echo        %PYTHON%
    pause
    exit /b 1
)

if not exist "%TOOL%" (
    echo ERROR: list_scans.py not found at:
    echo        %TOOL%
    echo        Re-sync BK-1 from the Mac.
    pause
    exit /b 1
)

cd /d "%CDW_SRC%"
"%PYTHON%" "%TOOL%" %*
pause
