@echo off
REM Windows 一键启动 Discord Bot
cd /d "%~dp0"

if not exist .env (
    copy .env.example .env
    echo 请编辑 .env 文件填入 Token 后重新运行
    pause
    exit /b 1
)

pip install -r requirements.txt -q
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set %%a=%%b

python main.py
pause
