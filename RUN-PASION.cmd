@echo off
setlocal
cd /d "%~dp0"
node --version >nul 2>&1
if errorlevel 1 (
  echo Node.js was not found. Install Node.js LTS with npm from https://nodejs.org/
  echo Reopen this window after installation, then run RUN-PASION.cmd again.
  pause
  exit /b 1
)
call npm.cmd run dev
set "PASION_RUN_EXIT=%errorlevel%"
if not "%PASION_RUN_EXIT%"=="0" (
  echo.
  echo PASION could not start or stopped with an error. Read the messages above.
  echo For missing packages, run npm.cmd ci in this folder and retry.
  echo For Python setup, follow README.md or BACKEND-RECOVERY.md.
  pause
)
exit /b %PASION_RUN_EXIT%
