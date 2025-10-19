# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\yanggyan\\TRAE\\FreeArk\\datacollection\\plc_data_viewer_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\yanggyan\\TRAE\\FreeArk\\resource', 'resource')],
    hiddenimports=['pandas._libs.tslibs.timedeltas', 'pandas._libs.tslibs.nattype', 'pandas._libs.skiplist'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PLC数据查看器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
