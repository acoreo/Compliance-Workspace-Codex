@echo off
setlocal enabledelayedexpansion

:: sync_to_dell.bat - Copy CDW runtime/code from BK-1 to Dell local disk.
:: This is a development workflow helper:
::   USB  = package/source of updates
::   C:\CDW = active local execution workspace
::
:: It preserves local runtime data by avoiding destructive mirroring.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"

set "SRC_CDW=%USB%\Shared\cdw"
set "DEST_ROOT=C:\CDW"
set "DEST_CDW=%DEST_ROOT%\Shared\cdw"
set "DEST_PROJECT=%DEST_CDW%\projects\cdw"
set "DEST_DATA=%DEST_PROJECT%\data"
set "USER_RAW=%USERPROFILE%\data\benchmark_raw.jsonl"
set "DEST_RAW=%DEST_DATA%\benchmark_raw.jsonl"
set "LOCAL_BENCH=%DEST_ROOT%\benchmark_fast_local.bat"

echo ============================================================
echo   CDW Sync to Dell Local Workspace
echo   USB root : %USB%
echo   Source   : %SRC_CDW%
echo   Target   : %DEST_CDW%
echo ============================================================
echo.

if not exist "%SRC_CDW%\projects\cdw\compliance_workspace\tools\benchmark_llm.py" (
    echo ERROR: CDW source not found on USB:
    echo        %SRC_CDW%\projects\cdw
    pause
    exit /b 1
)

mkdir "%DEST_ROOT%" 2>nul
mkdir "%DEST_CDW%" 2>nul
mkdir "%DEST_DATA%" 2>nul

echo Copying CDW runtime and source to local disk...
echo Preserving local data, reports, logs, and benchmark outputs.
echo.

robocopy "%SRC_CDW%" "%DEST_CDW%" /E ^
    /XD ^
        "%SRC_CDW%\projects\cdw\data" ^
        "%SRC_CDW%\projects\cdw\reports" ^
        "%SRC_CDW%\projects\cdw\logs" ^
        "%SRC_CDW%\projects\cdw\.git" ^
        "%SRC_CDW%\projects\cdw\__pycache__" ^
    /XF "*.pyc" "*.pyo" ".DS_Store"

set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo ERROR: robocopy failed with exit code %RC%.
    pause
    exit /b %RC%
)

echo.
if exist "%USER_RAW%" (
    if not exist "%DEST_RAW%" (
        echo Importing existing benchmark raw log:
        echo   from: %USER_RAW%
        echo   to  : %DEST_RAW%
        copy "%USER_RAW%" "%DEST_RAW%" >nul
        if errorlevel 1 (
            echo WARN: Failed to import existing benchmark raw log.
        ) else (
            echo OK: Imported benchmark_raw.jsonl.
        )
    ) else (
        echo Local benchmark raw log already exists:
        echo   %DEST_RAW%
        echo Existing user-profile raw log was left untouched:
        echo   %USER_RAW%
    )
) else (
    echo No existing user-profile benchmark raw log found at:
    echo   %USER_RAW%
)

echo.
echo Writing local fast benchmark launcher:
echo   %LOCAL_BENCH%

> "%LOCAL_BENCH%" echo @echo off
>> "%LOCAL_BENCH%" echo setlocal
>> "%LOCAL_BENCH%" echo set "PYTHON=%DEST_CDW%\python\python.exe"
>> "%LOCAL_BENCH%" echo set "BENCH=%DEST_PROJECT%\compliance_workspace\tools\benchmark_llm.py"
>> "%LOCAL_BENCH%" echo set "OLLAMA=%USB%\Shared\bin\ollama.exe"
>> "%LOCAL_BENCH%" echo set "CDW_SRC=%DEST_PROJECT%"
>> "%LOCAL_BENCH%" echo echo ============================================================
>> "%LOCAL_BENCH%" echo echo   CDW Local Fast Benchmark
>> "%LOCAL_BENCH%" echo echo   Python : %%PYTHON%%
>> "%LOCAL_BENCH%" echo echo   Bench  : %%BENCH%%
>> "%LOCAL_BENCH%" echo echo   Ollama : %%OLLAMA%%
>> "%LOCAL_BENCH%" echo echo ============================================================
>> "%LOCAL_BENCH%" echo echo.
>> "%LOCAL_BENCH%" echo cd /d "%%CDW_SRC%%"
>> "%LOCAL_BENCH%" echo "%%PYTHON%%" "%%BENCH%%" --base-url http://127.0.0.1:11434 --api ollama --calls warm --max-tokens 400 --ollama-bin "%%OLLAMA%%" llama3.2:3b
>> "%LOCAL_BENCH%" echo pause

echo.
echo ============================================================
echo   Sync complete.
echo ============================================================
echo.
echo Next:
echo   1. Keep/start Ollama from USB:
echo      %USB%\Shared\cdw\scripts\windows\start_ollama.bat
echo   2. Run local benchmark:
echo      %LOCAL_BENCH%
echo.
pause
exit /b 0
