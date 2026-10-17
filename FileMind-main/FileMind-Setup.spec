# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/xiao_hu/Desktop/file program1.2/build_out/filemind_installer.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/xiao_hu/Desktop/file program1.2/build_out/dist/FileMind', 'FileMind')],
    hiddenimports=[],
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
    name='FileMind-Setup',
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
    icon=['C:/Users/xiao_hu/Desktop/file program1.2/FileMind-main/tools/filemind.ico'],
)
