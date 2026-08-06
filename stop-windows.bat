@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0" >nul

echo ====================================
echo Stopping Smart QA Assistant
echo ====================================
echo.

echo [1/7] Stopping FastAPI service...
set "FASTAPI_STOPPED=0"
if exist "server.pid" (
    for /f %%P in (server.pid) do (
        echo [INFO] Stopping FastAPI PID %%P ^(from server.pid^).
        taskkill /PID %%P /T /F >nul 2>&1
        if not errorlevel 1 set "FASTAPI_STOPPED=1"
    )
    del "server.pid" >nul 2>&1
)
if "!FASTAPI_STOPPED!"=="0" (
    taskkill /FI "WINDOWTITLE eq SmartQA API*" /T /F >nul 2>&1
    if not errorlevel 1 set "FASTAPI_STOPPED=1"
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":9983 .*LISTENING"') do (
    echo [INFO] Stopping FastAPI PID %%p on port 9983.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "FASTAPI_STOPPED=1"
)
if "!FASTAPI_STOPPED!"=="1" (
    echo [OK] FastAPI service stopped.
) else (
    echo [INFO] FastAPI service was not running.
)
echo.

echo [2/7] Stopping CLS MCP service (port 8103)...
set "CLS_STOPPED=0"
if exist "mcp_cls.pid" (
    for /f %%P in (mcp_cls.pid) do (
        taskkill /PID %%P /T /F >nul 2>&1
        if not errorlevel 1 set "CLS_STOPPED=1"
    )
    del "mcp_cls.pid" >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8103 .*LISTENING"') do (
    echo [INFO] Stopping CLS MCP PID %%p on port 8103.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "CLS_STOPPED=1"
)
if "!CLS_STOPPED!"=="1" (
    echo [OK] CLS MCP service stopped.
) else (
    echo [INFO] CLS MCP service was not running.
)
echo.

echo [3/7] Stopping Monitor MCP service (port 8104)...
set "MONITOR_STOPPED=0"
if exist "mcp_monitor.pid" (
    for /f %%P in (mcp_monitor.pid) do (
        taskkill /PID %%P /T /F >nul 2>&1
        if not errorlevel 1 set "MONITOR_STOPPED=1"
    )
    del "mcp_monitor.pid" >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8104 .*LISTENING"') do (
    echo [INFO] Stopping Monitor MCP PID %%p on port 8104.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "MONITOR_STOPPED=1"
)
if "!MONITOR_STOPPED!"=="1" (
    echo [OK] Monitor MCP service stopped.
) else (
    echo [INFO] Monitor MCP service was not running.
)
echo.

echo [4/7] Stopping Alert MCP service (port 8105)...
set "ALERT_STOPPED=0"
if exist "mcp_alert.pid" (
    for /f %%P in (mcp_alert.pid) do (
        taskkill /PID %%P /T /F >nul 2>&1
        if not errorlevel 1 set "ALERT_STOPPED=1"
    )
    del "mcp_alert.pid" >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8105 .*LISTENING"') do (
    echo [INFO] Stopping Alert MCP PID %%p on port 8105.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "ALERT_STOPPED=1"
)
if "!ALERT_STOPPED!"=="1" (
    echo [OK] Alert MCP service stopped.
) else (
    echo [INFO] Alert MCP service was not running.
)
echo.

echo [5/7] Stopping Ops MCP service (port 8106)...
set "OPS_STOPPED=0"
if exist "mcp_ops.pid" (
    for /f %%P in (mcp_ops.pid) do (
        taskkill /PID %%P /T /F >nul 2>&1
        if not errorlevel 1 set "OPS_STOPPED=1"
    )
    del "mcp_ops.pid" >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8106 .*LISTENING"') do (
    echo [INFO] Stopping Ops MCP PID %%p on port 8106.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "OPS_STOPPED=1"
)
if "!OPS_STOPPED!"=="1" (
    echo [OK] Ops MCP service stopped.
) else (
    echo [INFO] Ops MCP service was not running.
)
echo.

echo [6/7] Stopping DuckDuckGo Search MCP service (port 8107)...
set "DDG_STOPPED=0"
if exist "mcp_ddg.pid" (
    for /f %%P in (mcp_ddg.pid) do (
        taskkill /PID %%P /T /F >nul 2>&1
        if not errorlevel 1 set "DDG_STOPPED=1"
    )
    del "mcp_ddg.pid" >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8107 .*LISTENING"') do (
    echo [INFO] Stopping DuckDuckGo Search MCP PID %%p on port 8107.
    taskkill /PID %%p /T /F >nul 2>&1
    if not errorlevel 1 set "DDG_STOPPED=1"
)
if "!DDG_STOPPED!"=="1" (
    echo [OK] DuckDuckGo Search MCP service stopped.
) else (
    echo [INFO] DuckDuckGo Search MCP service was not running.
)
echo.

echo [7/7] Stopping live log viewer...
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
