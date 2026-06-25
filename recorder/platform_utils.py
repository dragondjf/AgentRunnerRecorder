"""
跨平台工具函数
统一封装各平台差异，提供一致的接口
"""
import os
import platform
import subprocess
from pathlib import Path

# ── 平台常量 ────────────────────────────────────────────────
_SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"

IS_WINDOWS = _SYSTEM == "Windows"
IS_MACOS = _SYSTEM == "Darwin"
IS_LINUX = _SYSTEM == "Linux"


# ── 文件/文件夹打开 ──────────────────────────────────────────
def open_file(path: str) -> None:
    """跨平台打开文件或文件夹（使用系统默认程序）"""
    if IS_MACOS:
        subprocess.Popen(["open", path])
    elif IS_WINDOWS:
        os.startfile(path)
    else:  # Linux / 其他
        subprocess.Popen(["xdg-open", path])


def open_folder(path: str) -> None:
    """跨平台打开文件夹（在文件管理器中显示）"""
    path = os.path.realpath(path)
    if IS_MACOS:
        subprocess.Popen(["open", path])
    elif IS_WINDOWS:
        subprocess.Popen(["explorer", path])
    else:  # Linux / 其他
        subprocess.Popen(["xdg-open", path])


# ── 应用图标 ─────────────────────────────────────────────────
def get_app_icon(base_dir: Path, name: str = "app_icon") -> Path:
    """根据平台返回正确的图标文件路径
    
    Args:
        base_dir: 图标所在目录 (如 images/)
        name: 图标文件名前缀（不含扩展名）
    
    Returns:
        完整的图标路径，格式: Windows=.ico, macOS=.icns, Linux=.png
    """
    ext_map = {
        "Windows": ".ico",
        "Darwin": ".icns",
        "Linux": ".png",
    }
    ext = ext_map.get(_SYSTEM, ".png")
    icon_path = base_dir / f"{name}{ext}"
    # 回退：如果平台特定格式不存在，尝试 .png
    if not icon_path.exists():
        fallback = base_dir / f"{name}.png"
        if fallback.exists():
            return fallback
    return icon_path


# ── 默认录制目录 ─────────────────────────────────────────────
def get_default_recordings_dir() -> str:
    """获取跨平台的默认录制存储目录"""
    return str(Path.home() / "Videos" / "ScreenRecordings")


# ── 文本编辑器回退列表 ──────────────────────────────────────
def get_editor_candidates() -> list[str]:
    """按优先级返回当前平台的文本编辑器命令列表"""
    if IS_WINDOWS:
        return ["code", "notepad"]
    elif IS_MACOS:
        return ["code", "open", "nano"]
    else:  # Linux
        return ["code", "gedit", "nano", "vim"]


# ── DPI 感知设置 (仅 Windows) ───────────────────────────────
def set_dpi_aware() -> None:
    """设置进程 DPI 感知（仅 Windows 有效，其他平台静默忽略）"""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ── 便捷属性 ─────────────────────────────────────────────────
def is_windows() -> bool:
    return IS_WINDOWS

def is_macos() -> bool:
    return IS_MACOS

def is_linux() -> bool:
    return IS_LINUX

def current_platform() -> str:
    return _SYSTEM
