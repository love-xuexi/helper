@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0" >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ====================================
echo Starting SuperBizAgent services
echo ====================================
echo.

echo [1/9] Checking package manager...
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

echo [2/9] Checking .python-version...
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

echo [3/9] Creating or updating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating a new virtual environment...
    if "%USE_UV%"=="1" (
        echo [INFO] Trying uv sync...
        uv sync
        if not errorlevel 1 goto :venv_ready
        echo [WARN] uv sync failed. Falling back to python -m venv.
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

echo [4/9] Checking virtual environment Python version...
"%PYTHON_CMD%" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)"
if errorlevel 1 (
    echo [ERROR] This project requires Python 3.11, 3.12, or 3.13.
    "%PYTHON_CMD%" --version
    echo [TIP] Recreate .venv with a supported Python version.
    goto :fail
)
"%PYTHON_CMD%" --version
echo.

echo [5/9] Installing or updating dependencies...
"%PYTHON_CMD%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] pip was not found in the virtual environment. Bootstrapping pip...
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
echo [OK] Dependencies are ready.
echo.

echo [6/9] Checking application configuration...
"%PYTHON_CMD%" -c "from app.config import config; print('Config OK')"
if errorlevel 1 (
    echo [ERROR] Application configuration check failed.
    echo [TIP] Check .env values. DEBUG must be true or false.
    goto :fail
)
echo.

echo [7/9] Starting Milvus vector database...
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker was not found in PATH.
    echo [TIP] Install and start Docker Desktop first.
    goto :fail
)
docker ps --format "{{.Names}}" | findstr /C:"milvus-standalone" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Milvus is already running.
) else (
    docker compose -f vector-database.yml up -d
    if errorlevel 1 (
        echo [ERROR] Docker Compose startup failed.
        echo [TIP] Make sure Docker Desktop is running.
        goto :fail
    )
    echo [INFO] Waiting for Milvus startup...
    timeout /t 10 /nobreak >nul
)
echo [OK] Milvus is ready.
echo.

echo [8/9] Starting MCP services...
start "CLS MCP Server" /min cmd /c ""%PYTHON_CMD%" "mcp_servers\cls_server.py" > "mcp_cls.log" 2>&1"
timeout /t 2 /nobreak >nul
start "Monitor MCP Server" /min cmd /c ""%PYTHON_CMD%" "mcp_servers\monitor_server.py" > "mcp_monitor.log" 2>&1"
timeout /t 2 /nobreak >nul
echo [OK] MCP startup commands were sent.
echo.

echo [9/9] Starting FastAPI service...
type nul > "server.log"
start "SuperBizAgent API" cmd /c ""%PYTHON_CMD%" -m app.run_server > "server.log" 2>&1"
timeout /t 2 /nobreak >nul
start "SuperBizAgent Logs" powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command "$Host.UI.RawUI.WindowTitle='SuperBizAgent Logs'; Get-Content -Path 'server.log' -Wait -Tail 80 -Encoding UTF8"
echo [INFO] Waiting for API startup...
timeout /t 15 /nobreak >nul

echo [INFO] Checking API health...
curl -s http://localhost:9900/health >nul 2>&1
if errorlevel 1 (
    echo [WARN] API did not respond yet. Check server.log and logs\app_*.log.
) else (
    echo [OK] FastAPI is healthy.
    echo [INFO] Uploading aiops-docs files...
    for %%f in (aiops-docs\*.md) do (
        echo   Uploading: %%~nxf
        curl -s -X POST http://localhost:9900/api/upload -F "file=@%%f" >nul 2>&1
    )
    echo [OK] Document upload finished.
)

echo.
echo [INFO] Recent FastAPI logs:
if exist "server.log" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path 'server.log' -Tail 30 -Encoding UTF8"
) else (
    echo [WARN] server.log was not created.
)

echo.
echo ====================================
echo Startup finished.
echo ====================================
echo Web UI: http://localhost:9900
echo API docs: http://localhost:9900/docs
echo.
echo Logs:
echo   - FastAPI process: server.log
echo   - FastAPI app: logs\app_*.log
echo   - CLS MCP: mcp_cls.log
echo   - Monitor MCP: mcp_monitor.log
echo.
echo View live FastAPI logs:
echo   powershell -NoProfile -Command "Get-Content -Path server.log -Wait -Tail 80 -Encoding UTF8"
echo Stop services: stop-windows.bat
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
