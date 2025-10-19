from setuptools import setup, find_packages

# 读取requirements.txt内容
with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

# 过滤掉注释和空行
requirements = [req for req in requirements if req.strip() and not req.strip().startswith("#")]

setup(
    name="freeark-datacollection",
    version="1.0.0",
    description="FreeArk PLC数据收集系统",
    author="FreeArk Team",
    author_email="team@freeark.com",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.8",
    entry_points={
        'console_scripts': [
            'run-data-collection=datacollection.main_entry:main',
        ],
    },
)
