# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# darat_dir = folder 'darat/'
darat_dir = os.path.dirname(os.path.abspath(SPEC))
# repo_dir = root repository (parent of 'darat/')
repo_dir = os.path.dirname(darat_dir)

datas = [
    (os.path.join(darat_dir, 'assets', 'plane.ply'), 'darat/assets'),
    (os.path.join(darat_dir, 'ui', 'styles', 'mdi_theme.qss'), 'darat/ui/styles'),
    (os.path.join(darat_dir, 'ui', 'styles', 'icons'), 'darat/ui/styles/icons'),
    (os.path.join(darat_dir, 'config', 'ground_config_override.json'), 'config'),
    (os.path.join(darat_dir, 'custom_ssl_methods'), 'custom_ssl_methods'),
    (os.path.join(darat_dir, 'README_CUSTOM_SSL.md'), '.'),
]

hiddenimports = [
    # Built-in SSL algorithms (dimuat dinamis via importlib di ssl_registry.py)
    'darat.localization.builtin_ssl',
    'darat.localization.builtin_ssl.bucher_misra',
    'darat.localization.builtin_ssl.chan_ho',
    'darat.localization.builtin_ssl.pivot',
    'darat.localization.builtin_ssl.consensus',
    'darat.localization.builtin_ssl.density_consensus',
    'darat.localization.builtin_ssl.rotating_multilat',

    # Submodul internal darat (Package namespace `darat.xxx`)
    'darat.api',
    'darat.api.config_api',
    'darat.api.network_setup',
    'darat.core',
    'darat.core.config',
    'darat.core.config_manager',
    'darat.core.file_transfer',
    'darat.io',
    'darat.io.json_receiver',
    'darat.io.serial_manager',
    'darat.localization',
    'darat.localization.process_json_tdoa',
    'darat.localization.ssl_registry',
    'darat.localization.calibration_engine',
    'darat.ui',
    'darat.ui.config_laptop',
    'darat.ui.config_raspi',
    'darat.ui.dashboard',
    'darat.ui.pages',
    'darat.ui.pages.command_page',
    'darat.ui.pages.config_page',
    'darat.ui.pages.process_page',
    'darat.ui.pages.visualize_page',
    'darat.ui.pages.calibration_page',
    'darat.ui.services',
    'darat.ui.services.rest_client',
    'darat.ui.services.serial_bridge',
    'darat.ui.widgets',
    'darat.ui.widgets.collapsible_section',
    'darat.ui.widgets.filter_config_panel',
    'darat.ui.widgets.log_panel',
    'darat.ui.widgets.mesh_loader',
    'darat.ui.widgets.radar_widget',
    'darat.ui.widgets.tactical_3d_widget',
    'darat.ui.widgets.session_list_widget',
    'darat.visualize_results',

    # Uvicorn, httptools, websockets
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'httptools',
    'websockets',

    # FastAPI, Starlette, Pydantic
    'fastapi',
    'pydantic',
    'pydantic_core',
    'starlette',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.responses',
    'starlette.routing',
    'starlette.applications',
    'starlette.datastructures',
    'starlette.exceptions',

    # HTTP Client & Serial
    'requests',
    'urllib3',
    'certifi',
    'idna',
    'charset_normalizer',
    'serial',
    'serial.tools.list_ports',

    # Scientific
    'scipy.spatial',
    'scipy.spatial.distance',
    'scipy.spatial.transform._rotation_groups',
    'scipy.optimize',
]

a = Analysis(
    [os.path.join(darat_dir, 'main.py')],
    pathex=[repo_dir, darat_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['venv', 'tests', 'docs', 'drone_recordings', 'udara'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MDI_Ground',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MDI_GUI',
)
