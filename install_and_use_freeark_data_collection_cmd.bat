@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ===============================================================================
echo                    FreeArk Data Collection System - Install and Configure
echo ===============================================================================

:: Check Python environment
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo Error: Python not found!
    echo Please install Python 3.8 or higher first
    echo ===============================================================================
    pause
    exit /b 1
)

:: Show Python version
echo Checking Python version...
python --version

:: Upgrade pip
echo ===============================================================================
echo Upgrading pip...
python -m pip install --upgrade pip

:: Install snap7 from PyPI
echo Installing snap7...
python -m pip install python-snap7

:: Install project dependencies
echo Installing project dependencies...
python -m pip install pandas>=1.0.0 openpyxl>=3.0.0 paho-mqtt>=1.5.0
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo Error: Failed to install project dependencies!
    echo Please check Python environment and network connection
    echo ===============================================================================
    pause
    exit /b 1
)

:: Install packaging tools
echo ===============================================================================
echo Installing packaging tools...
python -m pip install setuptools wheel
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo Error: Failed to install packaging tools!
    echo Please check Python environment and network connection
    echo ===============================================================================
    pause
    exit /b 1
)

:: Build Wheel package
echo ===============================================================================
echo Building Wheel package...
python setup.py bdist_wheel
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo Error: Failed to build Wheel package!
    echo ===============================================================================
    pause
    exit /b 1
)
echo Success! Wheel package generated in dist directory

:: Install project locally
echo ===============================================================================
echo Installing project locally...
python -m pip install -e .
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo Error: Failed to install project!
    echo ===============================================================================
    pause
    exit /b 1
)

echo Success! Command-line tool installed, usage:
echo   - run-data-collection -f [config_file]

:: Show usage instructions
echo ===============================================================================
echo FreeArk Data Collection System installation completed!
echo The system provides the following run methods:
echo 1. Command-line tool installed via pip:
echo    - run-data-collection -f [config_file]
echo 2. Run Python scripts directly:
echo    - python datacollection\improved_data_collection_manager.py
echo    - python datacollection\plc_data_viewer_gui.py
echo    - python datacollection\quantity_statistics.py
echo 3. Run via batch files:
echo    - run_improved_data_collection_manager.bat
echo    - run_plc_data_viewer_gui.bat
echo    - run_quantity_statistics.bat
echo 4. Wheel package deployment:
echo    - dist\freeark_datacollection-1.0.0-py3-none-any.whl
echo    Can be installed on other Windows environments via pip install [wheel_path]

echo ===============================================================================
echo Installation complete! Press any key to exit...
pause
endlocal
