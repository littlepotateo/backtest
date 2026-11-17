@echo off
rem Brings the program up to date from GitHub before the dashboard starts, so a restart can never run an old version.
rem (The explicit refspec makes the fetch work even in a clone whose remote has none configured.)
rem It never stops the start-up: any problem is reported in plain words and the code you already have is used.
rem Opt out by setting the environment variable BACKTEST_NO_UPDATE=1.
cd /d "%~dp0.."
if defined BACKTEST_NO_UPDATE exit /b 0
if not exist .git exit /b 0
where git >nul 2>&1
if errorlevel 1 (
  echo Git was not found, so the program cannot update itself. Starting with the code you have.
  exit /b 0
)
set "BRANCH="
for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
git fetch --quiet origin "+refs/heads/*:refs/remotes/origin/*" >nul 2>&1
if errorlevel 1 (
  echo Could not check for updates ^(no internet connection?^). Starting with the code you have.
  exit /b 0
)
if "%BRANCH%"=="main" goto on_main
rem Never leave work that exists only on this computer: switch only if every commit here is also on GitHub.
git branch -r --contains HEAD > "%TEMP%\bt_remote_branches.txt" 2>nul
set "REMOTE_SIZE=0"
for %%F in ("%TEMP%\bt_remote_branches.txt") do set "REMOTE_SIZE=%%~zF"
del "%TEMP%\bt_remote_branches.txt" >nul 2>&1
if "%REMOTE_SIZE%"=="0" (
  echo You are on the branch '%BRANCH%', which has commits that are only on this computer, so it was left alone and no update was made.
  exit /b 0
)
git checkout --quiet main >nul 2>&1
if errorlevel 1 (
  echo You are on the branch '%BRANCH%' and could not switch to 'main' because of local changes. Starting with the code you have.
  echo To update by hand: git stash push -u, git checkout main, git pull origin main, git stash pop
  exit /b 0
)
echo Switched from '%BRANCH%' to 'main', the branch that carries the latest released program.
:on_main
set "BEFORE="
for /f %%H in ('git rev-parse --short HEAD') do set "BEFORE=%%H"
git merge --ff-only --quiet origin/main >nul 2>&1
if errorlevel 1 (
  echo Could not update automatically ^(a file you changed is also changed in the new version^). Starting with the code you have ^(version %BEFORE%^).
  echo To update by hand: git stash push -u, then git pull origin main, then git stash pop
  exit /b 0
)
set "AFTER="
for /f %%H in ('git rev-parse --short HEAD') do set "AFTER=%%H"
if not "%BEFORE%"=="%AFTER%" echo Updated the program: %BEFORE% to %AFTER%.
exit /b 0
