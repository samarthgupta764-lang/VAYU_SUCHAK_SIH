@echo off
rem
rem Double-click this file in File Explorer to start the VAYU-SUCHAK server.
rem It opens a console window, starts the backend (via serve.bat), and opens
rem the dashboard in your browser once it's up. Close the console window
rem (or press Ctrl-C in it) to stop the server.
rem
cd /d "%~dp0"

if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8000"

rem open the dashboard once the server responds (don't block server startup on it)
start "" /min cmd /c "for /l %%i in (1,1,30) do (timeout /t 1 /nobreak >nul & curl -s -o nul http://%HOST%:%PORT%/ && (start "" http://%HOST%:%PORT%/ & exit /b))"

call serve.bat
pause
