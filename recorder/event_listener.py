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

import queue
import threading
import time
from typing import Callable

from pynput import keyboard, mouse

from .window_tracker import get_active_window, get_active_window_info

# ---------------------------------------------------------------------------
# Stop-hotkey definition: Ctrl + Shift + F5
# ---------------------------------------------------------------------------
_STOP_KEY = keyboard.Key.f5


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
    ):
        self._cb = callback
        self._t0 = start_time
        self._on_stop = on_stop
        self._on_ui_click = on_ui_click
        self._drag_px = drag_threshold
        self._dbl_sec = dblclick_threshold

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
                    self._dragging = True
                    self._drag_btn = b
                    self._emit(f"DragStart at ({dx}, {dy})")
            if self._dragging and b == self._drag_btn:
                now = time.monotonic()
                if now - self._drag_move_ts > 0.05:
                    self._emit(f"DragMove at ({x}, {y})")
                    self._drag_move_ts = now
            break

    # -- scroll ---------------------------------------------------------------

    def _proc_scroll(self, x: int, y: int, dy: int) -> None:
        if dy == 0:
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
