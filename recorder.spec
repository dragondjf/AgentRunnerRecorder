# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — AgentRunner Recorder
# onedir mode
# PREBUILT=1: 使用 make dist 的产物（dist/ 目录下已有编译好的 .pyd）

import os
import sys

_PREBUILT = os.environ.get('PREBUILT') == '1'
_ENTRY = 'dist/recorder_app.py' if _PREBUILT else 'recorder_app.py'
_PATHEX = ['dist'] if _PREBUILT else []

# 收集 pypandoc 打包所需的 pandoc 二进制文件
def _find_pypandoc_datas():
    """找到 pypandoc 的 pandoc 二进制目录，返回 PyInstaller datas 格式"""
    try:
        import pypandoc
        # pypandoc_binary: files/ 下包含 pandoc.exe (Windows) 或 pandoc (Linux/macOS)
        pkg_dir = os.path.dirname(pypandoc.__file__)
        files_dir = os.path.join(pkg_dir, 'files')
        if os.path.isdir(files_dir):
            return [(files_dir, 'pypandoc/files')]
    except Exception:
        pass
    return []

_DATAS_BASE = [
    ('dist/images', 'images'),
    ('dist/urecorder', 'urecorder'),
    ('dist/recorder', 'recorder'),
] if _PREBUILT else [
    ('images', 'images'),
    ('urecorder', 'urecorder'),
    ('recorder', 'recorder'),
]

_DATAS = _DATAS_BASE + _find_pypandoc_datas()

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
        'win32process',
        'pythoncom',
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        # Pillow (PIL) — 图标/截图处理
        'PIL',
        'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw',
        # 录制核心依赖
        'mss',
        'numpy',
        'cv2',
        # recorder 桌面端
        'rich',
        # Word 报告生成
        'docx',
        # pypandoc (Word/PDF/HTML 导出)
        'pypandoc',
        # Qwen VL 蓝图依赖
        'openai', 'tiktoken',
        'autogen_agentchat', 'autogen_agentchat.agents', 'autogen_agentchat.messages',
        'autogen_core',
        'autogen_ext', 'autogen_ext.models', 'autogen_ext.models.openai',
        'autogen_core.codec_tools',
        # postcase 导出依赖
        'pandas', 'xlsxwriter', 'PyPDF2', 'pdfplumber',
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
        # tkinter 子模块 (PyInstaller 不会自动检测)
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.ttk',
        # recorder.app 新增模块
        'recorder.theme',
        'recorder.ui_components',
        'recorder.hotkey',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'IPython',
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
