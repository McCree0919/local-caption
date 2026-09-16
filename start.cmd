@echo off
cd /d "%~dp0"
if not exist "translation\.venv\Scripts\python.exe" (
  echo Run setup.cmd with Python 3.11 first.
  pause
  exit /b 1
)
"translation\.venv\Scripts\python.exe" scripts\doctor.py
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "translation\.venv\Scripts\pythonw.exe" "app\floating_asr.py"
