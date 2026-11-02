@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 scripts\setup.py
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe scripts\setup.py
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m liquidframe %*
goto :eof
:failed
echo Install Python 3.11+ and Node.js LTS, then try again.
pause
