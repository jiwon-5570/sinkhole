@echo off
setlocal
set "ROOT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%Run_Sinkhole.ps1"
exit /b %ERRORLEVEL%

