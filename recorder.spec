# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder
# onefile mode, cross-platform compatible

import os
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['recorder_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('images', 'images'),
    ],
    hiddenimports=[
        'recorder',
        'recorder.core',
        'recorder.screen_capture',
        'recorder.event_listener',
        'recorder.window_tracker',
        'recorder.manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'pandas', 'IPython',
        'jupyter', 'notebook', 'pytest', 'setuptools',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

# 跨平台图标选择：Windows 用 .ico，macOS/Linux 用 .png
if sys.platform == 'win32':
    _icon = 'images/app_icon.ico'
elif sys.platform == 'darwin':
    _icon = 'images/app_icon.png'
else:
    _icon = 'images/app_icon.png'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AgentRunnerRecorder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=_icon,
)
