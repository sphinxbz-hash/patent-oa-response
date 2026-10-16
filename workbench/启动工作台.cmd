@echo off
setlocal
cd /d "%~dp0.."
set "WB_PY=python"
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "WB_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist ".venv\Scripts\python.exe" set "WB_PY=%CD%\.venv\Scripts\python.exe"
"%WB_PY%" -c "import pypdf, docx" 2>nul
if errorlevel 1 (
  echo Install dependencies from workbench\requirements.txt first. See workbench\README.md.
  pause
  exit /b 1
)
"%WB_PY%" -X utf8 -m workbench --open
if errorlevel 1 pause
endlocal
