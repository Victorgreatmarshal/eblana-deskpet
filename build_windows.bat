@echo off
chcp 65001 >nul
title 死芒桌宠 · Windows 打包
rem 生成 dist\EblanaDeskPet\EblanaDeskPet.exe；装有 Inno Setup 时再生成安装包 Output\EblanaDeskPet_Setup.exe
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller || goto :fail

echo 正在打包程序...
.venv\Scripts\pyinstaller --noconfirm --clean EblanaDeskPet.spec || goto :fail

set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
where iscc >nul 2>nul && set "ISCC=iscc"

if defined ISCC (
    echo 正在生成安装包...
    "%ISCC%" installer.iss || goto :fail
    echo.
    echo 完成：安装包在 Output\EblanaDeskPet_Setup.exe
) else (
    echo.
    echo 完成：免安装版在 dist\EblanaDeskPet\EblanaDeskPet.exe
    echo 想要安装包的话，装好 Inno Setup 6 后重新运行这个脚本：https://jrsoftware.org/isdl.php
)
pause
exit /b 0

:fail
echo 打包失败，请查看上面的错误信息。
pause
exit /b 1
