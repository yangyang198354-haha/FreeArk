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
        # 安装最新稳定版的PyInstaller
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pyinstaller==5.13.2'], 
                      check=True, capture_output=True, text=True)
        print("✅ PyInstaller 安装成功")
        
        # 安装主要依赖包，明确包含numpy和snap7
        critical_packages = ['numpy', 'pandas', 'openpyxl', 'matplotlib']
        for package in critical_packages:
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', package], 
                              check=True, capture_output=True, text=True)
                print(f"✅ {package} 安装/更新成功")
            except subprocess.CalledProcessError as e:
                print(f"⚠️  {package} 安装/更新失败，错误信息: {e.stderr}")
                print(f"   将继续尝试，确保系统已安装相应的编译工具")
        
        # 尝试安装snap7包（Windows环境）
        print("🔄 尝试安装python-snap7包...")
        try:
            # 对于Windows环境，尝试安装python-snap7包
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'python-snap7'], 
                          check=True, capture_output=True, text=True)
            print("✅ python-snap7包安装成功")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  python-snap7包安装失败: {e.stderr}")
            print("   尝试使用snap7包名称...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'snap7'], 
                              capture_output=True, text=True)
                print("✅ snap7包安装尝试完成")
            except Exception as e2:
                print(f"⚠️  snap7包安装也失败: {e2}")
                print("   注意: snap7包可能需要手动编译安装")
                print("   请参考以下步骤安装snap7:")
                print("   1. 下载snap7源码: http://snap7.sourceforge.net/")
                print("   2. 编译C库文件")
                print("   3. pip install python-snap7 或从源码安装python封装")
        
        # 尝试安装项目依赖（如果存在）
        requirements_file = get_project_root() / "requirements.txt"
        if requirements_file.exists():
            print("🔄 尝试安装项目requirements.txt中的依赖...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)], 
                              capture_output=True, text=True)
                print("✅ requirements.txt 依赖安装成功")
            except Exception:
                print("⚠️  requirements.txt 安装过程中有错误，但将继续打包")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装PyInstaller失败: {e}")
        print(e.stderr)
        return False
    except Exception as e:
        print(f"❌ 安装过程中出现其他错误: {e}")
        return False

def get_project_root():
    """获取项目根目录"""
    # 获取当前脚本的目录
    script_dir = Path(__file__).resolve().parent
    return script_dir

def prepare_build_directory():
    """准备构建目录，添加异常处理"""
    project_root = get_project_root()
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"
    
    # 清理旧的构建目录
    if build_dir.exists():
        print(f"🧹 清理旧的构建目录: {build_dir}")
        try:
            shutil.rmtree(build_dir)
        except Exception as e:
            print(f"⚠️  清理构建目录失败: {e}，将继续尝试")
    
    # 清理旧的发布目录，处理可能的权限错误
    if dist_dir.exists():
        print(f"🧹 尝试清理旧的发布目录: {dist_dir}")
        try:
            # 首先尝试逐个删除文件，特别是可执行文件
            for item in dist_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        print(f"✅ 删除文件: {item.name}")
                    elif item.is_dir():
                        shutil.rmtree(item)
                        print(f"✅ 删除目录: {item.name}")
                except Exception as e:
                    print(f"⚠️  删除 {item.name} 失败: {e}")
            
            # 如果目录还在，尝试删除整个目录
            if dist_dir.exists():
                shutil.rmtree(dist_dir)
        except Exception as e:
            print(f"⚠️  清理发布目录时出错: {e}，但将继续构建")
    
    # 创建新的目录，忽略已存在的情况
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
        # 确保目标目录存在
        resource_dst.mkdir(exist_ok=True, parents=True)
        # 使用更可靠的复制方法
        try:
            # 先删除目标目录，避免权限问题
            if resource_dst.exists():
                shutil.rmtree(resource_dst)
            shutil.copytree(resource_src, resource_dst)
            print(f"✅ 资源文件复制成功")
        except Exception as e:
            print(f"⚠️  复制资源文件时出错: {e}")
            # 尝试逐个文件复制
            try:
                for item in resource_src.iterdir():
                    target = resource_dst / item.name
                    if item.is_file():
                        shutil.copy2(item, target)
                        print(f"✅ 复制文件: {item.name}")
            except Exception as e2:
                print(f"❌ 逐个复制文件也失败: {e2}")
    else:
        print(f"⚠️  资源目录不存在: {resource_src}")
    
    # 不再将配置文件复制到根目录，只保留在resource目录中
    print("✅ 配置文件将只保留在resource目录中，不再复制到根目录")

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
    
    # 确定要使用的图标路径
    ico_icon_path = project_root / "resource" / "GUI icon.ico"
    icon_path = ico_icon_path if os.path.exists(ico_icon_path) else project_root / 'resource' / 'GUI icon.jpg'
    
    # 构建PyInstaller命令
    pyinstaller_cmd = [
        sys.executable,
        '-m', 'PyInstaller',
        '--name=朗诗乐府自由方舟小工具',  # 可执行文件名称
        '--icon=c:/Users/yanggyan/TRAE/FreeArk/resource/GUI icon.ico',  # 直接使用绝对路径设置图标
        '--onefile',            # 生成单一可执行文件
        '--windowed',           # 窗口模式，不显示命令行
        '--add-data', f'{str(project_root / "resource")};resource',  # 添加资源文件
        '--add-data', f'{str(project_root / "resource" / "log_config.json")};.',  # 单独添加日志配置文件到根目录
        '--collect-all', 'numpy',    # 收集所有numpy相关模块
        '--collect-all', 'pandas',   # 收集所有pandas相关模块
        '--collect-all', 'openpyxl', # 收集所有openpyxl相关模块
        '--collect-all', 'tkinter',  # 收集所有tkinter相关模块
        '--collect-all', 'matplotlib', # 收集所有matplotlib相关模块
        '--collect-all', 'snap7',      # 收集所有snap7相关模块
        '--hidden-import=numpy',     # 明确导入numpy
        '--hidden-import=numpy._globals',
        '--hidden-import=numpy.core._methods',
        '--hidden-import=numpy.lib.format',
        '--hidden-import=pandas._libs.tslibs.timedeltas',  # 隐藏导入，解决pandas相关问题
        '--hidden-import=pandas._libs.tslibs.nattype',
        '--hidden-import=pandas._libs.skiplist',
        '--hidden-import=pandas._libs.tslibs.parsing',
        '--hidden-import=pandas._libs.tslibs.conversion',
        '--hidden-import=pandas._libs.tslibs.offsets',
        '--hidden-import=pandas._libs.tslibs.tzconversion',
        '--hidden-import=pandas._libs.tslibs.timezones',
        '--hidden-import=openpyxl',
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=snap7',       # 明确导入snap7
        '--clean',              # 清理临时文件
        '--log-level=DEBUG',    # 设置更详细的日志级别
        '--noupx',              # 禁用UPX压缩，避免某些兼容性问题
        '--noconfirm',          # 自动覆盖现有文件
        '--copy-metadata=numpy', # 复制numpy元数据
        '--copy-metadata=pandas', # 复制pandas元数据
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
        executable_path = project_root / "dist" / "朗诗乐府自由方舟小工具.exe"
        if executable_path.exists():
            print(f"✅ 构建成功！可执行文件路径: {executable_path}")
            print("📝 构建完成，您可以在dist目录中找到可执行文件")
            print("💡 提示: 确保在运行可执行文件时，resource目录与可执行文件在同一目录下")
            return True
        else:
            # 尝试查找dist目录中的其他exe文件
            dist_dir = project_root / "dist"
            exe_files = list(dist_dir.glob("*.exe"))
            if exe_files:
                found_exe = exe_files[0]
                print(f"⚠️  未找到预期的可执行文件，但找到了: {found_exe}")
                print("📝 构建可能已完成，您可以在dist目录中找到可执行文件")
                return True
            else:
                print(f"❌ 找不到生成的可执行文件: {executable_path}")
                print("❌ dist目录中也未找到任何exe文件")
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
echo 可执行文件位置: dist/PLC数据查看器.exe
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