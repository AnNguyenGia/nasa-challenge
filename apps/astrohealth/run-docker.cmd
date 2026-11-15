@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-docker.ps1" %*
exit /b %errorlevel%
