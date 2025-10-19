#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用于将plc_data_viewer_gui.py打包为可执行文件的脚本
使用PyInstaller进行打包，确保包含所有必要的依赖
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def ensure_pyinstaller_installed():
    """确保PyInstaller已安装"""
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pyinstaller'], 
                      check=True, capture_output=True, text=True)
        print("✅ PyInstaller 安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装PyInstaller失败: {e}")
        print(e.stderr)
        return False

def get_project_root():
    """获取项目根目录"""
    # 获取当前脚本的目录
    script_dir = Path(__file__).resolve().parent
    return script_dir

def prepare_build_directory():
    """准备构建目录"""
    project_root = get_project_root()
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"
    
    # 清理旧的构建目录
    if build_dir.exists():
        print(f"🧹 清理旧的构建目录: {build_dir}")
        shutil.rmtree(build_dir)
    
    if dist_dir.exists():
        print(f"🧹 清理旧的发布目录: {dist_dir}")
        shutil.rmtree(dist_dir)
    
    # 创建新的目录
    build_dir.mkdir(exist_ok=True)
    dist_dir.mkdir(exist_ok=True)
    
    return project_root

def copy_resources(project_root):
    """复制必要的资源文件"""
    # 复制resource目录到构建目录
    resource_src = project_root / "resource"
    resource_dst = project_root / "dist" / "resource"
    
    if resource_src.exists():
        print(f"📁 复制资源文件到发布目录: {resource_src} -> {resource_dst}")
        shutil.copytree(resource_src, resource_dst, dirs_exist_ok=True)
    else:
        print(f"⚠️  资源目录不存在: {resource_src}")

def build_executable():
    """使用PyInstaller构建可执行文件"""
    # 确保PyInstaller已安装
    if not ensure_pyinstaller_installed():
        return False
    
    # 准备构建目录
    project_root = prepare_build_directory()
    
    # 设置主脚本路径
    main_script = project_root / "datacollection" / "plc_data_viewer_gui.py"
    if not main_script.exists():
        print(f"❌ 找不到主脚本: {main_script}")
        return False
    
    print(f"🚀 开始构建可执行文件，主脚本: {main_script}")
    
    # 构建PyInstaller命令
    pyinstaller_cmd = [
        sys.executable,
        '-m', 'PyInstaller',
        '--name=PLC数据查看器',  # 可执行文件名称
        '--onefile',            # 生成单一可执行文件
        '--windowed',           # 窗口模式，不显示命令行
        '--add-data', f'{str(project_root / "resource")};resource',  # 添加资源文件
        '--hidden-import=pandas._libs.tslibs.timedeltas',  # 隐藏导入，解决pandas相关问题
        '--hidden-import=pandas._libs.tslibs.nattype',
        '--hidden-import=pandas._libs.skiplist',
        '--clean',              # 清理临时文件
        str(main_script)        # 主脚本路径
    ]
    
    try:
        # 执行PyInstaller命令
        print("📋 执行命令:", ' '.join(pyinstaller_cmd))
        process = subprocess.Popen(
            pyinstaller_cmd,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # 实时显示输出
        for line in process.stdout:
            print(line.strip())
        
        process.wait()
        
        if process.returncode != 0:
            print(f"❌ 构建失败，返回代码: {process.returncode}")
            return False
        
        # 复制资源文件
        copy_resources(project_root)
        
        # 检查可执行文件是否生成成功
        executable_path = project_root / "dist" / "PLC数据查看器.exe"
        if executable_path.exists():
            print(f"✅ 构建成功！可执行文件路径: {executable_path}")
            print("📝 构建完成，您可以在dist目录中找到可执行文件")
            print("💡 提示: 确保在运行可执行文件时，resource目录与可执行文件在同一目录下")
            return True
        else:
            print(f"❌ 找不到生成的可执行文件: {executable_path}")
            return False
            
    except Exception as e:
        print(f"❌ 构建过程中出现错误: {e}")
        return False

def create_batch_file():
    """创建运行批处理文件"""
    project_root = get_project_root()
    batch_path = project_root / "build_plc_viewer_exe.bat"
    
    batch_content = '''@echo off
chcp 65001 >nul

echo ====================================================
echo        朗诗乐府自由方舟 PLC数据查看器 打包工具
echo ====================================================

:: 检查Python环境
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未找到Python环境，请先安装Python
    pause
    exit /b 1
)

echo 正在使用Python环境: 
for /f "delims=" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo %PYTHON_VERSION%

:: 运行打包脚本
echo 开始打包PLC数据查看器...
python build_exe.py

:: 检查打包结果
if %errorlevel% neq 0 (
    echo 打包失败！
    pause
    exit /b 1
)

echo 打包成功！
echo 可执行文件位置: dist\PLC数据查看器.exe
echo 运行前请确保resource目录与可执行文件在同一目录下

echo.  
echo ====================================================
echo                     打包完成
echo ====================================================
pause
'''
    
    with open(batch_path, 'w', encoding='utf-8') as f:
        f.write(batch_content)
    
    print(f"✅ 创建打包批处理文件: {batch_path}")
    return batch_path

def main():
    """主函数"""
    print("====================================================")
    print("        朗诗乐府自由方舟 PLC数据查看器 打包工具")
    print("====================================================")
    
    # 创建批处理文件
    create_batch_file()
    
    # 开始构建
    success = build_executable()
    
    if success:
        print("🎉 PLC数据查看器打包完成！")
        return 0
    else:
        print("❌ PLC数据查看器打包失败！")
        return 1

if __name__ == "__main__":
    sys.exit(main())