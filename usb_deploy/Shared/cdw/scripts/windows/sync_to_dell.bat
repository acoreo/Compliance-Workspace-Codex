@echo off
setlocal enabledelayedexpansion

:: sync_to_dell.bat - Copy CDW runtime/code/models from BK-1 to Dell local disk.
:: This is a development workflow helper:
::   USB  = package/source of updates
::   C:\CDW = active local execution workspace
::
:: It preserves local runtime data by avoiding destructive mirroring.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\..\..") do set "USB=%%~fI"

set "SRC_SHARED=%USB%\Shared"
set "SRC_CDW=%USB%\Shared\cdw"
set "SRC_BIN=%USB%\Shared\bin"
set "SRC_MODELS=%USB%\Shared\models"
set "DEST_ROOT=C:\CDW"
set "DEST_SHARED=%DEST_ROOT%\Shared"
set "DEST_CDW=%DEST_ROOT%\Shared\cdw"
set "DEST_BIN=%DEST_ROOT%\Shared\bin"
set "DEST_MODELS=%DEST_ROOT%\Shared\models"
set "DEST_PROJECT=%DEST_CDW%\projects\cdw"
set "DEST_DATA=%DEST_PROJECT%\data"
set "USER_RAW=%USERPROFILE%\data\benchmark_raw.jsonl"
set "DEST_RAW=%DEST_DATA%\benchmark_raw.jsonl"
set "LOCAL_BENCH=%DEST_ROOT%\benchmark_fast_local.bat"
set "LOCAL_OLLAMA=%DEST_ROOT%\start_ollama_local.bat"

echo ============================================================
echo   CDW Sync to Dell Local Workspace
echo   USB root : %USB%
echo   Source   : %SRC_SHARED%
echo   Target   : %DEST_SHARED%
echo ============================================================
echo.

if not exist "%SRC_CDW%\projects\cdw\compliance_workspace\tools\benchmark_llm.py" (
    echo ERROR: CDW source not found on USB:
    echo        %SRC_CDW%\projects\cdw
    pause
    exit /b 1
)

mkdir "%DEST_ROOT%" 2>nul
mkdir "%DEST_SHARED%" 2>nul
mkdir "%DEST_CDW%" 2>nul
mkdir "%DEST_BIN%" 2>nul
mkdir "%DEST_MODELS%" 2>nul
mkdir "%DEST_DATA%" 2>nul

echo Copying CDW runtime/source to local disk...
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
echo Copying Ollama binaries to local disk...
robocopy "%SRC_BIN%" "%DEST_BIN%" /E
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo ERROR: robocopy failed copying bin with exit code %RC%.
    pause
    exit /b %RC%
)

echo.
echo Copying Ollama model store to local disk...
echo This can take a while because model files are large.
robocopy "%SRC_MODELS%" "%DEST_MODELS%" /E
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo ERROR: robocopy failed copying models with exit code %RC%.
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
>> "%LOCAL_BENCH%" echo set "OLLAMA=%DEST_BIN%\ollama.exe"
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
echo Writing local Ollama launcher:
echo   %LOCAL_OLLAMA%

> "%LOCAL_OLLAMA%" echo @echo off
>> "%LOCAL_OLLAMA%" echo setlocal
>> "%LOCAL_OLLAMA%" echo set "OLLAMA=%DEST_BIN%\ollama.exe"
>> "%LOCAL_OLLAMA%" echo set "OLLAMA_MODELS=%DEST_MODELS%\ollama_data"
>> "%LOCAL_OLLAMA%" echo set "OLLAMA_HOST=127.0.0.1:11434"
>> "%LOCAL_OLLAMA%" echo echo ============================================================
>> "%LOCAL_OLLAMA%" echo echo   CDW Local Ollama Server
>> "%LOCAL_OLLAMA%" echo echo   Ollama binary : %%OLLAMA%%
>> "%LOCAL_OLLAMA%" echo echo   Model store   : %%OLLAMA_MODELS%%
>> "%LOCAL_OLLAMA%" echo echo ============================================================
>> "%LOCAL_OLLAMA%" echo echo.
>> "%LOCAL_OLLAMA%" echo "%%OLLAMA%%" serve
>> "%LOCAL_OLLAMA%" echo pause

echo.
echo ============================================================
echo   Sync complete.
echo ============================================================
echo.
echo Next:
echo   1. Start local Ollama:
echo      %LOCAL_OLLAMA%
echo   2. Run local benchmark:
echo      %LOCAL_BENCH%
echo.
pause
exit /b 0
