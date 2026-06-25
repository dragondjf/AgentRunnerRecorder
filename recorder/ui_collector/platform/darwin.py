"""
darwin.py — macOS 平台适配器
==============================
基于 ApplicationServices (AX API) + PyObjC 实现 PlatformAdapter 接口。

依赖:
    pip install pyobjc-framework-Quartz pyobjc-framework-Accessibility
    pip install pyautogui pillow
"""

from __future__ import annotations

import time
import subprocess
from typing import Optional

import pyautogui
from PIL import Image

from .base import PlatformAdapter, WindowInfo, CLICKABLE_TYPES_DARWIN
from ..element import UIElement


class DarwinAdapter(PlatformAdapter):
    """macOS 平台适配器（基于 Accessibility API）"""

    def __init__(self):
        self._ax_available = False
        self._init_ax()

    def _init_ax(self):
        try:
            import Quartz
            import ApplicationServices
            self._Quartz = Quartz
            self._ApplicationServices = ApplicationServices
            self._ax_available = True
        except ImportError:
            self._ax_available = False

    @property
    def platform_name(self) -> str:
        return "darwin"

    @property
    def clickable_types(self) -> set[str]:
        return CLICKABLE_TYPES_DARWIN

    # ── 工具方法 ──

    def _cfstring_to_str(self, cfstring) -> str:
        """CFStringRef / NSString → str"""
        if cfstring is None:
            return ""
        try:
            return str(cfstring)
        except Exception:
            return ""

    def _get_ax_attribute(self, element, attr):
        """安全获取 AX 属性"""
        try:
            return self._ApplicationServices.AXUIElementCopyAttributeValue(
                element, attr, None
            )[1]
        except Exception:
            return None

    def _get_ax_attributes(self, element, attr):
        """安全获取 AX 属性数组"""
        try:
            return self._ApplicationServices.AXUIElementCopyAttributeValues(
                element, attr, 0, None
            )[1]
        except Exception:
            return None

    def _get_ax_position(self, element):
        """获取 AX 元素的位置 (x, y, w, h)"""
        pos = self._get_ax_attribute(element, "AXPosition")
        size = self._get_ax_attribute(element, "AXSize")
        if pos and size:
            return (
                int(pos.x), int(pos.y),
                int(size.width), int(size.height)
            )
        return None

    def _get_pid_from_ax(self, element) -> int:
        try:
            return self._ApplicationServices.AXUIElementGetPid(element)
        except Exception:
            return 0

    # ── 窗口枚举 ──

    def enumerate_windows(self) -> list[WindowInfo]:
        if not self._ax_available:
            return self._enumerate_fallback()

        windows: list[WindowInfo] = []
        try:
            # 获取所有运行中的应用
            ws = self._ApplicationServices.NSWorkspace.sharedWorkspace()
            apps = ws.runningApplications()
            for app in apps:
                try:
                    pid = app.processIdentifier()
                    app_ref = self._ApplicationServices.AXUIElementCreateApplication(pid)
                    if app_ref is None:
                        continue

                    # 获取窗口列表
                    windows_refs = self._get_ax_attributes(app_ref, "AXWindows")
                    if not windows_refs:
                        continue

                    for win_ref in windows_refs:
                        try:
                            title = self._cfstring_to_str(
                                self._get_ax_attribute(win_ref, "AXTitle"))
                            if not title:
                                continue
                            pos = self._get_ax_position(win_ref)
                            if pos is None:
                                continue
                            x, y, w, h = pos
                            bundle = self._cfstring_to_str(
                                self._get_ax_attribute(app_ref, "AXIdentifier"))
                            windows.append(WindowInfo(
                                name=title, pid=pid, hwnd=id(win_ref),
                                exe=bundle,
                                _ctrl=win_ref,
                                win_left=x, win_top=y,
                                win_width=w, win_height=h,
                            ))
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        return windows

    def _enumerate_fallback(self) -> list[WindowInfo]:
        """回退方案：通过 osascript 枚举窗口"""
        windows: list[WindowInfo] = []
        try:
            script = '''
            tell application "System Events"
                set appList to every process whose visible is true
                set output to ""
                repeat with proc in appList
                    set procName to name of proc
                    set winList to every window of proc
                    repeat with win in winList
                        set winTitle to title of win
                        if winTitle is not "" then
                            set output to output & procName & "|||" & winTitle & "|||" & ¬
                                (position of win) & "|||" & (size of win) & "\n"
                        end if
                    end repeat
                end repeat
                return output
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("|||")
                if len(parts) >= 4:
                    app_name, title, pos_str, size_str = parts[:4]
                    # 解析 "{x, y}" 和 "{w, h}"
                    try:
                        pos = pos_str.strip("{}").split(",")
                        size = size_str.strip("{}").split(",")
                        x, y = int(pos[0]), int(pos[1])
                        w, h = int(size[0]), int(size[1])
                        windows.append(WindowInfo(
                            name=title.strip(),
                            pid=0,
                            hwnd=hash(title + app_name),
                            exe=app_name.strip(),
                            win_left=x, win_top=y,
                            win_width=w, win_height=h,
                        ))
                    except Exception:
                        pass
        except Exception:
            pass
        return windows

    # ── 窗口激活 ──

    def activate_window(self, win: WindowInfo) -> None:
        try:
            # 使用 osascript 激活窗口
            script = '''
            tell application "System Events"
                set frontmost of every process whose name is "{}" to true
            end tell
            '''.format(win.exe.replace('"', ''))
            subprocess.run(["osascript", "-e", script],
                           capture_output=True, timeout=5)
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
        if not self._ax_available:
            return None

        try:
            element = self._ApplicationServices.AXUIElementCreateSystemWide()
            point = self._Quartz.CGPoint(screen_x, screen_y)
            result = self._ApplicationServices.AXUIElementCopyElementAtPosition(
                element, point.x, point.y, None
            )
            if result[0] != 0:
                return None
            hit = result[1]
            if hit is None:
                return None

            role = self._cfstring_to_str(
                self._get_ax_attribute(hit, "AXRole"))
            if role not in self.clickable_types:
                return None

            name = self._cfstring_to_str(
                self._get_ax_attribute(hit, "AXDescription"))
            if not name:
                name = self._cfstring_to_str(
                    self._get_ax_attribute(hit, "AXTitle"))
            if not name:
                name = self._cfstring_to_str(
                    self._get_ax_attribute(hit, "AXLabel"))
            if not name:
                name = role.capitalize()

            pos = self._get_ax_position(hit)
            if pos is None:
                return None
            x, y, w, h = pos
            if w < 16 or h < 10 or w * h < 200:
                return None

            return UIElement(
                name=name.strip() or "(空)",
                type=role.replace("AX", ""),
                bbox_left=max(0, x - win.win_left),
                bbox_top=max(0, y - win.win_top),
                bbox_right=min(win.win_width, x + w - win.win_left),
                bbox_bottom=min(win.win_height, y + h - win.win_top),
                width=w, height=h,
            )
        except Exception:
            return None

    # ── 控件采集（批量遍历） ──

    def collect_all_elements(self, win: WindowInfo) -> list[UIElement]:
        all_elems: list[UIElement] = []
        if not self._ax_available or win._ctrl is None:
            return all_elems

        def _collect(element, depth=0, max_depth=8):
            if depth > max_depth:
                return
            try:
                role = self._cfstring_to_str(
                    self._get_ax_attribute(element, "AXRole"))
                if role in self.clickable_types:
                    pos = self._get_ax_position(element)
                    if pos and pos[2] >= 16 and pos[3] >= 10:
                        x, y, w, h = pos
                        name = self._cfstring_to_str(
                            self._get_ax_attribute(element, "AXDescription"))
                        if not name:
                            name = self._cfstring_to_str(
                                self._get_ax_attribute(element, "AXTitle"))
                        if not name:
                            name = role.capitalize()

                        left = x - win.win_left
                        top = y - win.win_top
                        right = x + w - win.win_left
                        bottom = y + h - win.win_top
                        if left < win.win_width and top < win.win_height and right > 0 and bottom > 0:
                            all_elems.append(UIElement(
                                name=name.strip() or "(空)",
                                type=role.replace("AX", ""),
                                bbox_left=max(0, left),
                                bbox_top=max(0, top),
                                bbox_right=min(win.win_width, right),
                                bbox_bottom=min(win.win_height, bottom),
                                width=w, height=h,
                            ))
            except Exception:
                pass
            try:
                children = self._get_ax_attributes(element, "AXChildren")
                if children:
                    for child in children:
                        _collect(child, depth + 1, max_depth)
            except Exception:
                pass

        _collect(win._ctrl)
        return all_elems

    # ── 输入模拟 ──

    def wait_for_click(self, timeout: float = 30.0) -> Optional[tuple[int, int]]:
        self.set_crosshair_cursor()
        prev = False
        cx, cy = 0, 0
        start = time.time()
        while time.time() - start < timeout:
            try:
                import Quartz
                event = Quartz.CGEventCreate(None)
                loc = Quartz.CGEventGetLocation(event)
                state = Quartz.CGEventGetType(event)
                btn1 = state == Quartz.kCGEventLeftMouseDown
                if btn1 and not prev:
                    cx, cy = int(loc.x), int(loc.y)
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
            subprocess.run(
                ["osascript", "-e",
                 'tell app "System Events" to set cursor to crosshair'],
                capture_output=True, timeout=2
            )
        except Exception:
            pass
