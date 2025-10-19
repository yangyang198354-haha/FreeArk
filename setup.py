from setuptools import setup, find_packages

setup(
    name="freeark-datacollection",
    version="1.0.0",
    description="FreeArk PLC??????",
    author="FreeArk Team",
    author_email="team@freeark.com",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.0.0",
        "openpyxl>=3.0.0",
        "python-snap7>=1.4.0",
        "paho-mqtt>=1.5.0",
        "argparse"
    ],
    python_requires=">=3.8",
    entry_points={
        'console_scripts': [
            'run-data-collection=datacollection.main_entry:main',
        ],
    },
)
