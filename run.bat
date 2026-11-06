@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Google Maps Domain Search
echo ========================================
echo.

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" goto :venv_ready

where py >nul 2>nul
if not errorlevel 1 (
    py -3 --version >nul 2>nul
    if not errorlevel 1 (
        echo Creating virtual environment...
        py -3 -m venv .venv
        goto :check_venv
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python --version >nul 2>nul
    if not errorlevel 1 (
        echo Creating virtual environment...
        python -m venv .venv
        goto :check_venv
    )
)

echo ERROR: Python 3 was not found.
echo Install Python from https://www.python.org/downloads/
echo During installation, enable "Add python.exe to PATH".
goto :failed

:check_venv
if errorlevel 1 (
    echo ERROR: Could not create the virtual environment.
    goto :failed
)

:venv_ready
"%VENV_PYTHON%" -c "import streamlit, requests, pandas" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 goto :install_failed
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :install_failed
)

for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0); $listener.Start(); $port = $listener.LocalEndpoint.Port; $listener.Stop(); $port"`) do set "STREAMLIT_PORT=%%P"

if not defined STREAMLIT_PORT (
    echo ERROR: Could not select a free port.
    goto :failed
)

echo.
echo Starting Streamlit on http://localhost:%STREAMLIT_PORT%
echo Press Ctrl+C to stop the server.
echo.

"%VENV_PYTHON%" -m streamlit run app.py --server.address localhost --server.port %STREAMLIT_PORT% --browser.gatherUsageStats false
set "APP_EXIT_CODE=%ERRORLEVEL%"

if not "%APP_EXIT_CODE%"=="0" (
    echo.
    echo Streamlit stopped with exit code %APP_EXIT_CODE%.
    goto :failed
)

endlocal
exit /b 0

:install_failed
echo.
echo ERROR: Could not install dependencies from requirements.txt.

:failed
echo.
if not defined NO_PAUSE pause
endlocal
exit /b 1
