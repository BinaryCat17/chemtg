# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

# Функция для безопасного добавления папок
def get_datas():
    paths = [
        ('telegram-bot', 'telegram-bot'),
        ('updater', 'updater'),
    ]
    # Добавляем папки только если они реально существуют
    for folder in ['data', 'bin']:
        if os.path.exists(folder):
            paths.append((folder, folder))
        else:
            print(f"⚠️ ПРЕДУПРЕЖДЕНИЕ: Папка '{folder}' не найдена, она не будет включена в сборку.")
    return paths

datas = get_datas()
binaries = []
hiddenimports = [
    'tiktoken_ext.openai_public',
    'tiktoken_ext',
    'litellm',
    'litellm.litellm_core_utils',
    'litellm.litellm_core_utils.default_encoding',
    'cachetools',
    'sqlite3',
    'lxml',
    'lxml.etree',
]

# Автоматический сбор для библиотек
for pkg in ['litellm', 'aiogram', 'tavily', 'schedule', 'requests', 'urllib3']:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ['standalone_launcher.py'],
    pathex=['telegram-bot', 'updater'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'], 
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide6', 'PyQt6', 'PySide2', 'matplotlib', 'notebook', 'numpy', 'pandas', 'torch', 'tensorflow', 'scipy', 'PIL', 'tkinter'],
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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
