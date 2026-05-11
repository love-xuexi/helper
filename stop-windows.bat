@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0" >nul

echo ====================================
echo Stopping SuperBizAgent services
echo ====================================
echo.

echo [1/5] Stopping FastAPI service...
set "FASTAPI_STOPPED=0"
taskkill /FI "WINDOWTITLE eq SuperBizAgent API*" /T /F >nul 2>&1
if not errorlevel 1 set "FASTAPI_STOPPED=1"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":9900 .*LISTENING"') do (
    echo [INFO] Stopping FastAPI PID %%p on port 9900.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "FASTAPI_STOPPED=1"
)
if "!FASTAPI_STOPPED!"=="1" (
    echo [OK] FastAPI service stopped.
) else (
    echo [INFO] FastAPI service was not running.
)
echo.

echo [2/5] Stopping CLS MCP service...
set "CLS_STOPPED=0"
taskkill /FI "WINDOWTITLE eq CLS MCP Server*" /T /F >nul 2>&1
if not errorlevel 1 set "CLS_STOPPED=1"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8003 .*LISTENING"') do (
    echo [INFO] Stopping CLS MCP PID %%p on port 8003.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "CLS_STOPPED=1"
)
if "!CLS_STOPPED!"=="1" (
    echo [OK] CLS MCP service stopped.
) else (
    echo [INFO] CLS MCP service was not running.
)
echo.

echo [3/5] Stopping Monitor MCP service...
set "MONITOR_STOPPED=0"
taskkill /FI "WINDOWTITLE eq Monitor MCP Server*" /T /F >nul 2>&1
if not errorlevel 1 set "MONITOR_STOPPED=1"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8004 .*LISTENING"') do (
    echo [INFO] Stopping Monitor MCP PID %%p on port 8004.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "MONITOR_STOPPED=1"
)
if "!MONITOR_STOPPED!"=="1" (
    echo [OK] Monitor MCP service stopped.
) else (
    echo [INFO] Monitor MCP service was not running.
)
echo.

echo [4/5] Stopping live log viewer...
taskkill /FI "WINDOWTITLE eq SuperBizAgent Logs*" /T /F >nul 2>&1
if errorlevel 1 (
    echo [INFO] Live log viewer was not running.
) else (
    echo [OK] Live log viewer stopped.
)
echo.

echo [5/5] Stopping Milvus containers...
where docker >nul 2>&1
if errorlevel 1 (
    echo [WARN] Docker was not found. Skipping Milvus shutdown.
) else (
    docker ps --format "{{.Names}}" | findstr /C:"milvus" >nul 2>&1
    if not errorlevel 1 (
        docker compose -f vector-database.yml down
        if errorlevel 1 (
            echo [ERROR] Docker Compose shutdown failed.
        ) else (
            echo [OK] Milvus containers stopped.
        )
    ) else (
        echo [INFO] Milvus containers were not running.
    )
)
echo.

echo ====================================
echo Stop finished.
echo ====================================
echo.
echo Tip:
echo   To remove Docker volumes, run:
echo   docker compose -f vector-database.yml down -v
echo.
popd >nul
if not defined NO_PAUSE pause
exit /b 0
