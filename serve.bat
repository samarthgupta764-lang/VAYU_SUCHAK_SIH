@echo off
setlocal enabledelayedexpansion
rem
rem VAYU-SUCHAK dev server launcher (Windows).
rem
rem   serve.bat            start in the foreground (Ctrl-C to stop)
rem   serve.bat --bg       start in the background, log to backend\data\server.log
rem   serve.bat --stop     stop whatever is listening on the port
rem   serve.bat --restart  stop then start (foreground)
rem
rem PORT / HOST env vars override the defaults, e.g.  set PORT=9000 && serve.bat
rem

set "REPO_ROOT=%~dp0"
set "BACKEND=%REPO_ROOT%backend"
if not defined PORT set "PORT=8000"
if not defined HOST set "HOST=127.0.0.1"
set "PY=%BACKEND%\.venv\Scripts\python.exe"
set "LOG=%BACKEND%\data\server.log"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=--start"

if /i "%CMD%"=="-h" goto :help
if /i "%CMD%"=="--help" goto :help
if /i "%CMD%"=="--stop" goto :stop
if /i "%CMD%"=="--restart" goto :restart
if /i "%CMD%"=="--bg" goto :startbg
if /i "%CMD%"=="--fg" goto :start
if /i "%CMD%"=="--start" goto :start

echo unknown option: %CMD% (try --help) 1>&2
exit /b 1

:help
echo   serve.bat            start in the foreground (Ctrl-C to stop)
echo   serve.bat --bg       start in the background, log to backend\data\server.log
echo   serve.bat --stop     stop whatever is listening on the port
echo   serve.bat --restart  stop then start (foreground)
exit /b 0

:preflight
if not exist "%PY%" (
  echo error: venv not found at %PY% 1>&2
  echo   cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt 1>&2
  echo   .venv\Scripts\playwright install chromium 1>&2
  exit /b 1
)
exit /b 0

:stop
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"TCP.*:%PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo stopping server on :%PORT% ^(pid %%P^)
  taskkill /F /PID %%P >nul 2>&1
)
if not defined FOUND echo nothing listening on :%PORT%
exit /b 0

:restart
call :preflight
if errorlevel 1 exit /b 1
call :stop
goto :start

:start
call :preflight
if errorlevel 1 exit /b 1
call :stop
cd /d "%BACKEND%"
echo VAYU-SUCHAK  ·  http://%HOST%:%PORT%
"%PY%" run.py
exit /b %errorlevel%

:startbg
call :preflight
if errorlevel 1 exit /b 1
call :stop
cd /d "%BACKEND%"
if not exist "%BACKEND%\data" mkdir "%BACKEND%\data"
echo VAYU-SUCHAK  ·  http://%HOST%:%PORT%
start "VAYU-SUCHAK server" /min cmd /c ""%PY%" run.py > "%LOG%" 2>&1"
timeout /t 3 /nobreak >nul
set "RUNNING="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"TCP.*:%PORT% .*LISTENING"') do set "RUNNING=%%P"
if defined RUNNING (
  echo running in background ^(pid %RUNNING%^) · logs: %LOG%
) else (
  echo failed to start — check %LOG% 1>&2
  exit /b 1
)
exit /b 0
