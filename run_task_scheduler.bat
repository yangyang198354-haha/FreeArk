@echo off
chcp 65001 >nul

REM Task Scheduler Launcher

echo =============================================================
echo Task Scheduler Started
echo This script will run TaskScheduler to collect data periodically
echo Config file: resource/task_scheduler_config.json
Press Ctrl+C to stop
=============================================================

REM Check Python installation
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python not found. Please install Python and add to system PATH.
    pause
    exit /b 1
)

REM Change to script directory
cd /d "%~dp0"

REM Run task scheduler
echo Starting task scheduler...
echo Please check console output for status...
echo. 

python datacollection/run_task_scheduler.py

REM Check exit code
if %errorlevel% neq 0 (
    echo Task scheduler exited with error code: %errorlevel%
    pause
    exit /b %errorlevel%
)

echo Task scheduler exited normally
pause