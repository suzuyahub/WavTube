@echo off
rem ============================================================
rem  WavTube mp3+  build + installer creation (double-click to run)
rem  - Installs Python 3.12 via winget if missing (same as the old updater tool)
rem  - Then runs build_installer.py (pip -> deno -> PyInstaller -> Inno Setup)
rem  Add --skip-pip to rebuild quickly without updating libraries.
rem ============================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

call :find_python
if not defined PYCMD (
    echo Python 3.12 was not found. Installing with winget...
    winget install --id Python.Python.3.12 -e --scope user --accept-source-agreements --accept-package-agreements
    if errorlevel 1 winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    call :find_python
)
if not defined PYCMD (
    echo.
    echo [ERROR] Python 3.12 could not be set up.
    echo Install Python 3.12 from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
)

echo Using: !PYCMD!
!PYCMD! build_installer.py %*
if errorlevel 1 (
    echo.
    echo Build failed. See the log above.
    pause
    exit /b 1
)
echo.
pause
exit /b 0

:find_python
set "PYCMD="
py -3.12 -c "import tkinter" >nul 2>nul && (set "PYCMD=py -3.12" & goto :eof)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYCMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :eof
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set PYCMD="%ProgramFiles%\Python312\python.exe"
    goto :eof
)
goto :eof
