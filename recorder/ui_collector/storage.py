"""
storage.py — 采集数据持久化存储（会话级）
=========================================
数据模型：
  session.json
  ├── session: { program, pid, window_title, start_time, total_captures }
  ├── captures: [
  │     {
  │       capture_index, timestamp,
  │       mouse_x, mouse_y,
  │       screenshot_file,      # screenshots/screenshot_{index}.png
  │       new_elements_count,
  │       elements: [
  │         { id, name, type, bbox_left, bbox_top, bbox_right, bbox_bottom,
  │           width, height, crop_file }  # crops/{id}_{name}.png
  │       ]
  │     }
  │   ]
  └── flat_items: [ ... ]  # 所有控件的扁平列表（兼容旧版）
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Optional

from PIL import Image

from .element import UIElement


class CaptureRecord:
    """单次采集记录"""
    def __init__(
        self,
        capture_index: int = 0,
        timestamp: float = 0.0,
        mouse_x: int = 0,
        mouse_y: int = 0,
        screenshot_file: str = "",
        elements: list[UIElement] = None,
        new_elements_count: int = 0,
    ):
        self.capture_index = capture_index
        self.timestamp = timestamp or time.time()
        self.mouse_x = mouse_x
        self.mouse_y = mouse_y
        self.screenshot_file = screenshot_file
        self.elements = elements or []
        self.new_elements_count = new_elements_count

    def to_dict(self) -> dict:
        return {
            "capture_index": self.capture_index,
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "mouse_x": self.mouse_x,
            "mouse_y": self.mouse_y,
            "screenshot_file": self.screenshot_file,
            "new_elements_count": self.new_elements_count,
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, d: dict) -> CaptureRecord:
        ts_str = d.get("timestamp", "")
        ts = time.time()
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str).timestamp()
            except Exception:
                ts = time.time()
        return cls(
            capture_index=d.get("capture_index", 0),
            timestamp=ts,
            mouse_x=d.get("mouse_x", 0),
            mouse_y=d.get("mouse_y", 0),
            screenshot_file=d.get("screenshot_file", ""),
            elements=[UIElement.from_dict(item) for item in d.get("elements", [])],
            new_elements_count=d.get("new_elements_count", 0),
        )


class CollectionStorage:
    """采集数据持久化存储（会话级）

    目录结构:
      output_dir/
      ├── session.json          # 会话元数据 + 采集记录
      ├── screenshots/          # 每次采集的全屏截图
      └── crops/                # 控件裁剪图标
    """

    def __init__(
        self,
        output_dir: str = "",
        target_window: str = "",
        target_pid: int = 0,
        target_exe: str = "",
    ):
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = os.path.join(os.getcwd(), "ui_collector_output")

        self.target_window = target_window
        self.target_pid = target_pid
        self.target_exe = target_exe

        # 文件路径
        self.data_file = os.path.join(self.output_dir, "session.json")
        self.screenshots_dir = os.path.join(self.output_dir, "screenshots")
        self.crops_dir = os.path.join(self.output_dir, "crops")

        # 数据
        self.captures: list[CaptureRecord] = []
        self._flat_items: list[UIElement] = []
        self.next_id: int = 0
        self.start_time: float = time.time()

        # 创建目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.crops_dir, exist_ok=True)

        # 后台 I/O
        self._io_lock = threading.Lock()
        self._pending_save = False

    # ── 序列化 ──

    def to_dict(self) -> dict:
        return {
            "session": {
                "program": self.target_exe,
                "pid": self.target_pid,
                "window_title": self.target_window,
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "total_captures": len(self.captures),
                "total_elements": len(self._flat_items),
            },
            "captures": [c.to_dict() for c in self.captures],
            "flat_items": [e.to_dict() for e in self._flat_items],
        }

    @classmethod
    def from_dict(cls, d: dict, output_dir: str = "") -> CollectionStorage:
        session = d.get("session", {})
        storage = cls(
            output_dir=output_dir,
            target_window=session.get("window_title", ""),
            target_pid=session.get("pid", 0),
            target_exe=session.get("program", ""),
        )
        storage.captures = [CaptureRecord.from_dict(c) for c in d.get("captures", [])]
        storage._flat_items = [UIElement.from_dict(item) for item in d.get("flat_items", [])]
        storage.next_id = len(storage._flat_items)
        return storage

    # ── 加载/保存 ──

    def load(self) -> bool:
        """从磁盘加载历史数据，返回是否成功"""
        if not os.path.exists(self.data_file):
            return False
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            session = data.get("session", {})
            self.target_exe = session.get("program", self.target_exe)
            self.target_pid = session.get("pid", self.target_pid)
            self.target_window = session.get("window_title", self.target_window)
            self.captures = [CaptureRecord.from_dict(c) for c in data.get("captures", [])]
            self._flat_items = [UIElement.from_dict(item) for item in data.get("flat_items", [])]
            self.next_id = len(self._flat_items)
            return True
        except Exception:
            self.captures = []
            self._flat_items = []
            self.next_id = 0
            return False

    def save(self) -> bool:
        """保存到磁盘"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    # ── 采集记录管理 ──

    def add_capture(
        self,
        screenshot: Image.Image,
        elements: list[UIElement],
        mouse_x: int = 0,
        mouse_y: int = 0,
        save_screenshot: bool = True,
    ) -> CaptureRecord:
        """添加一次采集记录（截图和裁剪异步写入，不阻塞采集路径）

        Args:
            save_screenshot: False 时跳过保存全屏截图（仅保存控件裁剪），
                             避免与主程序 mss 截图重复。
        """
        capture_index = len(self.captures)

        # 内存中分配 id
        new_count = 0
        for elem in elements:
            elem.id = self.next_id
            self.next_id += 1
            self._flat_items.append(elem)
            new_count += 1

        screenshot_file = "screenshot_{:03d}.jpg".format(capture_index) if save_screenshot else ""

        record = CaptureRecord(
            capture_index=capture_index,
            timestamp=time.time(),
            mouse_x=mouse_x,
            mouse_y=mouse_y,
            screenshot_file=screenshot_file,
            elements=list(elements),
            new_elements_count=new_count,
        )
        self.captures.append(record)

        # 后台线程写入磁盘（不阻塞采集路径）
        self._schedule_deferred_io(screenshot, elements, screenshot_file, capture_index)

        return record

    def _schedule_deferred_io(
        self,
        screenshot: Image.Image,
        elements: list[UIElement],
        screenshot_file: str,
        capture_index: int,
    ):
        """在后台线程执行磁盘 I/O

        性能优化：
          - 截图存 JPEG (quality=85)，比 PNG 快 ~3x
          - 控件裁剪存 JPEG，比 PNG 快 ~3x
          - session.json 仅在数据变化时写入
        """
        screenshots_dir = self.screenshots_dir
        crops_dir = self.crops_dir
        data_file = self.data_file

        def _do_io():
            # 保存截图（JPEG，quality=85，~6ms vs PNG ~22ms）
            if screenshot_file:
                path = os.path.join(screenshots_dir, screenshot_file)
                try:
                    screenshot.save(path, "JPEG", quality=85)
                except Exception:
                    try:
                        screenshot.convert("RGB").save(path, "JPEG", quality=85)
                    except Exception:
                        pass

            # 保存控件裁剪（JPEG，quality=90）
            for elem in elements:
                try:
                    l, t, r, b = elem.bbox_left, elem.bbox_top, elem.bbox_right, elem.bbox_bottom
                    if l >= r or t >= b:
                        continue
                    sw, sh = screenshot.size
                    l, t = max(0, l), max(0, t)
                    r, b = min(sw, r), min(sh, b)
                    if r - l < 2 or b - t < 2:
                        continue
                    crop = screenshot.crop((l, t, r, b))
                    filename = "{}_{}.jpg".format(elem.id, elem.safe_name)
                    crop.convert("RGB").save(os.path.join(crops_dir, filename), "JPEG", quality=90)
                except Exception:
                    pass

            # 保存 session.json
            with self._io_lock:
                try:
                    with open(data_file, "w", encoding="utf-8") as f:
                        json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                self._pending_save = False

        t = threading.Thread(target=_do_io, daemon=True)
        t.start()

    def get_latest_capture(self) -> Optional[CaptureRecord]:
        if self.captures:
            return self.captures[-1]
        return None

    # ── 元素管理 ──

    def add(self, elem: UIElement) -> int:
        """添加元素（兼容旧接口），返回 id（-1 表示重复）"""
        from .element import is_duplicate
        if is_duplicate(elem, self._flat_items):
            return -1
        elem.id = self.next_id
        self.next_id += 1
        self._flat_items.append(elem)
        return elem.id

    def remove(self, elem_id: int) -> bool:
        for i, e in enumerate(self._flat_items):
            if e.id == elem_id:
                self._flat_items.pop(i)
                return True
        return False

    def remove_multi(self, elem_ids: list[int]) -> int:
        id_set = set(elem_ids)
        before = len(self._flat_items)
        self._flat_items = [e for e in self._flat_items if e.id not in id_set]
        return before - len(self._flat_items)

    def clear(self) -> None:
        self.captures.clear()
        self._flat_items.clear()
        self.next_id = 0

    def get_by_id(self, elem_id: int) -> Optional[UIElement]:
        for e in self._flat_items:
            if e.id == elem_id:
                return e
        return None

    def get_all(self) -> list[UIElement]:
        return list(self._flat_items)

    def get_count(self) -> int:
        return len(self._flat_items)

    # ── 截图管理 ──

    def save_crop(self, elem: UIElement, screenshot: Image.Image) -> Optional[str]:
        """保存控件截图（JPEG），返回文件路径"""
        try:
            l, t, r, b = elem.bbox_left, elem.bbox_top, elem.bbox_right, elem.bbox_bottom
            if l >= r or t >= b:
                return None
            sw, sh = screenshot.size
            l, t = max(0, l), max(0, t)
            r, b = min(sw, r), min(sh, b)
            if r - l < 2 or b - t < 2:
                return None
            crop = screenshot.crop((l, t, r, b))
            filename = "{}_{}.jpg".format(elem.id, elem.safe_name)
            path = os.path.join(self.crops_dir, filename)
            crop.convert("RGB").save(path, "JPEG", quality=90)
            return path
        except Exception:
            return None

    def get_crop_path(self, elem: UIElement) -> str:
        return os.path.join(self.crops_dir, "{}_{}.jpg".format(elem.id, elem.safe_name))

    def get_screenshot_path(self, capture_index: int) -> str:
        return os.path.join(self.screenshots_dir, "screenshot_{:03d}.jpg".format(capture_index))

    def clear_crops(self) -> None:
        for d in [self.crops_dir, self.screenshots_dir]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    try:
                        os.remove(os.path.join(d, f))
                    except Exception:
                        pass

    # ── 导出 ──

    def export(self, export_dir: str = "") -> str:
        if not export_dir:
            export_dir = self.output_dir
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(export_dir, "export_{}.json".format(ts))
        data = self.to_dict()
        data["export_time"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
