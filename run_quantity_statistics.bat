REM 批处理文件用于运行用量统计脚本
REM 此文件将执行quantity_statistics.py，收集所有PLC数据并生成统计报表

REM 设置批处理文件所在目录为当前工作目录
cd /d "%~dp0"

echo 正在运行用量统计工具...
echo 请稍候，正在收集和处理数据...

REM 使用相对路径运行Python脚本
python datacollection\quantity_statistics.py

IF %ERRORLEVEL% EQU 0 (
echo 用量统计工具运行成功！
echo 统计结果已保存至output目录的"用量统计.xlsx"文件

echo.
echo 按任意键退出...
pause >nul
) ELSE (
echo 用量统计工具运行失败！

echo.
echo 按任意键退出...
pause >nul
)