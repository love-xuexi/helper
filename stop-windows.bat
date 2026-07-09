@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0" >nul

echo ====================================
echo Stopping Smart QA Assistant
echo ====================================
echo.

echo [1/4] Stopping FastAPI service...
set "FASTAPI_STOPPED=0"
taskkill /FI "WINDOWTITLE eq SmartQA API*" /T /F >nul 2>&1
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

echo [2/4] Stopping CLS MCP service (if running)...
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

echo [3/4] Stopping Monitor MCP service (if running)...
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

echo [4/4] Stopping live log viewer...
taskkill /FI "WINDOWTITLE eq SmartQA Logs*" /T /F >nul 2>&1
if errorlevel 1 (
    echo [INFO] Live log viewer was not running.
) else (
    echo [OK] Live log viewer stopped.
)
echo.

echo ====================================
echo Stop finished.
echo ====================================
echo.
popd >nul
if not defined NO_PAUSE pause
exit /b 0
