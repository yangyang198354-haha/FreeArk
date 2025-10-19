@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: FreeArk ?????????????

:: ??Python????
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ??:???Python!
    echo ????Python 3.8??????
    echo ===============================================================================
    pause
    exit /b 1
)

:: ??Python??
echo ??Python??...
python --version

:: ????
echo ===============================================================================
echo ?????...
python -m pip install --upgrade pip

:: ????snap7(?GitHub????)
echo ??snap7?...
python -m pip install python-snap7

:: ??????
python -m pip install pandas>=1.0.0 openpyxl>=3.0.0 paho-mqtt>=1.5.0
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ??:???????!
    echo ????????Python???
    echo ===============================================================================
    pause
    exit /b 1
)

:: ??????
echo ===============================================================================
echo ??????...
python -m pip install setuptools wheel
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ??:????????!
    echo ????????Python???
    echo ===============================================================================
    pause
    exit /b 1
)

:: ???Wheel
echo ===============================================================================
echo ???Wheel??...
python setup.py bdist_wheel
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ??:???Wheel????!
    echo ===============================================================================
    pause
    exit /b 1
)
echo ????!Wheel?????? dist ????

:: ????????
echo ===============================================================================
echo ????????...
python -m pip install -e .
if %ERRORLEVEL% neq 0 (
    echo ===============================================================================
    echo ??:?????!
    echo ===============================================================================
    pause
    exit /b 1
)

echo ????!??????????????:
echo   - run-data-collection -f [????]

:: ??????
echo ===============================================================================
echo FreeArk ??????????!
echo ???????????:
echo 1. ??pip????????:
echo    - run-data-collection -f [????]
echo 2. ????Python??:
echo    - python datacollection\improved_data_collection_manager.py
echo    - python datacollection\plc_data_viewer_gui.py
echo    - python datacollection\quantity_statistics.py
echo 3. ???????????:
echo    - run_improved_data_collection_manager.bat
echo    - run_plc_data_viewer_gui.bat
echo    - run_quantity_statistics.bat
echo 4. Wheel???:
echo    - dist\freeark_datacollection-1.0.0-py3-none-any.whl
echo    ???????Windows???? pip install [wheel????] ??

echo ===============================================================================
pause
endlocal
