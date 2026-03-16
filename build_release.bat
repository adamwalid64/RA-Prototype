@echo off
setlocal
python "%~dp0build_release.py"
if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Build completed successfully.
pause
