"""
linux.py — Linux 平台适配器
=============================
基于 pyatspi / AT-SPI 实现 PlatformAdapter 接口。

依赖:
    pip install pyatspi  (或 apt install python3-pyatspi)
    pip install pyautogui pillow
"""

from __future__ import annotations

import time
import subprocess
from typing import Optional

import pyautogui
from PIL import Image

from .base import PlatformAdapter, WindowInfo, CLICKABLE_TYPES_LINUX
from ..element import UIElement


class LinuxAdapter(PlatformAdapter):
    """Linux 平台适配器（基于 AT-SPI）"""

    def __init__(self):
        self._atspi_available = False
        self._init_atspi()

    def _init_atspi(self):
        try:
            import pyatspi
            self._pyatspi = pyatspi
            self._registry = pyatspi.Registry
            self._atspi_available = True
        except ImportError:
            self._atspi_available = False

    @property
    def platform_name(self) -> str:
        return "linux"

    @property
    def clickable_types(self) -> set[str]:
        return CLICKABLE_TYPES_LINUX

    # ── 窗口枚举 ──

    def enumerate_windows(self) -> list[WindowInfo]:
        if not self._atspi_available:
            return self._enumerate_fallback()

        windows: list[WindowInfo] = []
        try:
            desktop = self._pyatspi.Registry.getDesktop(0)
            for app in desktop:
                try:
                    name = app.name.strip()
                    pid = self._get_pid_from_app(app)
                    if not name:
                        continue
                    # 获取窗口边界
                    w, h, x, y = self._get_app_extents(app)
                    windows.append(WindowInfo(
                        name=name, pid=pid, hwnd=id(app),
                        exe=self._get_exe_from_pid(pid),
                        _ctrl=app,
                        win_left=x, win_top=y,
                        win_width=w, win_height=h,
                    ))
                except Exception:
                    pass
        except Exception:
            pass

        return windows

    def _enumerate_fallback(self) -> list[WindowInfo]:
        """回退方案：通过 xdotool / wmctrl 枚举窗口"""
        windows: list[WindowInfo] = []
        try:
            # 尝试 wmctrl
            result = subprocess.run(
                ["wmctrl", "-l", "-p"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split("\n"):
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    hwnd_hex, desktop, pid_str, title = parts
                    hwnd = int(hwnd_hex, 16)
                    pid = int(pid_str)
                    if title.strip():
                        windows.append(WindowInfo(
                            name=title.strip(), pid=pid, hwnd=hwnd,
                            exe=self._get_exe_from_pid(pid),
                        ))
        except Exception:
            pass
        return windows

    def _get_pid_from_app(self, app) -> int:
        try:
            return app.get_process_id()
        except Exception:
            return 0

    def _get_app_extents(self, app):
        """获取应用窗口的边界"""
        try:
            # 尝试从 AT-SPI 获取
            for comp in self._iter_component(app):
                try:
                    extents = comp.getExtents(0)  # 0 = no children
                    if extents:
                        return extents.width, extents.height, extents.x, extents.y
                except Exception:
                    pass
        except Exception:
            pass
        return 800, 600, 0, 0

    def _iter_component(self, obj, depth=0, max_depth=4):
        if depth > max_depth:
            return
        if obj and obj.get_role_name() in ("frame", "window", "dialog", "application"):
            yield obj
        try:
            for i in range(obj.getChildCount()):
                child = obj[i]
                yield from self._iter_component(child, depth + 1, max_depth)
        except Exception:
            pass

    def _get_exe_from_pid(self, pid: int) -> str:
        try:
            import os
            return os.popen(f"readlink -f /proc/{pid}/exe").read().strip()
        except Exception:
            return ""

    # ── 窗口激活 ──

    def activate_window(self, win: WindowInfo) -> None:
        try:
            subprocess.run(
                ["wmctrl", "-i", "-a", hex(win.hwnd)],
                capture_output=True, timeout=3
            )
        except Exception:
            pass
        time.sleep(0.3)

    # ── 窗口截图 ──

    def capture_window_screenshot(self, win: WindowInfo) -> Image.Image:
        return pyautogui.screenshot(
            region=(win.win_left, win.win_top, win.win_width, win.win_height)
        )

    # ── 控件采集（单点） ──

    def get_element_at_point(
        self,
        screen_x: int,
        screen_y: int,
        win: WindowInfo,
    ) -> Optional[UIElement]:
        if not self._atspi_available:
            return None

        try:
            obj = self._pyatspi.Registry.getAccessibleAtPoint(screen_x, screen_y)
            if obj is None:
                return None
            role = obj.get_role_name()
            if role not in self.clickable_types:
                return None
            try:
                extents = obj.getExtents(0)
                if extents is None:
                    return None
            except Exception:
                return None

            return UIElement(
                name=obj.name.strip() or role.capitalize() or "(空)",
                type=role,
                bbox_left=max(0, extents.x - win.win_left),
                bbox_top=max(0, extents.y - win.win_top),
                bbox_right=min(win.win_width, extents.x + extents.width - win.win_left),
                bbox_bottom=min(win.win_height, extents.y + extents.height - win.win_top),
                width=extents.width,
                height=extents.height,
            )
        except Exception:
            return None

    # ── 控件采集（批量遍历） ──

    def collect_all_elements(self, win: WindowInfo) -> list[UIElement]:
        all_elems: list[UIElement] = []
        if not self._atspi_available or win._ctrl is None:
            return all_elems

        def _collect(obj, depth=0, max_depth=8):
            if depth > max_depth:
                return
            try:
                role = obj.get_role_name()
                if role in self.clickable_types:
                    try:
                        extents = obj.getExtents(0)
                        if extents and extents.width >= 16 and extents.height >= 10:
                            left = extents.x - win.win_left
                            top = extents.y - win.win_top
                            right = extents.x + extents.width - win.win_left
                            bottom = extents.y + extents.height - win.win_top
                            if left < win.win_width and top < win.win_height and right > 0 and bottom > 0:
                                all_elems.append(UIElement(
                                    name=obj.name.strip() or role.capitalize() or "(空)",
                                    type=role,
                                    bbox_left=max(0, left),
                                    bbox_top=max(0, top),
                                    bbox_right=min(win.win_width, right),
                                    bbox_bottom=min(win.win_height, bottom),
                                    width=extents.width,
                                    height=extents.height,
                                ))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                for i in range(obj.getChildCount()):
                    _collect(obj[i], depth + 1)
            except Exception:
                pass

        _collect(win._ctrl)
        return all_elems

    # ── 输入模拟 ──

    def wait_for_click(self, timeout: float = 30.0) -> Optional[tuple[int, int]]:
        self.set_crosshair_cursor()
        import Xlib.display
        display = Xlib.display.Display()
        root = display.screen().root

        prev = False
        cx, cy = 0, 0
        start = time.time()
        while time.time() - start < timeout:
            try:
                data = root.query_pointer()._data
                state = data["mask"]
                btn1 = bool(state & 0x100)  # Button1Mask
                if btn1 and not prev:
                    cx, cy = data["root_x"], data["root_y"]
                    time.sleep(0.2)
                    break
                prev = btn1
            except Exception:
                pass
            time.sleep(0.05)

        if cx == 0 and cy == 0:
            return None
        return cx, cy

    def set_crosshair_cursor(self) -> None:
        try:
            subprocess.run(["xsetroot", "-cursor_name", "crosshair"],
                           capture_output=True, timeout=2)
        except Exception:
            pass
