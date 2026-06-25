"""
window.py — 窗口信息获取与操作（跨平台）
=========================================
所有平台特定操作委托给 PlatformAdapter。
"""

from __future__ import annotations

from typing import Optional

from .platform import create_adapter, WindowInfo as _WindowInfo
from .platform.base import WindowInfo

# 全局适配器实例（懒加载）
_adapter = None


def _get_adapter():
    global _adapter
    if _adapter is None:
        _adapter = create_adapter()
    return _adapter


def enumerate_windows() -> list[WindowInfo]:
    """枚举所有可见顶层窗口"""
    return _get_adapter().enumerate_windows()


def find_window_by_title(title_substring: str) -> Optional[WindowInfo]:
    """按标题子串查找窗口"""
    for w in enumerate_windows():
        if title_substring.lower() in w.name.lower():
            return w
    return None


def find_window_by_pid(pid: int) -> Optional[WindowInfo]:
    """按 PID 查找窗口"""
    for w in enumerate_windows():
        if w.pid == pid:
            return w
    return None


def find_window_by_exe(exe_path: str) -> Optional[WindowInfo]:
    """按程序路径查找窗口（模糊匹配）"""
    target = exe_path.lower().replace("/", "\\")
    for w in enumerate_windows():
        if target in w.exe.lower():
            return w
    return None


def activate_window(win: WindowInfo) -> None:
    """激活窗口到前台并确保可见"""
    _get_adapter().activate_window(win)


def capture_window_screenshot(win: WindowInfo):
    """截取目标窗口的屏幕截图"""
    from PIL import Image
    return _get_adapter().capture_window_screenshot(win)


def get_platform_name() -> str:
    """获取当前平台名称: 'windows', 'linux', 'darwin'"""
    return _get_adapter().platform_name
