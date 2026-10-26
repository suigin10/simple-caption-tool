@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import PySide6, PIL" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto failed
)
if not exist ".venv\Scripts\pythonw.exe" goto failed
start "" "%~dp0.venv\Scripts\pythonw.exe" -m captioner
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. See README.md for setup instructions.
pause
exit /b 1
