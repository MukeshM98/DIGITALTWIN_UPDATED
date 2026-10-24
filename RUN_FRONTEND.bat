@echo off
cd /d "%~dp0frontend"
echo Starting FloodSense DT Frontend at http://localhost:5173...
py -m http.server 5173
pause