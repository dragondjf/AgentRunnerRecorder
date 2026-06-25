"""
ui_collector_bridge.py — UICollector <-> RecordingSession 桥接层
=================================================================
职责:
  1. 管理 UICollector 实例的生命周期
  2. 接收 RecordingSession 的 mss 截图帧（numpy array），复用截图
  3. 接收 EventListener 的鼠标点击事件，触发控件采集
  4. 输出统一到 inputs/ui_controls/ 目录
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from .ui_collector import WindowInfo


class UICollectorBridge:
    """UICollector 桥接层，与 RecordingSession 协同工作"""

    def __init__(self, win: WindowInfo, output_dir: Path):
        from .ui_collector import UICollector

        self.win = win
        self.output_dir = output_dir / "inputs" / "ui_controls"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.collector = UICollector(
            win=win,
            output_dir=str(self.output_dir),
        )

        # 加载历史数据（如果存在）
        loaded = self.collector.get_storage().load()
        if loaded:
            print(f"  [UICollect] 已加载历史数据: {self.collector.get_count()} 个控件")

        self._capture_count = 0
        self._skip_count = 0
        self._traverse_count = 0
        self._bounds_refresh_interval = 5
        self._start_time = time.monotonic()

    # ── 截图复用 ──────────────────────────────────────────────

    def on_screenshot(self, np_array: np.ndarray) -> None:
        """接收 RecordingSession 的截图帧（numpy BGR array）

        将 numpy 数组转为 PIL.Image 并设置到 collector.screenshot，
        这样 capture_full() 就不用重新截图了。

        Args:
            np_array: BGR 格式的 numpy 数组 (H, W, 3)
        """
        from PIL import Image
        import numpy as np

        # BGR → RGB
        rgb = np_array[:, :, ::-1].copy()
        self.collector.screenshot = Image.fromarray(rgb)

    # ── 鼠标点击 ──────────────────────────────────────────────

    def on_mouse_click(self, x: int, y: int) -> None:
        """鼠标左键释放回调 — 触发 UI 控件采集

        Args:
            x, y: 屏幕坐标
        """
        win = self.win

        # 检查点击是否在目标窗口内
        if (x < win.win_left or x > win.win_left + win.win_width or
                y < win.win_top or y > win.win_top + win.win_height):
            return

        self._capture_count += 1
        count = self._capture_count

        try:
            # 边界刷新冷却：每 N 次才刷新一次窗口边界
            if count % self._bounds_refresh_interval == 1:
                if hasattr(self.collector.adapter, 'refresh_bounds_silent'):
                    self.collector.adapter.refresh_bounds_silent(win)

            # 执行完整采集（内含智能跳过：已知控件跳过全量遍历）
            # save_screenshot=False: 不保存全屏截图，避免与主程序 mss 截图重复
            screenshot, candidates, new_count = self.collector.capture_full(
                mouse_x=x, mouse_y=y, save_screenshot=False
            )

            total = self.collector.get_count()

            if new_count > 0:
                self._traverse_count += 1
                print(f"  [UICollect] #{count:03d} \U0001f5b1({x},{y}) "
                      f"\u2705 +{new_count} 新控件 (共 {total} 个)")
            else:
                if len(candidates) == 0:
                    self._skip_count += 1
                else:
                    self._traverse_count += 1
                    print(f"  [UICollect] #{count:03d} \U0001f5b1({x},{y}) "
                          f"\u23ed\ufe0f 无新控件 (共 {total} 个)")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  [UICollect] \u274c 采集异常 #{count}: {e}")

    # ── 生命周期 ──────────────────────────────────────────────

    def stop(self) -> dict:
        """停止采集，保存数据，返回统计摘要"""
        self.collector.get_storage().save()
        total = self.collector.get_count()
        captures = len(self.collector.get_storage().captures)
        elapsed = time.monotonic() - self._start_time
        print(f"  [UICollect] 采集停止: {captures} 次采集, "
              f"{total} 个控件, 跳过 {self._skip_count} 次, "
              f"耗时 {elapsed:.1f}s")
        return {
            "total_controls": total,
            "captures": captures,
            "skipped": self._skip_count,
            "traversed": self._traverse_count,
            "elapsed_s": round(elapsed, 1),
        }
