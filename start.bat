@echo off
chcp 65001 >nul
echo ================================================
echo   场景机会与能力匹配 Demo — 一键启动
echo ================================================
echo.

cd /d "%~dp0"

:: 设置 HuggingFace 国内镜像（避免访问 huggingface.co 超时）
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_DISABLE_IMPLICIT_TOKEN=1

:: 设置 conda 虚拟环境
set CONDA_ENV=scenedemo
set CONDA_PYTHON=%USERPROFILE%\.conda\envs\%CONDA_ENV%\python.exe

echo [1/3] 检查 conda 环境...
if exist "%CONDA_PYTHON%" (
    echo   已找到虚拟环境: %CONDA_ENV%
    set PYTHON_EXE=%CONDA_PYTHON%
) else (
    echo   [警告] 未找到虚拟环境 %CONDA_ENV%，尝试用 conda 创建...
    call conda create -n %CONDA_ENV% python=3.10 -y
    if errorlevel 1 (
        echo   [错误] 创建虚拟环境失败，回退到系统 Python
        set PYTHON_EXE=python
    ) else (
        call conda install -n %CONDA_ENV% pytorch cpuonly -c pytorch -y
        call %CONDA_PYTHON% -m pip install flask sentence-transformers pandas openpyxl -q
        set PYTHON_EXE=%CONDA_PYTHON%
        echo   虚拟环境创建完成
    )
)

echo [2/3] 检查依赖...
%PYTHON_EXE% -c "import flask, torch, sentence_transformers, pandas" 2>nul
if errorlevel 1 (
    echo   [警告] 依赖缺失，正在安装...
    %PYTHON_EXE% -m pip install flask sentence-transformers pandas openpyxl -q
)
echo   依赖就绪

echo [3/3] 启动 Flask 服务...
echo.
%PYTHON_EXE% app.py

pause
