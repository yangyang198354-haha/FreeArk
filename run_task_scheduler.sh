#!/bin/bash

# Set UTF-8 locale for proper character encoding
export LANG=en_US.UTF-8

# Task Scheduler Launcher
echo "============================================================="
echo "Task Scheduler Started"
echo "This script will run TaskScheduler to collect data periodically"
echo "Config file: resource/task_scheduler_config.json"
echo "Press Ctrl+C to stop"
echo "============================================================="

# Check if Python is installed
if command -v python3 > /dev/null 2>&1; then
    PYTHON=python3
elif command -v python > /dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: Python not found. Please install Python and add to system PATH."
exit 1
fi

# Change to the project root directory
cd "$(dirname "$0")" || exit 1

# Run the task scheduler
echo "Starting task scheduler..."
echo "Please check console output for status..."
echo ""

$PYTHON datacollection/run_task_scheduler.py

# Check if the script exited with an error
if [ $? -ne 0 ]; then
    echo "Task scheduler exited with error code: $?"
exit 1
fi

echo "Task scheduler exited normally"