@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
py -3.12 -X utf8 "%~dp0scripts\prepare_recovery_bundle.py" %*
set "recovery_exit=%errorlevel%"
if not "%recovery_exit%"=="0" echo Neu khong tim thay Python, hay kiem tra: py -3.12 --version
echo.
pause
exit /b %recovery_exit%
