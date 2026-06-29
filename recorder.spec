# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder
# onedir mode
# PREBUILT=1: 使用 make dist 的产物（dist/ 目录下已有编译好的 .pyd）

import os
import sys

_PREBUILT = os.environ.get('PREBUILT') == '1'
_ENTRY = 'dist/recorder_app.py' if _PREBUILT else 'recorder_app.py'
_PATHEX = ['dist'] if _PREBUILT else []
_DATAS = [
    ('dist/images', 'images'),
    ('dist/urecorder', 'urecorder'),
    ('dist/recorder', 'recorder'),
] if _PREBUILT else [
    ('images', 'images'),
    ('urecorder', 'urecorder'),
    ('recorder', 'recorder'),
]

block_cipher = None

a = Analysis(
    [_ENTRY],
    pathex=_PATHEX,
    binaries=[],
    datas=_DATAS,
    hiddenimports=[
        'recorder',
        'recorder.core',
        'recorder.screen_capture',
        'recorder.event_listener',
        'recorder.window_tracker',
        'recorder.manager',
        'recorder.report_generator',
        'recorder.urc_bridge',
        'urecorder.view.history_bp',
        'urecorder.view.qwen_vl_service',
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
        'psutil',
        'dotenv',
        'pydantic',
        'httpx',
        'yaml',
        'urecorder.flask_app',
        'requests',
        'requests_toolbelt',
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
    contents_directory='.',
)
