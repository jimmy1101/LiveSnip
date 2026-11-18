@echo off
chcp 65001 >nul
cd /d "%~dp0"
title LiveSnip 运行中 (请勿关闭本窗口)

set "PY_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=%LOCALAPPDATA%\Python\bin\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python.exe"

echo =======================================
echo 正在启动 LiveSnip (最新代码)...
echo Python 路径: %PY_EXE%
echo =======================================
"%PY_EXE%" "%~dp0main.py"
echo.
echo 程序已退出。
pause
