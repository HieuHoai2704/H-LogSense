@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1

if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto from_path
for %%V in (3.13 3.12 3.11 3.10) do (
    py -%%V -c "import platform,sys; sys.exit(sys.maxsize <= 2**32 or platform.machine().lower() not in ('amd64','x86_64'))" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_VERSION=%%V"
        goto from_launcher
    )
)

:from_path
python -c "import platform,sys; sys.exit(not ((3, 10) <= sys.version_info[:2] < (3, 14) and sys.maxsize > 2**32 and platform.machine().lower() in ('amd64','x86_64')))" >nul 2>nul
if errorlevel 1 goto python_required
python -m venv ".venv"
if errorlevel 1 goto failed
goto install

:from_launcher
py -%PYTHON_VERSION% -m venv ".venv"
if errorlevel 1 goto failed

:install
set "PACKAGE="
for %%W in (h_logsen-*.whl) do if exist "%%W" (
    if defined PACKAGE goto multiple
    set "PACKAGE=%%W"
)
if not defined PACKAGE if exist "pyproject.toml" set "PACKAGE=."
if not defined PACKAGE goto package_required
if "%PACKAGE%"=="." (
    ".venv\Scripts\python.exe" -m pip --isolated install .
) else (
    ".venv\Scripts\python.exe" -m pip --isolated install --prefer-binary "%PACKAGE%"
)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -I -m app.workbench.windows
if errorlevel 1 echo Could not update Windows shortcuts. Open-H-logsen.cmd is still available.
echo.
echo H-logsen installed. Double-click Open-H-logsen.cmd to start.
popd
exit /b 0

:python_required
echo Python 3.10 to 3.13 x64 is required. Install Python, then run this file again.
goto failed
:multiple
echo Keep one H-logsen wheel in this folder.
goto failed
:package_required
echo H-logsen package missing. Extract the whole ZIP into a folder first.
:failed
echo Installation did not finish.
popd
if /i not "%~1"=="--no-pause" pause
exit /b 1
