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
        ('tools/meta_optimization.html', '.'),
        ('tools/position_manager.html', '.'),
        # v3.35.0 — ML confidence predictor: modelos dedicados + metadata
        ('config/confidence_model_news.joblib', 'config'),
        ('config/confidence_model_m15_structure.joblib', 'config'),
        ('config/confidence_predictor_meta.json', 'config'),
    ],
    hiddenimports=['numpy', 'MetaTrader5', 'sklearn', 'sklearn.ensemble', 'sklearn.linear_model',
                   'sklearn.preprocessing', 'sklearn.tree', 'sklearn.utils', 'joblib', 'scipy.sparse.csgraph._validation'],
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
    icon='static/aidan_icon.ico',
)
