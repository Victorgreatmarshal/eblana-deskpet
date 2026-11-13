@echo off
chcp 65001 >nul
title 死芒桌宠
rem 在 Windows 上从源码运行：双击这个文件即可（首次运行会自动准备环境）
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo 没有找到 Python。请先安装 Python 3.10 或更新版本，安装时勾选 "Add python.exe to PATH"。
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist .venv\Scripts\pythonw.exe (
    echo 首次运行，正在创建虚拟环境并安装依赖，大约需要一两分钟...
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

start "" .venv\Scripts\pythonw.exe main.py
