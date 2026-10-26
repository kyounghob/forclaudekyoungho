@echo off
rem ETF learning recommender - pilot server on this Windows PC.
rem First run (or when requirements change) creates .venv and installs packages, then starts "python -m etfrec desktop".
setlocal
cd /d "%~dp0\..\.."
rem Python uses UTF-8 for files and pipes (Korean logs and data), whatever the Windows code page is.
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating a virtual environment in .venv ...
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>nul && py -3 -m venv .venv
  if not exist ".venv\Scripts\python.exe" python -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>nul && python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [setup] Python 3.11 or newer is required. Install it from https://www.python.org/downloads/
    echo [setup] and tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
  )
)

rem Install when packages were never installed, an earlier install failed, or the requirement files changed.
set NEED_INSTALL=
fc /b requirements-core.txt ".venv\installed-core.txt" >nul 2>&1 || set NEED_INSTALL=1
fc /b requirements-web.txt ".venv\installed-web.txt" >nul 2>&1 || set NEED_INSTALL=1
if defined NEED_INSTALL (
  echo [setup] Installing packages. This takes a few minutes the first time ...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
  if errorlevel 1 (
    echo [setup] Package installation failed. Check the internet connection and run this file again.
    pause
    exit /b 1
  )
  copy /y requirements-core.txt ".venv\installed-core.txt" >nul
  copy /y requirements-web.txt ".venv\installed-web.txt" >nul
)

".venv\Scripts\python.exe" -m etfrec desktop %*
pause
