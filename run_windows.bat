@echo off
setlocal
cd /d "%~dp0"
if not defined LOCAL_AGENT_HUB_VENV set "LOCAL_AGENT_HUB_VENV=%~dp0.venv"
if not exist "%LOCAL_AGENT_HUB_VENV%\Scripts\python.exe" (
  echo [1/2] Creating local Python environment...
  py -3 -m venv "%LOCAL_AGENT_HUB_VENV%" 2>nul || python -m venv "%LOCAL_AGENT_HUB_VENV%"
  if errorlevel 1 (
    echo Could not create a virtual environment. Install Python 3.10+ and try again.
    pause
    exit /b 1
  )
)
call "%LOCAL_AGENT_HUB_VENV%\Scripts\activate.bat"
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
