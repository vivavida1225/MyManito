@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-stop.ps1"
exit /b %ERRORLEVEL%
