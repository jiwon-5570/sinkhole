@echo off
setlocal
set "ROOT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%Install_Sinkhole.ps1"
exit /b %ERRORLEVEL%

