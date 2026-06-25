"""
base.py — 平台适配器抽象基类
==============================
定义跨平台接口，各平台（Windows/Linux/macOS）实现此接口。
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from PIL import Image

from ..element import UIElement


# ──────────────────────────────────────────────
# 跨平台窗口信息
# ──────────────────────────────────────────────

@dataclass
class WindowInfo:
    """跨平台窗口信息

    hwnd 为平台特定句柄（Windows: HWND, Linux: XID, macOS: AXUIElementRef）
    _ctrl 为适配器内部缓存，外部不应直接访问
    """
    name: str
    pid: int
    hwnd: int
    exe: str = ""
    _ctrl: Any = None  # 适配器内部缓存

    # 窗口边界（屏幕坐标）
    win_left: int = 0
    win_top: int = 0
    win_width: int = 0
    win_height: int = 0

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'pid': self.pid,
            'hwnd': self.hwnd,
            'exe': self.exe,
            'win_left': self.win_left,
            'win_top': self.win_top,
            'win_width': self.win_width,
            'win_height': self.win_height,
        }


# ──────────────────────────────────────────────
# 可点击控件类型（平台相关，由各适配器提供）
# ──────────────────────────────────────────────

CLICKABLE_TYPES_WINDOWS: set[str] = {
    'ButtonControl', 'ListItemControl', 'MenuItemControl',
    'CheckBoxControl', 'RadioButtonControl', 'ComboBoxControl',
    'HyperlinkControl', 'SplitButtonControl', 'TabItemControl',
    'TreeItemControl', 'DataItemControl', 'HeaderItemControl',
    'TextBoxControl', 'SpinnerControl', 'ScrollBarControl',
    'EditControl', 'DocumentControl', 'TabControl', 'PaneControl',
}

CLICKABLE_TYPES_LINUX: set[str] = {
    'push button', 'toggle button', 'check box', 'radio button',
    'combo box', 'list item', 'menu item', 'page tab', 'tab',
    'hyperlink', 'spin button', 'text', 'entry', 'table cell',
    'tree item', 'scroll bar', 'slider',
}

CLICKABLE_TYPES_DARWIN: set[str] = {
    'AXButton', 'AXCheckBox', 'AXRadioButton', 'AXComboBox',
    'AXMenuItem', 'AXMenuItemCheckbox', 'AXMenuItemRadio',
    'AXPopUpButton', 'AXDisclosureTriangle', 'AXSlider',
    'AXStepper', 'AXTabGroup', 'AXTextField', 'AXComboBox',
    'AXList', 'AXOutline', 'AXScrollBar', 'AXSplitter',
    'AXTable', 'AXCell', 'AXLink', 'AXMenuButton',
}


# ──────────────────────────────────────────────
# 平台适配器抽象基类
# ──────────────────────────────────────────────

class PlatformAdapter(ABC):
    """平台适配器抽象基类

    所有平台特定操作（窗口枚举、激活、截图、UI 控件遍历等）
    均通过此接口访问，上层代码无需关心底层实现。
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称: 'windows', 'linux', 'darwin'"""
        ...

    @property
    @abstractmethod
    def clickable_types(self) -> set[str]:
        """返回当前平台的可点击控件类型集合"""
        ...

    # ── 窗口操作 ──

    @abstractmethod
    def enumerate_windows(self) -> list[WindowInfo]:
        """枚举所有可见顶层窗口"""
        ...

    @abstractmethod
    def activate_window(self, win: WindowInfo) -> None:
        """激活窗口到前台并确保可见"""
        ...

    @abstractmethod
    def capture_window_screenshot(self, win: WindowInfo) -> Image.Image:
        """截取目标窗口的屏幕截图"""
        ...

    # ── 控件采集 ──

    @abstractmethod
    def get_element_at_point(
        self,
        screen_x: int,
        screen_y: int,
        win: WindowInfo,
    ) -> Optional[UIElement]:
        """从屏幕坐标获取控件元素"""
        ...

    @abstractmethod
    def collect_all_elements(self, win: WindowInfo) -> list[UIElement]:
        """遍历窗口子树，收集所有可点击控件"""
        ...

    # ── 输入模拟 ──

    @abstractmethod
    def wait_for_click(self, timeout: float = 30.0) -> Optional[tuple[int, int]]:
        """等待用户鼠标点击，返回屏幕坐标 (x, y) 或 None（超时）"""
        ...

    @abstractmethod
    def set_crosshair_cursor(self) -> None:
        """设置十字准星光标"""
        ...


# ──────────────────────────────────────────────
# 平台检测与适配器工厂
# ──────────────────────────────────────────────

def detect_platform() -> str:
    """检测当前操作系统"""
    p = sys.platform
    if p == "win32":
        return "windows"
    elif p == "linux":
        return "linux"
    elif p == "darwin":
        return "darwin"
    return p


def create_adapter() -> PlatformAdapter:
    """自动检测平台并创建对应的适配器实例"""
    platform = detect_platform()

    if platform == "windows":
        from .windows import WindowsAdapter
        return WindowsAdapter()
    elif platform == "linux":
        from .linux import LinuxAdapter
        return LinuxAdapter()
    elif platform == "darwin":
        from .darwin import DarwinAdapter
        return DarwinAdapter()
    else:
        raise RuntimeError(f"不支持的操作系统: {platform}")
