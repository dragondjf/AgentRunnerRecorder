# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder

import os
import sys
from pathlib import Path

a = Analysis(
    ['recorder_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 图标资源目录（整个文件夹打包进去）
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
)

# 去除不需要的模块，减小体积
pyz = PYZ(a.pure)

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
    console=False,            # 不弹出黑色命令行窗口
    icon='images/app_icon.ico',  # 窗口图标
)
