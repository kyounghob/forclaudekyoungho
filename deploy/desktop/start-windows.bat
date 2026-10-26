@echo off
rem ETF learning recommender - pilot server on this Windows PC.
rem First run creates a virtual environment (.venv) and installs the packages, then starts "python -m etfrec desktop".
cd /d "%~dp0\..\.."
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating a virtual environment and installing packages. This takes a few minutes...
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>nul && py -3 -m venv .venv
  if not exist ".venv\Scripts\python.exe" python -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>nul && python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [setup] Python 3.11 or newer is required. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
  if errorlevel 1 (
    echo [setup] Package installation failed. Check the internet connection and run this file again.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m etfrec desktop %*
pause
