"""
collector.py — UI 控件采集器引擎（跨平台）
============================================
基于 PlatformAdapter 实现，支持 Windows/Linux/macOS。
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from PIL import Image

from .platform import create_adapter, WindowInfo
from .platform.base import PlatformAdapter
from .element import (
    UIElement,
    deduplicate_elements,
    sort_elements_top_left,
)
from .storage import CollectionStorage


class UICollector:
    """UI 控件采集器引擎（跨平台）

    职责:
    - 窗口管理（激活、截图）
    - 单点采集（鼠标点击位置）
    - 批量采集（遍历子树）
    - 增量去重
    - 数据持久化

    用法:
        from ui_collector import UICollector, enumerate_windows, activate_window

        windows = enumerate_windows()
        win = windows[0]
        activate_window(win)

        collector = UICollector(win, output_dir="./my_data")

        # 单点采集
        elem = collector.capture_at_point(500, 300)

        # 批量采集
        new_elems = collector.batch_capture()

        # 访问结果
        all_items = collector.get_all()
    """

    def __init__(
        self,
        win: WindowInfo,
        output_dir: str = "",
        on_status: Callable[[str], None] | None = None,
        adapter: PlatformAdapter | None = None,
    ):
        """
        Args:
            win: 目标窗口信息
            output_dir: 输出目录（默认 ./ui_collector_output）
            on_status: 状态回调函数，用于 UI 层显示状态信息
            adapter: 平台适配器（自动检测，通常无需传入）
        """
        self.win = win
        self.on_status = on_status
        self.adapter = adapter or create_adapter()

        # 存储
        self.storage = CollectionStorage(
            output_dir=output_dir,
            target_window=win.name,
            target_pid=win.pid,
            target_exe=win.exe,
        )

        # 当前窗口截图
        self.screenshot: Optional[Image.Image] = None

        # 加载历史数据
        loaded = self.storage.load()
        if loaded:
            self._status("已加载历史数据: {} 个控件".format(self.storage.get_count()))

    # ── 平台信息 ──

    @property
    def platform_name(self) -> str:
        """当前平台名称"""
        return self.adapter.platform_name

    # ── 状态回调 ──

    def _status(self, msg: str) -> None:
        if self.on_status:
            self.on_status(msg)

    # ── 窗口操作 ──

    def activate(self) -> None:
        """激活目标窗口"""
        self.adapter.activate_window(self.win)

    def refresh_screenshot(self) -> Image.Image:
        """刷新窗口截图"""
        self.activate()
        time.sleep(0.3)
        self.screenshot = self.adapter.capture_window_screenshot(self.win)
        return self.screenshot

    # ── 单点采集 ──

    def capture_at_point(self, screen_x: int, screen_y: int) -> Optional[UIElement]:
        """从屏幕坐标采集一个控件

        Args:
            screen_x, screen_y: 屏幕坐标

        Returns:
            新增的 UIElement，重复或无效则返回 None
        """
        # 检查是否在窗口内
        if (screen_x < self.win.win_left or
                screen_x > self.win.win_left + self.win.win_width or
                screen_y < self.win.win_top or
                screen_y > self.win.win_top + self.win.win_height):
            self._status("点击位置不在目标窗口内")
            return None

        # 获取控件
        elem = self.adapter.get_element_at_point(screen_x, screen_y, self.win)
        if elem is None:
            self._status("未识别到可点击控件")
            return None

        # 去重并添加
        elem_id = self.storage.add(elem)
        if elem_id < 0:
            self._status("重复元素，已跳过: {} \"{}\"".format(elem.type, elem.name[:20]))
            return None

        # 保存截图
        if self.screenshot is not None:
            self.storage.save_crop(elem, self.screenshot)

        # 持久化
        self.storage.save()
        self._status("已采集: #{} {} \"{}\"".format(elem.id, elem.type, elem.name[:20]))
        return elem

    # ── 完整采集（截图+控件+记录） ──

    def capture_full(
        self,
        mouse_x: int = 0,
        mouse_y: int = 0,
        save_screenshot: bool = True,
    ) -> tuple[Image.Image, list[UIElement], int]:
        """执行一次完整采集：截图 → 识别控件 → 去重 → 存储

        性能优化（无感采集）：
          - 不激活窗口（无闪烁）
          - mss 极速截图（10-30ms）
          - 智能跳过：点击已知控件时跳过全量遍历（节省 ~30ms）
          - 无 time.sleep

        Args:
            save_screenshot: False 时跳过保存全屏截图（避免与主程序 mss 截图重复）

        Returns:
            (screenshot, all_candidates, new_count)
        """
        # 静默刷新窗口边界（不激活窗口，不闪烁）
        if hasattr(self.adapter, 'refresh_bounds_silent'):
            self.adapter.refresh_bounds_silent(self.win)

        # 智能跳过：先检查点击位置是否命中已知控件
        # 如果命中，跳过全量遍历（节省 ~30ms）
        if mouse_x > 0 or mouse_y > 0:
            hit = self.adapter.get_element_at_point(mouse_x, mouse_y, self.win)
            if hit is not None:
                from .element import is_duplicate
                if is_duplicate(hit, self.get_all()):
                    # 点击在已知控件上 → 只截图不遍历
                    screenshot = self.adapter.capture_window_screenshot(self.win)
                    self._status("⏭️ 已知控件，跳过遍历 (共 {} 个)".format(
                        self.storage.get_count()))
                    return screenshot, [], 0

        screenshot = self.adapter.capture_window_screenshot(self.win)
        candidates = self.adapter.collect_all_elements(self.win)

        # 去重
        from .element import deduplicate_elements, sort_elements_top_left
        new_elems = deduplicate_elements(candidates, self.get_all())
        new_elems = sort_elements_top_left(new_elems)

        # 使用 add_capture 保存完整记录
        if new_elems:
            self.storage.add_capture(screenshot, new_elems, mouse_x, mouse_y, save_screenshot=save_screenshot)

        self._status("采集完成: 新增 {} 个控件 (共 {} 个)".format(
            len(new_elems), self.storage.get_count()))
        return screenshot, candidates, len(new_elems)

    # ── 批量采集（旧接口，兼容） ──

    def batch_capture(self) -> list[UIElement]:
        """批量采集目标窗口的所有控件

        Returns:
            新增的 UIElement 列表
        """
        self._status("正在批量采集所有控件...")

        # 刷新截图
        self.refresh_screenshot()

        # 遍历子树（平台相关）
        candidates = self.adapter.collect_all_elements(self.win)

        # 去重（内部 + 历史）— 平台无关
        deduped = deduplicate_elements(candidates, self.storage.get_all())

        if not deduped:
            self._status("没有新的控件可采集（全部已存在）")
            return []

        # 按左上到右下排序
        deduped = sort_elements_top_left(deduped)

        # 添加并保存截图
        added: list[UIElement] = []
        for elem in deduped:
            elem_id = self.storage.add(elem)
            if elem_id >= 0:
                if self.screenshot is not None:
                    self.storage.save_crop(elem, self.screenshot)
                added.append(elem)

        # 持久化
        self.storage.save()
        self._status("批量采集完成: 新增 {} 个控件 (共 {} 个)".format(
            len(added), self.storage.get_count()))
        return added

    # ── 数据访问 ──

    def get_all(self) -> list[UIElement]:
        return self.storage.get_all()

    def get_count(self) -> int:
        return self.storage.get_count()

    def get_storage(self) -> CollectionStorage:
        return self.storage

    # ── 数据管理 ──

    def remove_by_id(self, elem_id: int) -> bool:
        result = self.storage.remove(elem_id)
        if result:
            self.storage.save()
        return result

    def remove_by_ids(self, elem_ids: list[int]) -> int:
        count = self.storage.remove_multi(elem_ids)
        if count > 0:
            self.storage.save()
        return count

    def clear_all(self) -> None:
        self.storage.clear()
        self.storage.clear_crops()
        self.storage.save()
        self._status("已清空全部")

    def export_json(self, export_dir: str = "") -> str:
        path = self.storage.export(export_dir)
        self._status("已导出: {}".format(path))
        return path

    # ── 等待点击（委托给适配器） ──

    def wait_for_click(self, timeout: float = 30.0) -> Optional[tuple[int, int]]:
        """等待用户鼠标点击，返回屏幕坐标 (x, y) 或 None（超时）"""
        return self.adapter.wait_for_click(timeout)
