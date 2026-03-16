# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Собираем всё содержимое для пакетов, как вы делали в консоли (--collect-all)
datas = []
binaries = []
hiddenimports = [
    'tiktoken_ext.openai_public',
    'tiktoken_ext',
    'litellm',
    'litellm.litellm_core_utils',
    'litellm.litellm_core_utils.default_encoding',
    'cachetools'
]

# Эквивалент --collect-all для ваших папок и litellm
for pkg in ['telegram-bot', 'updater', 'litellm']:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ['standalone_launcher.py'],
    pathex=['telegram-bot', 'updater'], # Пути, где лежат main.py и import_reestr.py
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'], # Наш хук для tiktoken
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide6', 'PyQt6', 'PySide2'],
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
    name='ChemTG_Bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True, # Оставляем консоль для отладки
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
