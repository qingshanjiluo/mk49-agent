@echo off
set A=%~1
if not "%A%"=="" goto direct
echo ============================================
echo    mk49-agent control
echo    1  Status   show status
echo    2  Stop     stop loop+dashboard
echo    3  Restart  stop then start
echo    4  Start    start if not running
echo    5  Open dashboard page
echo    0  Exit
echo ============================================
choice /c 123450 /n /m "Select: "
if errorlevel 6 goto done
if errorlevel 5 set A=open& goto direct
if errorlevel 4 set A=start& goto direct
if errorlevel 3 set A=restart& goto direct
if errorlevel 2 set A=stop& goto direct
if errorlevel 1 set A=status& goto direct
goto done
:direct
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mk49-ctl.ps1" %A%
:done
pause
