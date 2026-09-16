@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11 x64 or activate a Python 3.11 Conda environment first.
  pause
  exit /b 1
)
python scripts\setup.py %*
if errorlevel 1 (
  echo Setup failed. See the error above. You can rerun this command.
  pause
  exit /b 1
)
echo Ready. Double-click start.cmd.
pause
