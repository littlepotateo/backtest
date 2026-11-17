@echo off
rem Starts the dashboard on Windows. The first run sets everything up (about a minute).
cd /d "%~dp0"

if exist .venv\Scripts\python.exe goto have_venv
set PY=
for %%V in (3.13 3.12 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set PY=py -%%V
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set PY=python
)
if not defined PY (
  echo This needs Python 3.11 or newer, and none was found.
  echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run this again.
  pause
  exit /b 1
)
echo Setting up ^(first run only^) ...
%PY% -m venv .venv
if errorlevel 1 ( echo Could not create the .venv folder. & pause & exit /b 1 )

:have_venv
rem Keep the installed packages in step with pyproject.toml. When nothing changed this takes a few seconds.
echo Checking installed packages ...
.venv\Scripts\python -m pip install --quiet --upgrade pip > .venv\install.log 2>&1
.venv\Scripts\python -m pip install --quiet -e . >> .venv\install.log 2>&1
if errorlevel 1 ( type .venv\install.log & echo Installation failed ^(see above^). & pause & exit /b 1 )
rem Read and write every file as UTF-8 (Windows would otherwise use a legacy code page and fail on letters such as the fi ligature in papers).
set PYTHONUTF8=1
.venv\Scripts\bt serve --open %*
if errorlevel 1 pause
