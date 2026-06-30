"""Global hotkey listener — Ctrl+Shift+F5 (stop) / Ctrl+Shift+F9 (pause toggle)."""

import threading
import time


class HotkeyListener:
    """Background thread listening for global hotkeys via pynput.

    Usage::

        hk = HotkeyListener(on_stop=stop_fn, on_pause_toggle=pause_fn)
        hk.start()
        # ... later ...
        hk.stop()
    """

    def __init__(self, on_stop, on_pause_toggle):
        self._on_stop = on_stop
        self._on_pause_toggle = on_pause_toggle
        self._thread = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True, name="hotkey")
        self._thread.start()

    def stop(self):
        self._running = False

    def _listen(self):
        try:
            from pynput import keyboard
            _mods: set = set()

            def on_press(key):
                if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    _mods.add("SHIFT"); return
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    _mods.add("CTRL"); return
                if "CTRL" in _mods and "SHIFT" in _mods:
                    if key == keyboard.Key.f5: self._on_stop()
                    elif key == keyboard.Key.f9: self._on_pause_toggle()

            def on_release(key):
                if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    _mods.discard("SHIFT")
                elif key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    _mods.discard("CTRL")

            with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
                while self._running:
                    time.sleep(0.2)
                l.stop()
        except ImportError:
            pass
