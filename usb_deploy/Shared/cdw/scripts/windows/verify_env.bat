@echo off
:: verify_env.bat — Checks that Python and CDW dependencies are installed.
:: Resolves paths relative to this script so any drive letter works.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"

echo === CDW Environment Check ===
echo USB root: %USB%
echo.

if not exist "%PYTHON%" (
    echo ERROR: python.exe not found at:
    echo        %PYTHON%
    echo        Run start_cdw.bat to install dependencies first.
    pause
    exit /b 1
)

echo Python:
"%PYTHON%" --version

echo.
echo Key packages:
"%PYTHON%" -c "import PySide6; print('PySide6 OK')"
"%PYTHON%" -c "import pdfminer; print('pdfminer OK')"
"%PYTHON%" -c "import numpy; print('numpy OK')"
"%PYTHON%" -c "import sqlite3; print('sqlite3 OK')"
"%PYTHON%" -c "import tomllib; print('tomllib OK')" 2>nul || "%PYTHON%" -c "import tomli; print('tomli OK')"

echo.
echo Ollama:
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:11434' -TimeoutSec 3 -UseBasicParsing; Write-Host 'Ollama running' } catch { Write-Host 'Ollama NOT running' }"

echo.
echo Config model name:
"%PYTHON%" -c "import pathlib,sys; p=pathlib.Path(r'%USB%\Shared\cdw\projects\cdw\compliance_workspace\config\cdw_config.toml'); sys.stdout.write(p.read_text()) if p.exists() else sys.stdout.write('config not found')"

echo.
pause
