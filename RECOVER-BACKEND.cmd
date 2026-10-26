@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
  py -3.12 -X utf8 "%~dp0backend\recover_state.py" --gui
  goto finished
)
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" --version >nul 2>&1
  if not errorlevel 1 (
    "%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0backend\recover_state.py" --gui
    goto finished
  )
)
echo Python 3.12 was not found. Install it, reopen this window, and retry:
echo winget install --exact --id Python.Python.3.12
:finished
echo.
echo See BACKEND-RECOVERY.md for instructions and command-line alternatives.
pause
endlocal
