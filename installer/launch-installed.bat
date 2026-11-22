@echo off
setlocal
if not defined LOCALAPPDATA (
  echo Local AppData folder could not be found.
  pause
  exit /b 1
)
set "LOCAL_AGENT_HUB_DATA_DIR=%LOCALAPPDATA%\Local Agent Hub"
set "LOCAL_AGENT_HUB_VENV=%LOCAL_AGENT_HUB_DATA_DIR%\.venv"
if not exist "%LOCAL_AGENT_HUB_DATA_DIR%" mkdir "%LOCAL_AGENT_HUB_DATA_DIR%"
call "%~dp0run_windows.bat"
