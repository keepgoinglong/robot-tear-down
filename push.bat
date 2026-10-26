@echo off
rem ============================================================
rem  push this folder to https://github.com/keepgoinglong/robot-tear-down
rem  double-click it. Git for Windows must be installed.
rem  first push may open a browser window to sign in to GitHub
rem  (or ask for a Personal Access Token as the password).
rem ============================================================
setlocal
cd /d "%~dp0"
set REPO=https://github.com/keepgoinglong/robot-tear-down.git

where git >nul 2>&1
if errorlevel 1 goto nogit

git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
  echo [i] initialising repository
  git init -b main
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin %REPO%
) else (
  git remote set-url origin %REPO%
)

echo [i] committing local changes
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git -c user.name="robot-tear-down" -c user.email="robot-tear-down@users.noreply.github.com" commit -m "robot teardown page + CAD-to-web pipeline"
)

echo [i] checking remote
git fetch origin main
git rev-parse --verify origin/main >nul 2>&1
if errorlevel 1 goto push

echo [i] remote already has commits - merging first
git pull --rebase --allow-unrelated-histories origin main
if errorlevel 1 goto conflict

:push
echo [i] pushing
git push -u origin main
if errorlevel 1 goto failed

echo.
echo [OK] pushed to https://github.com/keepgoinglong/robot-tear-down
echo      next: Settings - Pages - Source: main / (root) to publish the page
start "" https://github.com/keepgoinglong/robot-tear-down
pause
exit /b 0

:nogit
echo [!] Git not found. Install Git for Windows: https://git-scm.com/download/win
pause
exit /b 1

:conflict
echo [!] merge conflict - resolve the files listed above, then run this again
pause
exit /b 1

:failed
echo.
echo [!] push failed. Check network / proxy, and make sure your account has
echo     write access. If GitHub asks for a password, paste a Personal Access
echo     Token (classic, scope: repo).
pause
exit /b 1