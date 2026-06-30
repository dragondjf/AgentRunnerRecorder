"""Keyboard + mouse event listener (pynput) emitting workflow-compatible JSONL.

Low-level hooks (SetWindowsHookEx) have a strict timeout (~100 ms on Windows).
If the callback blocks too long, Windows silently drops the event.  This is
especially noticeable with **double-clicks**, which must arrive in rapid
succession.

Solution: the pynput callbacks do **nothing** but push a lightweight tuple
onto a `queue.Queue`.  A dedicated worker thread pops events and performs
all the heavy work (lock, JSON, GetForegroundWindow, etc.).
"""

from __future__ import annotations

import ctypes
import logging
import platform
import queue
import threading
import time
from typing import Callable

from pynput import keyboard, mouse

from .window_tracker import get_active_window, get_active_window_info

_LOG = logging.getLogger(__name__)
_SYSTEM = platform.system()

# ---------------------------------------------------------------------------
# Stop-hotkey definition: Ctrl + Shift + F5
# ---------------------------------------------------------------------------
_STOP_KEY = keyboard.Key.f5


# ---------------------------------------------------------------------------
# Cross-platform target-window rectangle query.
# Used to filter events that occur outside the user's chosen target app
# (taskbar, Recorder toolbar, other windows, etc.).
# ---------------------------------------------------------------------------
def _query_window_rect(hwnd) -> tuple[int, int, int, int] | None:
    """Return (left, top, width, height) of *hwnd*, or None when invalid.

    Implementation notes:
        * Windows: ``GetWindowRect`` via ctypes.  Fast (~0.02 ms/call).
        * Linux:   ``python-xlib`` is already a pynput dependency.
        * Darwin:  macOS target windows do not generally move while a recording
          is in progress; we fall back to a *None* result (filter active).
    """
    if not hwnd:
        return None
    try:
        if _SYSTEM == "Windows":
            import ctypes.wintypes as wt

            rect = wt.RECT()
            ok = ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(rect))
            if not ok:
                return None
            # If the window is minimised / hidden, width or height may be 0.
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return None
            return (int(rect.left), int(rect.top), int(w), int(h))

        if _SYSTEM == "Linux":
            try:
                from Xlib import display  # type: ignore
            except Exception:
                return None
            d = display.Display()
            w = d.create_resource_object("window", int(hwnd))
            geom = w.get_geometry()
            # ``get_geometry`` returns coordinates relative to the parent.
            # For top-level windows this is usually the root window,
            # which is what we want here.
            return (int(geom.x), int(geom.y), int(geom.width), int(geom.height))

        # macOS / unsupported — leave filtering to the PID check.
        return None
    except Exception:
        return None


class EventListener:
    """Capture OS-level input events and emit them in the recorder JSONL format.

    Events are delivered to *callback* as dicts::

        {"timestamp": "HH:MM:SS.mmm", "message": "...", "window": "..."}

    The listener also watches for **Ctrl+Shift+F5** and fires *on_stop*
    (filtering that combo out of the event log).
    """

    def __init__(
        self,
        callback: Callable[[dict], None],
        start_time: float,
        on_stop: Callable[[], None] | None = None,
        on_ui_click: Callable[[int, int], None] | None = None,
        drag_threshold: int = 5,
        dblclick_threshold: float = 0.4,
        target_win=None,
    ):
        self._cb = callback
        self._t0 = start_time
        self._on_stop = on_stop
        self._on_ui_click = on_ui_click
        self._drag_px = drag_threshold
        self._dbl_sec = dblclick_threshold

        # ── target-window filtering (None → no filtering, fully backwards-compatible) ──
        # target_win is a ``WindowInfo`` dataclass from ``ui_collector.platform.base``
        # exposing at least: ``hwnd`` (int | None), ``pid`` (int) and bounding-box
        # fields ``win_left / win_top / win_width / win_height``.
        self._target_win = target_win
        self._rect_cache: tuple[int, int, int, int] | None = None
        self._rect_cache_ts: float = 0.0
        self._rect_cache_ttl: float = 0.2  # 200 ms — keep ctypes calls cheap
        self._filter_warned: bool = False  # avoid log spam when target is gone

        # ── event queue: hook → worker ──
        self._q: queue.Queue[tuple | None] = queue.Queue()

        # ── mouse state (accessed only by worker thread) ──
        self._pressed: dict[str, tuple[int, int, float]] = {}
        self._dragging = False
        self._drag_btn: str | None = None
        self._drag_move_ts = 0.0
        self._last_release: dict[str, tuple[int, int, float]] = {}

        # ── keyboard state (accessed only by worker thread) ──
        self._mods: set[str] = set()

        # ── threading ──
        self._ml: mouse.Listener | None = None
        self._kl: keyboard.Listener | None = None
        self._worker: threading.Thread | None = None
        self._running = False

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        # Start the async worker first
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

        # Hook callbacks — these must return as fast as possible
        self._ml = mouse.Listener(
            on_click=self._hook_on_click,
            on_scroll=self._hook_on_scroll,
            on_move=self._hook_on_move,
        )
        self._kl = keyboard.Listener(
            on_press=self._hook_on_press,
            on_release=self._hook_on_release,
        )
        self._ml.start()
        self._kl.start()

    def stop(self) -> None:
        self._running = False
        self._q.put(None)  # signal worker to exit
        if self._ml:
            self._ml.stop()
        if self._kl:
            self._kl.stop()
        if self._worker:
            self._worker.join(timeout=2)

    # -- helpers (used by worker thread only) ──────────────────────────────

    def _ts(self) -> str:
        e = time.monotonic() - self._t0
        h = int(e // 3600)
        m = int((e % 3600) // 60)
        s = int(e % 60)
        ms = int((e % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    # -- target-window filtering (worker thread only) -----------------------

    def _is_in_target_window(self, x: int, y: int) -> bool:
        """Return True if (x, y) is inside the user-selected target window.

        When no target window is set (``_target_win is None``) we always
        return True — fully backwards-compatible with the legacy behaviour.

        The window rectangle is queried via the platform-specific
        :func:`_query_window_rect` helper, cached for 200 ms to keep the cost
        negligible for high-frequency mouse-move events.
        """
        win = self._target_win
        if win is None:
            return True

        # Refresh cache lazily.
        now = time.monotonic()
        if (
            self._rect_cache is None
            or (now - self._rect_cache_ts) > self._rect_cache_ttl
        ):
            self._rect_cache = _query_window_rect(getattr(win, "hwnd", None))
            self._rect_cache_ts = now

        rect = self._rect_cache
        if rect is None:
            # Window gone — be conservative: drop the event.  This protects the
            # log from trailing clicks the user makes on the taskbar / Recorder
            # toolbar while shutting the target app down.
            if not self._filter_warned:
                _LOG.info(
                    "[EventListener] target window hwnd=%s unavailable; "
                    "filtering is now rejecting all events.",
                    getattr(win, "hwnd", None),
                )
                self._filter_warned = True
            return False
        self._filter_warned = False

        l, t, w, h = rect
        return l <= x <= l + w and t <= y <= t + h

    def _pid_matches_target(self, win_info) -> bool:
        """Return True when the foreground process is the chosen target.

        When either side lacks a ``pid`` (e.g. macOS) we fall back to ``True``
        so the rectangle check remains the primary guard.
        """
        win = self._target_win
        if win is None or win_info is None:
            return True
        target_pid = getattr(win, "pid", 0) or 0
        event_pid = win_info.get("pid", 0) or 0
        if not target_pid or not event_pid:
            return True
        return target_pid == event_pid

    def _should_drop_event(self, x: int, y: int) -> bool:
        """Combined rectangle + PID filter.  Return True to *drop* the event."""
        if self._target_win is None:
            return False
        if not self._is_in_target_window(x, y):
            return True
        # Foreground-window PID check — only meaningful on platforms that
        # actually populate ``win_info["pid"]`` (Windows/Linux).
        try:
            win_info = get_active_window_info()
        except Exception:
            win_info = None
        if not self._pid_matches_target(win_info):
            return True
        return False

    def _emit(self, message: str) -> None:
        try:
            win_info = get_active_window_info()
        except Exception:
            win_info = None
        win_title = win_info.get("title", "") if win_info else ""
        try:
            event = {"timestamp": self._ts(), "message": message, "window": win_title}
            # 附加结构化进程信息（向后兼容：window 字段仍为纯标题字符串）
            if win_info:
                event["process_name"] = win_info.get("process_name", "")
                event["process_path"] = win_info.get("process_path", "")
                event["pid"] = win_info.get("pid", 0)
            self._cb(event)
        except Exception:
            import traceback
            traceback.print_exc()

    @staticmethod
    def _btn(button) -> str:
        if button == mouse.Button.left:
            return "L"
        if button == mouse.Button.right:
            return "R"
        return "M"

    # ========================================================================
    # Worker loop — all heavy processing happens here (no hook timeout risk)
    # ========================================================================

    def _worker_loop(self) -> None:
        while self._running:
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            tag, *args = item

            try:
                if tag == "click":
                    self._proc_click(*args)
                elif tag == "scroll":
                    self._proc_scroll(*args)
                elif tag == "move":
                    self._proc_move(*args)
                elif tag == "press":
                    self._proc_press(*args)
                elif tag == "release":
                    self._proc_release(*args)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[EventListener] worker error: {e}")

    # -- click ----------------------------------------------------------------

    def _proc_click(self, x: int, y: int, btn_name: str, pressed: bool, now: float) -> None:
        b = btn_name

        if pressed:
            # Target-window filter — drop the press entirely if it happened
            # outside the user's chosen app (taskbar / Recorder toolbar / etc.).
            if self._should_drop_event(x, y):
                # Clear any leftover state so the matching release is also
                # dropped (it will hit the ``b not in self._pressed`` branch).
                self._pressed.pop(b, None)
                self._dragging = False
                self._drag_btn = None
                return

            # double-click? (check BEFORE adding to _pressed)
            prev = self._last_release.get(b)
            if prev:
                px, py, pt = prev
                if (now - pt < self._dbl_sec
                        and abs(x - px) <= 5 and abs(y - py) <= 5):
                    self._emit(f"{b}DblClick at ({x}, {y})")
                    self._last_release.pop(b, None)
                    return

            self._pressed[b] = (x, y, now)
            self._dragging = False
            self._emit(f"{b}Click at ({x}, {y})")
        else:
            # If the press was filtered out (or never tracked), drop the
            # matching release too — keeps click/release pairs symmetric.
            if b not in self._pressed:
                return
            self._pressed.pop(b, None)
            if self._dragging and self._drag_btn == b:
                self._emit(f"{b}DragEnd at ({x}, {y})")
                self._dragging = False
                self._drag_btn = None
            else:
                self._emit(f"{b}Release at ({x}, {y})")
                # 左键释放时触发 UI 控件采集
                if b == "L" and self._on_ui_click:
                    try:
                        self._on_ui_click(x, y)
                    except Exception:
                        import traceback
                        traceback.print_exc()
                self._last_release[b] = (x, y, now)

    # -- move -----------------------------------------------------------------

    def _proc_move(self, x: int, y: int) -> None:
        if not self._pressed:
            return
        for b, (dx, dy, _) in self._pressed.items():
            if not self._dragging:
                if max(abs(x - dx), abs(y - dy)) > self._drag_px:
                    # Only start a drag if the *press* landed inside the
                    # target window.  This preserves the legacy behaviour for
                    # unfiltered sessions (target_win is None) and prevents
                    # spurious drag tracks when the user clicked on the
                    # taskbar before moving the mouse into the app.
                    if not self._is_in_target_window(dx, dy):
                        return
                    self._dragging = True
                    self._drag_btn = b
                    self._emit(f"DragStart at ({dx}, {dy})")
            if self._dragging and b == self._drag_btn:
                # DragMove samples may travel outside the target window
                # (dragging a slider, scrollbar, etc.) — always emit them
                # so the resulting track is continuous.
                now = time.monotonic()
                if now - self._drag_move_ts > 0.05:
                    self._emit(f"DragMove at ({x}, {y})")
                    self._drag_move_ts = now
            break

    # -- scroll ---------------------------------------------------------------

    def _proc_scroll(self, x: int, y: int, dy: int) -> None:
        if dy == 0:
            return
        if self._should_drop_event(x, y):
            return
        direction = "ScrollUp" if dy > 0 else "ScrollDown"
        for _ in range(max(1, abs(dy))):
            self._emit(f"{direction} at ({x}, {y})")

    # ========================================================================
    # Keyboard (worker)
    # ========================================================================

    _MOD_MAP: dict = {
        keyboard.Key.shift: "SHIFT",
        keyboard.Key.shift_l: "SHIFT",
        keyboard.Key.shift_r: "SHIFT",
        keyboard.Key.ctrl: "CTRL",
        keyboard.Key.ctrl_l: "CTRL",
        keyboard.Key.ctrl_r: "CTRL",
        keyboard.Key.alt: "ALT",
        keyboard.Key.alt_l: "ALT",
        keyboard.Key.alt_r: "ALT",
        keyboard.Key.cmd: "CMD",
        keyboard.Key.cmd_l: "CMD",
        keyboard.Key.cmd_r: "CMD",
    }

    _SPECIAL: dict = {
        keyboard.Key.enter: "ENTER",
        keyboard.Key.backspace: "BACKSPACE",
        keyboard.Key.delete: "DELETE",
        keyboard.Key.space: "SPACE",
        keyboard.Key.tab: "TAB",
        keyboard.Key.esc: "ESC",
        keyboard.Key.up: "UP",
        keyboard.Key.down: "DOWN",
        keyboard.Key.left: "LEFT",
        keyboard.Key.right: "RIGHT",
        keyboard.Key.home: "HOME",
        keyboard.Key.end: "END",
        keyboard.Key.page_up: "PAGE_UP",
        keyboard.Key.page_down: "PAGE_DOWN",
        keyboard.Key.f1: "F1",
        keyboard.Key.f2: "F2",
        keyboard.Key.f3: "F3",
        keyboard.Key.f4: "F4",
        keyboard.Key.f5: "F5",
        keyboard.Key.f6: "F6",
        keyboard.Key.f7: "F7",
        keyboard.Key.f8: "F8",
        keyboard.Key.f9: "F9",
        keyboard.Key.f10: "F10",
        keyboard.Key.f11: "F11",
        keyboard.Key.f12: "F12",
    }

    def _is_stop_hotkey(self, key) -> bool:
        return key == _STOP_KEY and "CTRL" in self._mods and "SHIFT" in self._mods

    def _key_name(self, key) -> str | None:
        if key in self._SPECIAL:
            return self._SPECIAL[key]
        if hasattr(key, "char") and key.char:
            c = key.char
            if len(c) == 1 and ord(c) < 32 and "CTRL" in self._mods:
                return chr(ord(c) + 64)
            return c
        return None

    def _proc_press(self, key, now: float) -> None:
        if key in self._MOD_MAP:
            self._mods.add(self._MOD_MAP[key])
            return
        if self._is_stop_hotkey(key):
            if self._on_stop:
                self._on_stop()
            return
        name = self._key_name(key)
        if name is None:
            return
        if "CTRL" in self._mods:
            self._emit(f"Hotkey: CTRL+{name.upper()}")
        elif "SHIFT" in self._mods and len(name) == 1:
            self._emit(f"Hotkey: SHIFT+{name.upper()}")
        else:
            self._emit(f"Key Press: {name}")

    def _proc_release(self, key, now: float) -> None:
        if key in self._MOD_MAP:
            self._mods.discard(self._MOD_MAP[key])
            return
        if key == _STOP_KEY:
            return
        name = self._key_name(key)
        if name is None:
            return
        self._emit(f"Key Release: {name}")

    # ========================================================================
    # Hook callbacks — ONLY put into queue, return immediately
    # ========================================================================

    def _hook_on_click(self, x, y, button, pressed) -> bool:
        self._q.put(("click", int(x), int(y), self._btn(button), pressed, time.monotonic()))
        return True

    def _hook_on_move(self, x, y) -> None:
        self._q.put(("move", int(x), int(y)))

    def _hook_on_scroll(self, x, y, dx, dy) -> None:
        self._q.put(("scroll", int(x), int(y), dy))

    def _hook_on_press(self, key) -> None:
        self._q.put(("press", key, time.monotonic()))

    def _hook_on_release(self, key) -> None:
        self._q.put(("release", key, time.monotonic()))
