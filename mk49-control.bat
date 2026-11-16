@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "A=%~1"
if not "%A%"=="" goto direct
:menu
cls
echo ==================================================
echo    mk49-agent Control Center
echo    project: %~dp0
echo ==================================================
echo    [1] Status    process/port/forum status
echo    [2] Stop      stop loop + dashboard
echo    [3] Restart   stop then start both
echo    [4] Start     start if not running
echo    [5] Dashboard open http://127.0.0.1:8899
echo    [6] Log       open full loop.log in notepad
echo    [7] Console   tail loop.log (last 60 lines)
echo    [0] Exit
echo ==================================================
choice /c 12345670 /n /m "  Select [1-7, 0=exit]: "
if errorlevel 8 goto done
if errorlevel 7 goto op7
if errorlevel 6 goto op6
if errorlevel 5 goto op5
if errorlevel 4 goto op4
if errorlevel 3 goto op3
if errorlevel 2 goto op2
if errorlevel 1 goto op1
goto menu
:op1
set "A=status"
goto run
:op2
set "A=stop"
goto run
:op3
set "A=restart"
goto run
:op4
set "A=start"
goto run
:op5
set "A=open"
goto run
:op6
start "" notepad "%~dp0state\loop.log"
goto menu
:op7
powershell -NoProfile -Command "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); Get-Content -Path '%~dp0state\loop.log' -Tail 60 -Encoding UTF8"
goto pausemenu
:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mk49-ctl.ps1" %A%
:pausemenu
echo.
echo  --- press any key to return to menu ---
pause >nul
goto menu
:direct
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mk49-ctl.ps1" %A%
goto done
:done
endlocal
