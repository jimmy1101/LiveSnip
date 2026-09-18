@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" wscript.exe "%~dp0run.vbs"
exit
