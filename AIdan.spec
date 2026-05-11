# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['AIdan_TodoEnUno.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('dashboard_multi_theme.html', '.'),
        ('static', 'static'),
        ('tools/dashboard_theme_editor.html', '.'),
        ('tools/what_if_simulator.html', '.'),
    ],
    hiddenimports=['numpy', 'MetaTrader5'],
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
    name='AIdan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
