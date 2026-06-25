"""
windows.py — Windows 平台适配器
=================================
基于 uiautomation + win32api 实现 PlatformAdapter 接口。
"""

from __future__ import annotations

import time
import ctypes
from typing import Optional

import pyautogui
import win32api
import win32con
import win32gui
import win32process
from PIL import Image

import mss
import pythoncom
from uiautomation import GetRootControl, ControlFromPoint

from .base import PlatformAdapter, WindowInfo, CLICKABLE_TYPES_WINDOWS
from ..element import UIElement


class WindowsAdapter(PlatformAdapter):
    """Windows 平台适配器"""

    @property
    def platform_name(self) -> str:
        return "windows"

    @property
    def clickable_types(self) -> set[str]:
        return CLICKABLE_TYPES_WINDOWS

    # ── 窗口枚举 ──

    def enumerate_windows(self) -> list[WindowInfo]:
        root = GetRootControl()
        windows: list[WindowInfo] = []

        for child in root.GetChildren():
            try:
                name = child.Name.strip()
                pid = child.ProcessId
                visible = not child.IsOffscreen
                if not name or not visible:
                    continue

                hwnd = child.NativeWindowHandle
                exe_path = self._get_exe_path(pid)

                winfo = WindowInfo(
                    name=name, pid=pid, hwnd=hwnd,
                    exe=exe_path, _ctrl=child,
                )
                self._refresh_bounds(winfo)
                windows.append(winfo)
            except Exception:
                pass

        return windows

    def _get_exe_path(self, pid: int) -> str:
        try:
            h_process = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                False, pid
            )
            if h_process:
                path = win32process.GetModuleFileNameEx(h_process, 0)
                win32api.CloseHandle(h_process)
                return path
        except Exception:
            pass
        return ""

    def _refresh_bounds(self, win: WindowInfo) -> None:
        if win._ctrl is not None:
            try:
                rect = win._ctrl.BoundingRectangle
                if not rect.isempty():
                    win.win_left = int(rect.left)
                    win.win_top = int(rect.top)
                    win.win_width = int(rect.right) - win.win_left
                    win.win_height = int(rect.bottom) - win.win_top
                    return
            except Exception:
                pass
        try:
            r = win32gui.GetWindowRect(win.hwnd)
            win.win_left, win.win_top = r[0], r[1]
            win.win_width = r[2] - r[0]
            win.win_height = r[3] - r[1]
        except Exception:
            pass

    # ── 窗口激活 ──

    def activate_window(self, win: WindowInfo) -> None:
        hwnd = win.hwnd
        ctrl = win._ctrl

        try:
            if ctrl is not None:
                ctrl.SetFocus()
                time.sleep(0.3)
        except Exception:
            pass

        ctypes.windll.user32.ShowWindow(hwnd, 9)
        time.sleep(0.2)
        ctypes.windll.user32.ShowWindow(hwnd, 3)
        time.sleep(0.3)

        try:
            if ctrl is not None:
                ctrl.SetFocus()
                time.sleep(0.3)
        except Exception:
            pass

        self._refresh_bounds(win)

    # ── 窗口截图（极速版，mss ~10-30ms，无需激活窗口） ──

    def capture_window_screenshot(self, win: WindowInfo) -> Image.Image:
        """使用 mss 极速截图（10-30ms），无需激活窗口"""
        with mss.mss() as sct:
            monitor = {
                "left": win.win_left,
                "top": win.win_top,
                "width": win.win_width,
                "height": win.win_height,
            }
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.rgb)

    def refresh_bounds_silent(self, win: WindowInfo) -> None:
        """静默刷新窗口边界（不激活窗口，不闪烁）"""
        try:
            r = win32gui.GetWindowRect(win.hwnd)
            win.win_left, win.win_top = r[0], r[1]
            win.win_width = r[2] - r[0]
            win.win_height = r[3] - r[1]
        except Exception:
            pass

    # ── 控件采集（单点） ──

    def get_element_at_point(
        self,
        screen_x: int,
        screen_y: int,
        win: WindowInfo,
    ) -> Optional[UIElement]:
        try:
            ctrl = ControlFromPoint(screen_x, screen_y)
            if ctrl is None:
                return None
        except Exception:
            return None

        try:
            rect = ctrl.BoundingRectangle
            if rect.isempty():
                return None

            ct = ctrl.ControlTypeName
            if ct not in self.clickable_types:
                return None

            if not ctrl.IsEnabled or not ctrl.IsControlElement:
                return None

            w = rect.width()
            h = rect.height()
            if w < 16 or h < 10 or w * h < 200:
                return None

            return UIElement(
                name=ctrl.Name.strip() or ctrl.LocalizedControlType.capitalize() or "(空)",
                type=ct.replace("Control", ""),
                bbox_left=max(0, int(rect.left) - win.win_left),
                bbox_top=max(0, int(rect.top) - win.win_top),
                bbox_right=min(win.win_width, int(rect.right) - win.win_left),
                bbox_bottom=min(win.win_height, int(rect.bottom) - win.win_top),
                width=min(win.win_width, int(rect.right) - win.win_left) - max(0, int(rect.left) - win.win_left),
                height=min(win.win_height, int(rect.bottom) - win.win_top) - max(0, int(rect.top) - win.win_top),
            )
        except Exception:
            return None

    # ── 控件采集（批量遍历，性能优化版） ──

    def collect_all_elements(self, win: WindowInfo) -> list[UIElement]:
        """遍历窗口子树收集所有可点击控件

        性能优化：
          - 先过滤 IsOffscreen（避免不必要的 COM 调用）
          - 降低最大深度至 6
          - 跳过不可见节点子树
        """
        all_elems: list[UIElement] = []
        ctrl = win._ctrl
        if ctrl is None:
            return all_elems

        def _collect(node, depth=0, max_depth=6):
            if depth > max_depth:
                return
            try:
                # 先检查是否离屏（快速过滤，避免后续 COM 调用）
                if node.IsOffscreen:
                    return
                ct = node.ControlTypeName
                if ct in self.clickable_types and node.IsEnabled and node.IsControlElement:
                    r = node.BoundingRectangle
                    if not r.isempty():
                        w = r.width()
                        h = r.height()
                        if w >= 16 and h >= 10 and w * h >= 200 and w < win.win_width * 0.95:
                            left = int(r.left) - win.win_left
                            top = int(r.top) - win.win_top
                            right = int(r.right) - win.win_left
                            bottom = int(r.bottom) - win.win_top
                            if left < win.win_width and top < win.win_height and right > 0 and bottom > 0:
                                all_elems.append(UIElement(
                                    name=node.Name.strip() or node.LocalizedControlType.capitalize() or "(空)",
                                    type=ct.replace("Control", ""),
                                    bbox_left=max(0, left),
                                    bbox_top=max(0, top),
                                    bbox_right=min(win.win_width, right),
                                    bbox_bottom=min(win.win_height, bottom),
                                    width=min(win.win_width, right) - max(0, left),
                                    height=min(win.win_height, bottom) - max(0, top),
                                ))
            except Exception:
                pass
            try:
                for c in node.GetChildren():
                    _collect(c, depth + 1)
            except Exception:
                pass

        _collect(ctrl)
        return all_elems

    # ── 输入模拟 ──

    def wait_for_click(self, timeout: float = 30.0) -> Optional[tuple[int, int]]:
        self.set_crosshair_cursor()
        prev = False
        cx, cy = 0, 0
        start = time.time()
        while time.time() - start < timeout:
            state = ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000
            if state and not prev:
                cx, cy = pyautogui.position()
                time.sleep(0.2)
                break
            prev = state
            time.sleep(0.05)
        if cx == 0 and cy == 0:
            return None
        return cx, cy

    def set_crosshair_cursor(self) -> None:
        ctypes.windll.user32.SetCursor(
            ctypes.windll.user32.LoadCursorW(None, 32515))
