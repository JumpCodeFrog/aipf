@echo off
setlocal

where aipf >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Command 'aipf' not found.
  echo Install the project first:
  echo   pipx install -e .
  echo   pipx inject aipf pytest pytest-asyncio respx ruff mypy
  echo.
  pause
  exit /b 1
)

aipf interactive --pause
set EXIT_CODE=%ERRORLEVEL%
exit /b %EXIT_CODE%
