# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['darat/main.py'],
    pathex=[],
    binaries=[],
    datas=[('darat/ui/styles', 'darat/ui/styles'), ('darat/assets/plane.ply', 'darat/assets')],
    hiddenimports=['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'pydantic', 'starlette', 'anyio', 'h11', 'darat.localization.builtin_ssl.bucher_misra', 'darat.localization.builtin_ssl.chan_ho', 'darat.localization.builtin_ssl.pivot', 'darat.localization.builtin_ssl.consensus', 'darat.localization.builtin_ssl.density_consensus'],
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
    name='MDI_Ground',
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
    uac_admin=True,
)
