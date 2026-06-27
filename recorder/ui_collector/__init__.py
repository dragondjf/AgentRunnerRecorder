"""
ui_collector — 跨平台 Windows UI 控件增量采集库
================================================
支持 Windows (uiautomation)、Linux (AT-SPI)、macOS (AX API)。

核心组件:
  UICollector          — 采集器引擎（跨平台）
  WindowInfo           — 窗口信息数据类
  UIElement            — 控件元素数据类
  enumerate_windows()  — 枚举所有可见顶层窗口
  activate_window()    — 激活置顶窗口
  CollectionStorage    — 持久化存储（JSON + 截图）

平台适配器:
  create_adapter()     — 自动检测平台并创建适配器
  PlatformAdapter      — 适配器抽象基类
  detect_platform()    — 检测当前操作系统

用法示例:
    from ui_collector import UICollector, enumerate_windows, activate_window

    # 1. 选择窗口
    windows = enumerate_windows()
    win = windows[0]

    # 2. 激活窗口
    activate_window(win)

    # 3. 创建采集器
    collector = UICollector(win)

    # 4. 单点采集（传入屏幕坐标）
    elem = collector.capture_at_point(500, 300)

    # 5. 批量采集
    new_elems = collector.batch_capture()

    # 6. 访问结果
    all_items = collector.get_all()
    count = collector.get_count()
"""

from .window import (
    WindowInfo,
    enumerate_windows,
    enumerate_windows_fast,
    activate_window,
    capture_window_screenshot,
    find_window_by_title,
    find_window_by_pid,
    find_window_by_exe,
    get_platform_name,
)
from .element import (
    UIElement,
    elements_are_same,
    is_duplicate,
    deduplicate_elements,
    sort_elements_top_left,
)
from .storage import CollectionStorage, CaptureRecord
from .collector import UICollector
from .platform import (
    create_adapter,
    PlatformAdapter,
    detect_platform,
)

__all__ = [
    # 核心
    'UICollector',
    'WindowInfo',
    'UIElement',
    'CollectionStorage',
    'CaptureRecord',

    # 窗口操作
    'enumerate_windows',
    'enumerate_windows_fast',
    'activate_window',
    'capture_window_screenshot',
    'find_window_by_title',
    'find_window_by_pid',
    'find_window_by_exe',
    'get_platform_name',

    # 元素操作
    'elements_are_same',
    'is_duplicate',
    'deduplicate_elements',
    'sort_elements_top_left',

    # 平台适配
    'create_adapter',
    'PlatformAdapter',
    'detect_platform',
]
