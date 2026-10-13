@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0files\installer.ps1" -Action uninstall
