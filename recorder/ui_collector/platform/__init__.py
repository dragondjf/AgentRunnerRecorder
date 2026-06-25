"""
platform — 跨平台适配器抽象层
===============================
自动检测操作系统并加载对应的适配器。

用法:
    from ui_collector.platform import create_adapter, detect_platform, PlatformAdapter

    adapter = create_adapter()
    windows = adapter.enumerate_windows()
"""

from .base import (
    PlatformAdapter,
    WindowInfo,
    detect_platform,
    create_adapter,
    CLICKABLE_TYPES_WINDOWS,
    CLICKABLE_TYPES_LINUX,
    CLICKABLE_TYPES_DARWIN,
)

__all__ = [
    "PlatformAdapter",
    "WindowInfo",
    "detect_platform",
    "create_adapter",
    "CLICKABLE_TYPES_WINDOWS",
    "CLICKABLE_TYPES_LINUX",
    "CLICKABLE_TYPES_DARWIN",
]
