@echo off
cd /d "%~dp0"
if not exist "translation\.venv\Scripts\python.exe" (
  echo Run setup.cmd first.
  pause
  exit /b 1
)
"translation\.venv\Scripts\python.exe" scripts\doctor.py %*
pause
