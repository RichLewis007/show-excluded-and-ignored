# -*- mode: python ; coding: utf-8 -*-

import pathlib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_dir = pathlib.Path(__file__).resolve().parent
src_dir = project_dir / "src"
package_root = src_dir / "rfe"

icon_dir = package_root / "resources" / "icons"
feather_dir = icon_dir / "feather"
app_icon = icon_dir / "GhostFilesFinder.icns"
audio_dir = package_root / "resources" / "audio"
rules_file = project_dir / "tests" / "data" / "rclone-filter-list.txt"

pyside6_datas = collect_data_files("PySide6")

extra_datas = [
    (str(feather_dir), "rfe/resources/icons/feather"),
    (str(app_icon), "rfe/resources/icons"),
    (str(audio_dir), "rfe/resources/audio"),
    (str(rules_file), "tests/data"),
]

datas = pyside6_datas + extra_datas

hiddenimports = collect_submodules("PySide6")

block_cipher = None

a = Analysis(
    [str(package_root / "app.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher, allow_arch=False)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GhostFilesFinder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_icon),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GhostFilesFinder",
)
