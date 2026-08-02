@echo off
setlocal
if /I "%~1"=="--refresh-db-from-nas" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-start.ps1" -RefreshDbFromNas
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-start.ps1" %*
)
exit /b %ERRORLEVEL%
