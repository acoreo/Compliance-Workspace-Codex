@echo off
setlocal

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
set "LOCAL_ALL=%DEST_ROOT%\run_all_local_tests.bat"
set "LOG_DIR=%USB%\Shared\cdw\run_logs"
set "SYNC_LOG=%LOG_DIR%\sync_to_dell.log"
set "SYNC_LATEST=%LOG_DIR%\latest_sync_to_dell.log"

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
mkdir "%LOG_DIR%" 2>nul

echo [%DATE% %TIME%] Starting sync_to_dell.bat >> "%SYNC_LOG%"
echo USB=%USB% >> "%SYNC_LOG%"
echo DEST_ROOT=%DEST_ROOT% >> "%SYNC_LOG%"
copy /Y NUL "%SYNC_LATEST%" >nul
echo [%DATE% %TIME%] Starting sync_to_dell.bat >> "%SYNC_LATEST%"
echo USB=%USB% >> "%SYNC_LATEST%"
echo DEST_ROOT=%DEST_ROOT% >> "%SYNC_LATEST%"

echo Copying CDW runtime/source to local disk...
echo Preserving local data, reports, logs, and benchmark outputs.
echo.
echo Copying CDW runtime/source to local disk... >> "%SYNC_LOG%"
echo Copying CDW runtime/source to local disk... >> "%SYNC_LATEST%"

robocopy "%SRC_CDW%" "%DEST_CDW%" /E ^
    /XD ^
        "%SRC_CDW%\projects\cdw\data" ^
        "%SRC_CDW%\projects\cdw\reports" ^
        "%SRC_CDW%\projects\cdw\logs" ^
        "%SRC_CDW%\projects\cdw\.git" ^
        "%SRC_CDW%\projects\cdw\__pycache__" ^
    /XF "*.pyc" "*.pyo" ".DS_Store" ^
    /TEE /LOG+:"%SYNC_LOG%"

set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo ERROR: robocopy failed with exit code %RC%.
    pause
    exit /b %RC%
)

echo.
echo Copying Ollama binaries to local disk...
robocopy "%SRC_BIN%" "%DEST_BIN%" /E /TEE /LOG+:"%SYNC_LOG%"
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo ERROR: robocopy failed copying bin with exit code %RC%.
    pause
    exit /b %RC%
)

echo.
echo Copying Ollama model store to local disk...
echo This can take a while because model files are large.
robocopy "%SRC_MODELS%" "%DEST_MODELS%" /E /TEE /LOG+:"%SYNC_LOG%"
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
>> "%LOCAL_BENCH%" echo set "LOG_DIR=%USB%\Shared\cdw\run_logs"
>> "%LOCAL_BENCH%" echo set "LOG_APPEND=%%LOG_DIR%%\benchmark_fast_local.log"
>> "%LOCAL_BENCH%" echo set "LOG_LATEST=%%LOG_DIR%%\latest_benchmark_fast_local.log"
>> "%LOCAL_BENCH%" echo set "RAW_LOG=%%LOG_DIR%%\benchmark_raw.jsonl"
>> "%LOCAL_BENCH%" echo echo ============================================================
>> "%LOCAL_BENCH%" echo echo   CDW Local Fast Benchmark
>> "%LOCAL_BENCH%" echo echo   Python : %%PYTHON%%
>> "%LOCAL_BENCH%" echo echo   Bench  : %%BENCH%%
>> "%LOCAL_BENCH%" echo echo   Ollama : %%OLLAMA%%
>> "%LOCAL_BENCH%" echo echo   Log    : %%LOG_APPEND%%
>> "%LOCAL_BENCH%" echo echo   Latest : %%LOG_LATEST%%
>> "%LOCAL_BENCH%" echo echo   Raw    : %%RAW_LOG%%
>> "%LOCAL_BENCH%" echo echo ============================================================
>> "%LOCAL_BENCH%" echo echo.
>> "%LOCAL_BENCH%" echo mkdir "%%LOG_DIR%%" 2^>nul
>> "%LOCAL_BENCH%" echo cd /d "%%CDW_SRC%%"
>> "%LOCAL_BENCH%" echo powershell -NoProfile -ExecutionPolicy Bypass -Command "^& { ^& '%%PYTHON%%' '%%BENCH%%' --base-url http://127.0.0.1:11434 --api ollama --calls warm --max-tokens 400 --ollama-bin '%%OLLAMA%%' --raw-log '%%RAW_LOG%%' llama3.2:3b 2^>^&1 ^| Tee-Object -FilePath '%%LOG_APPEND%%' -Append ^| Tee-Object -FilePath '%%LOG_LATEST%%'; exit $LASTEXITCODE }"
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
echo Writing local all-tests launcher:
echo   %LOCAL_ALL%

> "%LOCAL_ALL%" echo @echo off
>> "%LOCAL_ALL%" echo setlocal enabledelayedexpansion
>> "%LOCAL_ALL%" echo set "PYTHON=%DEST_CDW%\python\python.exe"
>> "%LOCAL_ALL%" echo set "BENCH=%DEST_PROJECT%\compliance_workspace\tools\benchmark_llm.py"
>> "%LOCAL_ALL%" echo set "PROBE=%DEST_PROJECT%\compliance_workspace\tools\probe_llm_behavior.py"
>> "%LOCAL_ALL%" echo set "OLLAMA=%DEST_BIN%\ollama.exe"
>> "%LOCAL_ALL%" echo set "OLLAMA_LAUNCHER=%LOCAL_OLLAMA%"
>> "%LOCAL_ALL%" echo set "CDW_SRC=%DEST_PROJECT%"
>> "%LOCAL_ALL%" echo set "LOG_DIR=%USB%\Shared\cdw\run_logs"
>> "%LOCAL_ALL%" echo set "LOG_APPEND=%%LOG_DIR%%\run_all_local_tests.log"
>> "%LOCAL_ALL%" echo set "LOG_LATEST=%%LOG_DIR%%\latest_run_all_local_tests.log"
>> "%LOCAL_ALL%" echo set "BENCH_RAW=%%LOG_DIR%%\benchmark_raw.jsonl"
>> "%LOCAL_ALL%" echo set "PROBE_RAW=%%LOG_DIR%%\behavior_probe_raw.jsonl"
>> "%LOCAL_ALL%" echo set "TMP=%%TEMP%%\cdw_run_all_%%RANDOM%%.log"
>> "%LOCAL_ALL%" echo mkdir "%%LOG_DIR%%" 2^>nul
>> "%LOCAL_ALL%" echo copy /Y NUL "%%LOG_LATEST%%" ^>nul
>> "%LOCAL_ALL%" echo call :mark "CDW local all-tests run started"
>> "%LOCAL_ALL%" echo call :mark "Log append: %%LOG_APPEND%%"
>> "%LOCAL_ALL%" echo call :mark "Log latest: %%LOG_LATEST%%"
>> "%LOCAL_ALL%" echo call :mark "Benchmark raw: %%BENCH_RAW%%"
>> "%LOCAL_ALL%" echo call :mark "Behavior raw: %%PROBE_RAW%%"
>> "%LOCAL_ALL%" echo cd /d "%%CDW_SRC%%"
>> "%LOCAL_ALL%" echo curl -s -o NUL -w "%%%%{http_code}" "http://127.0.0.1:11434" 2^>nul ^| findstr /C:"200" ^>nul
>> "%LOCAL_ALL%" echo if errorlevel 1 ^(
>> "%LOCAL_ALL%" echo     call :mark "Ollama is not reachable. Starting local Ollama in a separate window."
>> "%LOCAL_ALL%" echo     start "CDW Local Ollama" /min "%%OLLAMA_LAUNCHER%%"
>> "%LOCAL_ALL%" echo ^)
>> "%LOCAL_ALL%" echo call :mark "Waiting for Ollama at http://127.0.0.1:11434"
>> "%LOCAL_ALL%" echo for /L %%%%N in ^(1,1,60^) do ^(
>> "%LOCAL_ALL%" echo     curl -s -o NUL -w "%%%%{http_code}" "http://127.0.0.1:11434" 2^>nul ^| findstr /C:"200" ^>nul
>> "%LOCAL_ALL%" echo     if not errorlevel 1 goto ollama_ready
>> "%LOCAL_ALL%" echo     timeout /t 2 /nobreak ^>nul
>> "%LOCAL_ALL%" echo ^)
>> "%LOCAL_ALL%" echo call :mark "ERROR: Ollama did not become reachable within 120 seconds."
>> "%LOCAL_ALL%" echo pause
>> "%LOCAL_ALL%" echo exit /b 2
>> "%LOCAL_ALL%" echo :ollama_ready
>> "%LOCAL_ALL%" echo call :mark "Ollama is reachable."
>> "%LOCAL_ALL%" echo call :mark "==== ollama list ===="
>> "%LOCAL_ALL%" echo "%%OLLAMA%%" list ^> "%%TMP%%" 2^>^&1
>> "%LOCAL_ALL%" echo set "RC=!ERRORLEVEL!"
>> "%LOCAL_ALL%" echo type "%%TMP%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_APPEND%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_LATEST%%"
>> "%LOCAL_ALL%" echo call :mark "ollama list exit_code=!RC!"
>> "%LOCAL_ALL%" echo call :mark "==== ollama ps before benchmark ===="
>> "%LOCAL_ALL%" echo "%%OLLAMA%%" ps ^> "%%TMP%%" 2^>^&1
>> "%LOCAL_ALL%" echo set "RC=!ERRORLEVEL!"
>> "%LOCAL_ALL%" echo type "%%TMP%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_APPEND%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_LATEST%%"
>> "%LOCAL_ALL%" echo call :mark "ollama ps before benchmark exit_code=!RC!"
>> "%LOCAL_ALL%" echo call :mark "==== structured benchmark: llama3.2:3b warm ===="
>> "%LOCAL_ALL%" echo "%%PYTHON%%" "%%BENCH%%" --base-url http://127.0.0.1:11434 --api ollama --calls warm --max-tokens 400 --ollama-bin "%%OLLAMA%%" --raw-log "%%BENCH_RAW%%" llama3.2:3b ^> "%%TMP%%" 2^>^&1
>> "%LOCAL_ALL%" echo set "RC=!ERRORLEVEL!"
>> "%LOCAL_ALL%" echo type "%%TMP%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_APPEND%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_LATEST%%"
>> "%LOCAL_ALL%" echo call :mark "structured benchmark exit_code=!RC!"
>> "%LOCAL_ALL%" echo call :mark "==== ollama ps after benchmark ===="
>> "%LOCAL_ALL%" echo "%%OLLAMA%%" ps ^> "%%TMP%%" 2^>^&1
>> "%LOCAL_ALL%" echo set "RC=!ERRORLEVEL!"
>> "%LOCAL_ALL%" echo type "%%TMP%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_APPEND%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_LATEST%%"
>> "%LOCAL_ALL%" echo call :mark "ollama ps after benchmark exit_code=!RC!"
>> "%LOCAL_ALL%" echo call :mark "==== behavior probe: llama3.2:3b ===="
>> "%LOCAL_ALL%" echo "%%PYTHON%%" "%%PROBE%%" --base-url http://127.0.0.1:11434 --raw-log "%%PROBE_RAW%%" llama3.2:3b ^> "%%TMP%%" 2^>^&1
>> "%LOCAL_ALL%" echo set "RC=!ERRORLEVEL!"
>> "%LOCAL_ALL%" echo type "%%TMP%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_APPEND%%"
>> "%LOCAL_ALL%" echo type "%%TMP%%" ^>^> "%%LOG_LATEST%%"
>> "%LOCAL_ALL%" echo call :mark "behavior probe exit_code=!RC!"
>> "%LOCAL_ALL%" echo call :mark "CDW local all-tests run complete"
>> "%LOCAL_ALL%" echo del "%%TMP%%" 2^>nul
>> "%LOCAL_ALL%" echo pause
>> "%LOCAL_ALL%" echo exit /b 0
>> "%LOCAL_ALL%" echo :mark
>> "%LOCAL_ALL%" echo echo.
>> "%LOCAL_ALL%" echo echo %%~1
>> "%LOCAL_ALL%" echo ^>^> "%%LOG_APPEND%%" echo.
>> "%LOCAL_ALL%" echo ^>^> "%%LOG_APPEND%%" echo %%~1
>> "%LOCAL_ALL%" echo ^>^> "%%LOG_LATEST%%" echo.
>> "%LOCAL_ALL%" echo ^>^> "%%LOG_LATEST%%" echo %%~1
>> "%LOCAL_ALL%" echo exit /b 0

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
echo   3. Or run all local tests:
echo      %LOCAL_ALL%
echo.
echo [%DATE% %TIME%] Sync complete. >> "%SYNC_LOG%"
echo [%DATE% %TIME%] Sync complete. >> "%SYNC_LATEST%"
echo Local benchmark launcher: %LOCAL_BENCH% >> "%SYNC_LOG%"
echo Local Ollama launcher: %LOCAL_OLLAMA% >> "%SYNC_LOG%"
echo Local all-tests launcher: %LOCAL_ALL% >> "%SYNC_LOG%"
pause
exit /b 0
