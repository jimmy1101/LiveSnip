@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=pythonw.exe"

start "" "%PY_EXE%" "%~dp0main.py"
exit
