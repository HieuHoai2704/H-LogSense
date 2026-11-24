@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run Install-H-logsen.cmd first.
    popd
    pause
    exit /b 1
)
if "%~1"=="" (
    start "" ".venv\Scripts\pythonw.exe" -I -m app.workbench --desktop
    popd
    exit /b 0
)
".venv\Scripts\python.exe" -I -m app.workbench %*
set "RESULT=%ERRORLEVEL%"
popd
if not "%RESULT%"=="0" pause
exit /b %RESULT%
