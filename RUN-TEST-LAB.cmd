@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Create the Python environment first. See TEST-LAB.md.
 pause
 exit /b 1
)
.venv\Scripts\python.exe scripts\test_lab.py --ui
set "LAB_EXIT=%errorlevel%"
pause
exit /b %LAB_EXIT%
