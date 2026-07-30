@echo off
setlocal
set "PUBLIC_REPO=%~dp0"
set "PRIVATE_SCANNER=C:\Users\15183\Documents\Codex\2026-07-27\ca\outputs\volume-scanner-hh-ll"
set "PYTHON=%PRIVATE_SCANNER%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Scanner Python environment not found: %PYTHON%
  exit /b 1
)

echo Building credential-free public snapshot...
"%PYTHON%" "%PUBLIC_REPO%publish_snapshot.py" --source "%PRIVATE_SCANNER%" --output "%PUBLIC_REPO%data"
if errorlevel 1 exit /b 1

cd /d "%PUBLIC_REPO%"
git -c safe.directory="%PUBLIC_REPO%" add data\watchlist.csv data\scanner-results.csv
git -c safe.directory="%PUBLIC_REPO%" diff --quiet --cached -- data\watchlist.csv data\scanner-results.csv
if not errorlevel 1 (
  echo No changes to publish.
  exit /b 0
)
git -c safe.directory="%PUBLIC_REPO%" commit -m "Update scanner snapshot"
git -c safe.directory="%PUBLIC_REPO%" push origin main
if errorlevel 1 (
  echo Push failed. Check GitHub authentication and branch name.
  exit /b 1
)
echo Public scanner updated successfully.
endlocal
