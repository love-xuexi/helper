@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0" >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"

echo ====================================
echo Starting Smart QA Assistant
echo ====================================
echo.

echo [1/7] Checking package manager...
where uv >nul 2>&1
if errorlevel 1 (
    echo [INFO] uv.exe was not found. pip fallback will be used.
    echo [TIP] Optional install: python -m pip install uv
    set "USE_UV=0"
) else (
    echo [OK] uv.exe found.
    set "USE_UV=1"
)
echo.

echo [2/7] Checking .python-version...
set "PYTHON_VERSION="
if exist ".python-version" (
    set /p PYTHON_VERSION=<".python-version"
)
if "!PYTHON_VERSION!"=="" (
    >".python-version" echo 3.13
    set "PYTHON_VERSION=3.13"
    echo [INFO] .python-version was empty and has been reset to 3.13.
) else (
    echo [INFO] .python-version: !PYTHON_VERSION!
)
echo.

echo [3/7] Creating or updating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating a new virtual environment...
    if "%USE_UV%"=="1" (
        echo [INFO] Trying uv venv...
        uv venv
        if not errorlevel 1 goto :venv_ready
        echo [WARN] uv venv failed. Falling back to python -m venv.
    )

    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found in PATH.
        echo [TIP] Install Python 3.11, 3.12, or 3.13 and try again.
        goto :fail
    )

    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Virtual environment creation failed.
        echo [TIP] Make sure Python 3.11, 3.12, or 3.13 is installed.
        goto :fail
    )
)

:venv_ready
set "PYTHON_CMD=.venv\Scripts\python.exe"
if not exist "%PYTHON_CMD%" (
    echo [ERROR] %PYTHON_CMD% was not created.
    goto :fail
)
echo [OK] Virtual environment is available.
echo.

echo [4/7] Checking virtual environment Python version...
"%PYTHON_CMD%" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)"
if errorlevel 1 (
    echo [ERROR] This project requires Python 3.11, 3.12, or 3.13.
    "%PYTHON_CMD%" --version
    echo [TIP] Recreate .venv with a supported Python version.
    goto :fail
)
"%PYTHON_CMD%" --version
echo.

echo [5/7] Checking dependencies...
"%PYTHON_CMD%" -c "import os,sys; s='.venv/.deps_stamp'; sys.exit(0 if os.path.exists(s) and os.path.getmtime(s)>max(os.path.getmtime('pyproject.toml'), os.path.getmtime('uv.lock') if os.path.exists('uv.lock') else 0) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Dependencies are up to date ^(stamp valid^).
    goto :deps_done
)
echo [INFO] Dependencies need updating (pyproject.toml/uv.lock changed or first run)...
"%PYTHON_CMD%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] pip not found. Bootstrapping...
    "%PYTHON_CMD%" -m ensurepip --upgrade
    if errorlevel 1 (
        echo [ERROR] pip bootstrap failed.
        echo [TIP] Delete .venv and run start-windows.bat again, or reinstall Python with pip support.
        goto :fail
    )
)
if "%USE_UV%"=="1" (
    uv sync
    if errorlevel 1 (
        echo [WARN] uv sync failed. Falling back to pip.
        "%PYTHON_CMD%" -m pip install -e .
    )
) else (
    "%PYTHON_CMD%" -m pip install -e .
)
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    goto :fail
)
type nul > ".venv\.deps_stamp"
echo [OK] Dependencies updated.
:deps_done
echo.

echo [6/7] Checking application configuration...
"%PYTHON_CMD%" -c "from app.config import config; print('Config OK')" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Config/import check failed. Attempting dependency recovery...
    if "%USE_UV%"=="1" (
        uv sync
        if errorlevel 1 "%PYTHON_CMD%" -m pip install -e .
    ) else (
        "%PYTHON_CMD%" -m pip install -e .
    )
    type nul > ".venv\.deps_stamp"
    "%PYTHON_CMD%" -c "from app.config import config; print('Config OK')" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Configuration check failed after recovery.
        echo [TIP] Check .env values. DEBUG must be true or false.
        echo [TIP] Try deleting .venv and running start-windows.bat again.
        goto :fail
    )
    echo [OK] Configuration valid after recovery.
) else (
    echo [OK] Configuration is valid.
)
echo.

echo [7/7] Starting FastAPI service...
if exist "server.log" del "server.log"
if exist "server_error.log" del "server_error.log"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%PYTHON_CMD%' -ArgumentList '-m','app.run_server' -RedirectStandardOutput 'server.log' -RedirectStandardError 'server_error.log' -WindowStyle Hidden -PassThru; Set-Content -Path 'server.pid' -Value $p.Id -NoNewline -Encoding ascii"
if errorlevel 1 (
    echo [ERROR] Failed to start FastAPI service.
    goto :fail
)
echo [INFO] API started in background (hidden, PID saved to server.pid).
echo [INFO] Waiting for API startup...
set "ATTEMPTS=0"
:health_loop
set /a ATTEMPTS+=1
if !ATTEMPTS! GTR 30 (
    echo [WARN] API did not become healthy within 30 seconds.
    echo.
    echo [INFO] --- Recent server.log ^(last 30 lines^) ---
    if exist "server.log" (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path 'server.log' -Tail 30 -Encoding UTF8"
    ) else (
        echo [WARN] server.log was not created.
    )
    echo.
    echo [INFO] --- Recent server_error.log ^(last 30 lines^) ---
    if exist "server_error.log" (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path 'server_error.log' -Tail 30 -Encoding UTF8"
    )
    echo.
    echo [TIP] Full logs: server.log, server_error.log, logs\app_*.log
    goto :fail
)
curl -s http://localhost:9983/api/health >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto :health_loop
)
echo [OK] FastAPI is healthy (ready in !ATTEMPTS!s).
echo.
echo [INFO] --- Recent startup logs (last 15 lines) ---
if exist "server.log" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path 'server.log' -Tail 15 -Encoding UTF8"
)
echo.
echo ====================================
echo Startup finished.
echo ====================================
echo Web UI:      http://localhost:9983
echo API docs:    http://localhost:9983/docs
echo.
echo Logs:
echo   server.log          - uvicorn + stdout (startup + runtime)
echo   server_error.log    - stderr (errors/crashes)
echo   logs\app_*.log      - loguru structured logs (daily rotation)
echo.
echo Live tail:   powershell -NoProfile -Command "Get-Content -Path server.log -Wait -Tail 80 -Encoding UTF8"
echo Stop:        stop-windows.bat
echo.
echo [NOTE] Knowledge base API must be reachable at the configured internal addresses.
echo [NOTE] MCP services (AIOps) are optional and not started by default.
echo   To start MCP: python mcp_servers\cls_server.py and python mcp_servers\monitor_server.py
echo ====================================
goto :done

:fail
echo.
echo Startup failed. See the messages above.
popd >nul
if not defined NO_PAUSE pause
exit /b 1

:done
popd >nul
if not defined NO_PAUSE pause
exit /b 0
