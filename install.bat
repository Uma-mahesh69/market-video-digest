@echo off
rem Double-click to set up (or update) the market video digest.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
