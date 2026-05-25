@echo off
chcp 65001 >nul
echo ================================================
echo   场景机会与能力匹配 Demo — 一键启动
echo ================================================
echo.

cd /d "%~dp0"

echo [1/2] 检查依赖...
pip install -r requirements.txt -q
echo.

echo [2/2] 启动 Flask 服务...
echo.
python app.py

pause
