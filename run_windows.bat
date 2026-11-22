@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating local Python environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Could not create a virtual environment. Install Python 3.10+ and try again.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
echo [2/2] Checking application dependencies...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your internet connection and Python setup.
  pause
  exit /b 1
)
echo Starting Local Agent Hub at http://127.0.0.1:7860
python main.py
if errorlevel 1 pause
