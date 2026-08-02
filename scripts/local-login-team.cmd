@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-login-team.ps1" %*
exit /b %ERRORLEVEL%
