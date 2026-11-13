# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置，Windows 与 macOS 共用：
#   pyinstaller --noconfirm --clean EblanaDeskPet.spec
# Windows 产出 dist/EblanaDeskPet/EblanaDeskPet.exe；macOS 产出 dist/EblanaDeskPet.app
import sys

from PyInstaller.utils.hooks import collect_data_files

sys.path.insert(0, SPECPATH)
from version import VERSION  # noqa: E402

IS_MAC = sys.platform == "darwin"
ICON = "assets/official/app_icon.icns" if IS_MAC else "assets/official/app_icon.ico"

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets", "assets"),
        ("data/eblana_archive.txt", "data"),
    ]
    + collect_data_files("docx")   # Word 默认模板
    + collect_data_files("pptx"),  # PPT 默认模板
    hiddenimports=["docx", "pptx"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EblanaDeskPet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EblanaDeskPet",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="EblanaDeskPet.app",
        icon=ICON,
        bundle_identifier="io.github.victorgreatmarshal.eblana-deskpet",
        version=VERSION,
        info_plist={
            "CFBundleName": "死芒桌宠",
            "CFBundleDisplayName": "死芒桌宠",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSUIElement": True,             # 不在程序坞显示图标，通过菜单栏图标和右键菜单操作
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
