@echo off
chcp 65001 >nul
echo 正在启动PLC数据查看器GUI...
python datacollection/plc_data_viewer_gui.py
pause