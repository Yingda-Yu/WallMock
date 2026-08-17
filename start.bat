@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

set PYTHON_CMD=
set PYTHON_FOUND=0

echo ========================================
echo   WallMock - 壁纸样机生成工具
echo ========================================
echo.

echo [1/3] 正在检测 Python 环境...

where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=python
    set PYTHON_FOUND=1
    goto :python_ok
)

where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py
    set PYTHON_FOUND=1
    goto :python_ok
)

if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    set PYTHON_FOUND=1
    goto :python_ok
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe" (
    set "PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
    set PYTHON_FOUND=1
    goto :python_ok
)
if exist "D:\Anaconda\python.exe" (
    set "PYTHON_CMD=D:\Anaconda\python.exe"
    set PYTHON_FOUND=1
    goto :python_ok
)

:python_not_found
echo.
echo [错误] 未检测到 Python，请先安装 Python 3.9 或更高版本。
echo 下载地址: https://www.python.org/downloads/
echo.
pause
exit /b 1

:python_ok
echo       Python 已找到: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

echo [2/3] 检查并安装依赖...
%PYTHON_CMD% -m pip show Pillow >nul 2>&1
if %errorlevel% neq 0 (
    echo       正在安装依赖包，请稍候...
    %PYTHON_CMD% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo       清华源安装失败，尝试默认源...
        %PYTHON_CMD% -m pip install -r requirements.txt
    )
) else (
    echo       依赖已安装
)
echo.

echo [3/3] 正在启动服务...
echo.
echo 服务启动后将自动打开浏览器。
echo 请勿关闭此窗口，关闭窗口将停止服务。
echo.
echo 访问地址: http://127.0.0.1:5876
echo.

start "" "%PYTHON_CMD%" -c "import time; time.sleep(1.5); import webbrowser; webbrowser.open('http://127.0.0.1:5876')"

%PYTHON_CMD% app.py

pause
