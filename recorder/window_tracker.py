"""Platform-specific active window detection.

Returns structured info including window title, process name,
binary path, and PID for the currently active (foreground) window.
"""

import os
import platform
import subprocess
from typing import Dict, Optional

_system = platform.system()


def get_active_window() -> str:
    """Return the title of the currently active window (legacy compat)."""
    info = get_active_window_info()
    return info.get("title", "") if info else ""


def get_active_window_info() -> Optional[Dict]:
    """Return structured info about the currently active window.

    Returns dict with keys:
        title:        窗口标题
        process_name:  进程文件名 (e.g., "SAM-Shock.exe")
        process_path:  完整二进制路径 (e.g., "C:\\...\\SAM-Shock.exe")
        pid:           进程 ID

    Returns None on failure.
    """
    try:
        if _system == "Darwin":
            return _macos_active_window_info()
        if _system == "Windows":
            return _windows_active_window_info()
        if _system == "Linux":
            return _linux_active_window_info()
    except Exception:
        pass
    return None


# ── Windows ────────────────────────────────────────────────────────────────


def _windows_active_window() -> str:   # legacy alias, kept for import compat
    info = _windows_active_window_info()
    return info.get("title", "") if info else ""


def _windows_active_window_info() -> Optional[Dict]:
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32          # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32      # type: ignore[attr-defined]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    # Window title
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    # PID
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value

    # Full binary path via QueryFullProcessImageNameW
    process_path = ""
    process_name = ""
    if pid_val:
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_val)
            if handle:
                try:
                    path_buf = ctypes.create_unicode_buffer(260)  # MAX_PATH
                    kernel32.QueryFullProcessImageNameW(
                        handle, 0, path_buf, ctypes.byref(wt.DWORD(260)),
                    )
                    process_path = path_buf.value
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            pass

    if process_path:
        process_name = os.path.basename(process_path)

    return {
        "title": title,
        "process_name": process_name,
        "process_path": process_path,
        "pid": pid_val,
    }


# ── macOS ──────────────────────────────────────────────────────────────────


def _macos_active_window() -> str:       # legacy alias
    info = _macos_active_window_info()
    return f"{info.get('process_name', '')} - {info.get('title', '')}" if info else ""


def _macos_active_window_info() -> Optional[Dict]:
    script = (
        'tell application "System Events"\n'
        "    set frontApp to name of first application process whose frontmost is true\n"
        "    try\n"
        "        tell process frontApp\n"
        "            set winTitle to name of front window\n"
        "        end tell\n"
        '        return frontApp & "\\n" & winTitle\n'
        "    on error\n"
        '        return frontApp & "\\n"\n'
        "    end try\n"
        'end tell'
    )
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    parts = r.stdout.strip().split("\n")
    app_name = parts[0] if parts else ""
    title = parts[1] if len(parts) > 1 else ""
    return {
        "title": title,
        "process_name": app_name,
        "process_path": "",
        "pid": 0,
    }


# ── Linux ──────────────────────────────────────────────────────────────────


def _linux_active_window() -> str:       # legacy alias
    info = _linux_active_window_info()
    return info.get("title", "") if info else ""


def _linux_active_window_info() -> Optional[Dict]:
    # Window title
    r_title = subprocess.run(
        ["xdotool", "getactivewindow", "getwindowname"],
        capture_output=True, text=True, timeout=2,
    )
    if r_title.returncode != 0 or not r_title.stdout.strip():
        return None
    title = r_title.stdout.strip()

    # PID via xdotool getwindowpid
    pid_val = 0
    process_name = ""
    process_path = ""
    r_pid = subprocess.run(
        ["xdotool", "getactivewindow", "getwindowpid"],
        capture_output=True, text=True, timeout=2,
    )
    if r_pid.returncode == 0 and r_pid.stdout.strip().isdigit():
        pid_val = int(r_pid.stdout.strip())
        try:
            link = os.readlink(f"/proc/{pid_val}/exe")
            process_path = link
            process_name = os.path.basename(link)
        except Exception:
            pass

    return {
        "title": title,
        "process_name": process_name,
        "process_path": process_path,
        "pid": pid_val,
    }
