# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder
# onefile 模式：跨平台统一，生成单个可执行文件

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
    icon='images/app_icon.ico',
)
