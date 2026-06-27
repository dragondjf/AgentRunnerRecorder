# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder
# onedir mode，输出结构: dist/AgentRunnerRecorder/
#   AgentRunnerRecorder.exe      ← 启动器
#   _internal/                    ← 依赖 + Cython .pyd
#   urecorder/                    ← Flask 应用 + 静态文件
#   images/                       ← 图标资源

import os
import sys
from pathlib import Path

from PyInstaller.building.datastruct import Tree

block_cipher = None

# 收集 urecorder/ 全部文件，排除运行时数据和缓存
# SPECPATH = spec 文件所在目录（项目根目录）
_urc_tree = Tree(os.path.join(SPECPATH, 'urecorder'),
                 prefix='urecorder',
                 excludes=['filestorage', '__pycache__', 'data', 'docs', 'guiocr',
                           '*.bat', 'server.log'])
# Tree 返回 (相对dest, 绝对src, 'DATA')，datas 需要 (绝对src, 相对dest)
_urc_datas = [(entry[1], entry[0]) for entry in _urc_tree]

a = Analysis(
    ['recorder_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('images', 'images'),
    ] + _urc_datas,
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

# 跨平台图标选择
if sys.platform == 'win32':
    _icon = 'images/app_icon.ico'
elif sys.platform == 'darwin':
    _icon = 'images/app_icon.png'
else:
    _icon = 'images/app_icon.png'

# ── onedir 模式：bootloader + COLLECT ──
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AgentRunnerRecorder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AgentRunnerRecorder',
)
