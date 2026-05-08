@echo off
setlocal
set "ROOT_DIR=%~dp0"
call "%ROOT_DIR%Run_Sinkhole.cmd"
exit /b %ERRORLEVEL%
