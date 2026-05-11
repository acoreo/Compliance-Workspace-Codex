@echo off
:: run_cdw.bat — Minimal CDW launcher (no install check, no Ollama start).
:: Use start_cdw.bat for the full first-run experience.
:: Uses %~d0 to detect the USB drive letter dynamically (D:, E:, F:, etc.)

set "USB=%~d0\USB-Uncensored-LLM"
set "PYTHON=%USB%\Shared\cdw\python\python.exe"
set "CDW_SRC=%USB%\Shared\cdw\projects\cdw"

if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    echo        Run start_cdw.bat first to complete the offline install.
    pause
    exit /b 1
)

set "PYTHONPATH=%CDW_SRC%"
cd /d "%CDW_SRC%"
"%PYTHON%" "%CDW_SRC%\compliance_workspace\main.py" %*
