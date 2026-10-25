@echo off
rem 黄金矿工 一键启动（优先用 pythonw：不带黑色控制台窗口）
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
) else (
    python main.py
    pause
)
