@echo off
chcp 65001 >nul
title 智能交通监测系统 - Traffic Monitor
setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "PIP=%VENV_DIR%\Scripts\pip.exe"

echo.
echo ╔════════════════════════════════════════════════╗
echo ║  🚗 智能交通监测与事故预警系统                 ║
echo ║  YOLOv8 + MongoDB + Redis + Neo4j              ║
echo ╚════════════════════════════════════════════════╝
echo.

:: -------- 1. Python --------
echo [1/5] Python 环境...
python --version >nul 2>&1 || (echo   ✗ 未安装 Python & pause & exit /b 1)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   ✓ Python %%v

:: -------- 2. Docker (Redis + Neo4j) --------
echo.
echo [2/5] Docker 容器 (Redis + Neo4j)...

docker ps --format "{{.Names}}" 2>nul | findstr "redis" >nul
if errorlevel 1 (
    docker start redis >nul 2>&1 && echo   ✓ Redis 已启动 || (
        docker run -d --name redis -p 6379:6379 redis:7-alpine >nul 2>&1 && echo   ✓ Redis 已创建 || echo   ⚠ Docker 不可用
    )
) else (echo   ✓ Redis 运行中)

docker ps --format "{{.Names}}" 2>nul | findstr "neo4j" >nul
if errorlevel 1 (
    docker start neo4j >nul 2>&1 && echo   ✓ Neo4j 已启动 || (
        docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/12345678 neo4j:5 >nul 2>&1 && echo   ✓ Neo4j 已创建 || echo   ⚠ Docker 不可用
    )
) else (echo   ✓ Neo4j 运行中)

:: -------- 3. MongoDB --------
echo.
echo [3/5] MongoDB...
mongosh --eval "db.version()" --quiet >nul 2>&1 && echo   ✓ MongoDB 已连接 || echo   ⚠ MongoDB 未运行

:: -------- 4. 虚拟环境 + 依赖 --------
echo.
echo [4/5] 虚拟环境 & 依赖...
if not exist "%PYTHON%" (
    echo   创建虚拟环境...
    python -m venv "%VENV_DIR%"
)
"%PYTHON%" -c "import flask,pymongo,redis" >nul 2>&1 || (
    echo   安装依赖...
    "%PIP%" install -r requirements.txt -q 2>nul
)
echo   ✓ 就绪

:: -------- 5. YOLO 模型 --------
echo.
echo [5/5] YOLO 模型...
set "M=%PROJECT_DIR%yolov8s.pt"
if not exist "%M%" set "M=%PROJECT_DIR%yolov8n.pt"
if exist "%M%" (echo   ✓ 模型: %M%) else (
    echo   ⚠ 模型未下载, 正在获取...
    "%PYTHON%" -c "import urllib.request;url='https://hf-mirror.com/ultralytics/yolov8/resolve/main/yolov8s.pt';f=r'%PROJECT_DIR%yolov8s.pt';open(f,'wb').write(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=60).read())" 2>nul
    echo   ✓ 下载完成
)

:: -------- 启动 --------
echo.
echo ════════════════════════════════════════════════
echo   启动中...  浏览器访问: http://127.0.0.1:5000
echo   Ctrl+C 停止
echo ════════════════════════════════════════════════
echo.
"%PYTHON%" app.py
pause
