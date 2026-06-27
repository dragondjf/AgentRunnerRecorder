# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder
# onefile mode, cross-platform compatible

import os
import sys
from pathlib import Path

from PyInstaller.building.datastruct import Tree

block_cipher = None

# 收集 urecorder/ 全部文件，排除运行时数据和缓存
# SPECPATH = spec 文件所在目录（项目根目录）
_urc_toc = Tree(os.path.join(SPECPATH, 'urecorder'),
                prefix='urecorder',
                excludes=['filestorage', '__pycache__', 'data', 'docs', 'guiocr',
                          '*.bat', 'server.log'])

a = Analysis(
    ['recorder_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('images', 'images'),
    ] + _urc_toc,
    hiddenimports=[
        'recorder',
        'recorder.core',
        'recorder.screen_capture',
        'recorder.event_listener',
        'recorder.window_tracker',
        'recorder.manager',
        'recorder.report_generator',
        'recorder.urc_bridge',
        'recorder.history_server',
        'recorder.platform_utils',
        'recorder.click_icon_extractor',
        'recorder.ui_collector',
        'recorder.ui_collector.platform',
        'recorder.ui_collector.platform.windows',
        'recorder.ui_collector_bridge',
        'pyautogui',
        'uiautomation',
        'win32api',
        'win32con',
        'win32gui',
        'flask',
        'flask_cors',
        'loguru',
        'werkzeug',
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
