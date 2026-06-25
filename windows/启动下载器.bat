@echo off
chcp 65001 >nul
title Multporn 漫画下载器
cd /d "%~dp0"

echo ========================================
echo   Multporn 批量漫画下载器
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.7+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: 安装依赖
echo [1/2] 检查依赖...
pip install requests beautifulsoup4 tqdm -q
if %errorlevel% neq 0 (
    echo [警告] pip 安装失败，尝试使用镜像源...
    pip install requests beautifulsoup4 tqdm -q -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo [2/2] 启动下载器...
echo.

:: 交互式菜单
:menu
cls
echo ========================================
echo   Multporn 批量漫画下载器
echo ========================================
echo.
echo   [1] 下载单部漫画（输入URL）
echo   [2] 批量下载多部漫画（粘贴多个URL，一行一个）
echo   [3] 从分类页批量下载
echo   [4] 关键词搜索下载
echo   [0] 退出
echo.
set /p choice="请选择 [0-4]: "

if "%choice%"=="0" goto :end
if "%choice%"=="1" goto :single
if "%choice%"=="2" goto :batch
if "%choice%"=="3" goto :list
if "%choice%"=="4" goto :search
goto :menu

:single
echo.
set /p url="粘贴漫画URL: "
echo.
python multporn_downloader.py -u "%url%" -o ".\Downloads"
echo.
pause
goto :menu

:batch
echo.
echo 将多个URL粘贴到 urls.txt 中（一行一个），然后按任意键继续...
echo.
type nul > urls.txt
start notepad urls.txt
pause
echo.
setlocal enabledelayedexpansion
set "cmd_args="
for /f "usebackq delims=" %%u in ("urls.txt") do (
    set "line=%%u"
    if not "!line!"=="" set "cmd_args=!cmd_args! -u "!line!""
)
if "!cmd_args!"=="" (
    echo urls.txt 为空，请先填入URL
    pause
    goto :menu
)
python multporn_downloader.py !cmd_args! -o ".\Downloads"
endlocal
echo.
pause
goto :menu

:list
echo.
set /p listurl="粘贴分类页URL（如 https://multporn.net/new?type=1）: "
set /p maxnum="最多下载几部？[默认50]: "
if "%maxnum%"=="" set maxnum=50
echo.
python multporn_downloader.py -l "%listurl%" --max %maxnum% -o ".\Downloads"
echo.
pause
goto :menu

:search
echo.
set /p keyword="搜索关键词: "
set /p maxnum="最多下载几部？[默认20]: "
if "%maxnum%"=="" set maxnum=20
echo.
python multporn_downloader.py -s "%keyword%" --max %maxnum% -o ".\Downloads"
echo.
pause
goto :menu

:end
echo 再见~
exit /b 0
