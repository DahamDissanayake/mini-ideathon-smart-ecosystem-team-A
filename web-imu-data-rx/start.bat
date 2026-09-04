@echo off
REM Serves the IMU dashboard on http://localhost:8000 and opens it in Chrome or Edge.
REM
REM Web Bluetooth needs a secure context, so localhost is required - file:// will not work.
REM The browser matters too: Firefox and Safari do not implement Web Bluetooth at all, and
REM Brave ships it disabled (enable brave://flags/#brave-web-bluetooth-api if you prefer Brave).
REM That is why this script picks Chrome/Edge explicitly instead of the default browser.

cd /d "%~dp0"

echo Starting IMU dashboard server on http://localhost:8000
start "imu-dashboard server" /min python -m http.server 8000 --bind 127.0.0.1

REM Give the server a moment before the browser asks for the page
timeout /t 2 /nobreak >nul

set "BROWSER="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe"      set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"  set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"       set "BROWSER=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"      set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if defined BROWSER (
  echo Opening in "%BROWSER%"
  start "" "%BROWSER%" "http://localhost:8000"
) else (
  echo Chrome/Edge not found - opening the default browser.
  echo If it is not Chromium-based, Web Bluetooth will be unavailable.
  start "" "http://localhost:8000"
)

echo.
echo The server runs in the minimised "imu-dashboard server" window -
echo close that window to stop it.
echo.
pause
