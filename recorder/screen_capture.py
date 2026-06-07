"""Screen recording via mss + OpenCV VideoWriter."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

@dataclass
class ScreenInfo:
    """Screen dimensions and scaling metadata for the CONFIG line."""

    logical_width: int
    logical_height: int
    physical_width: int
    physical_height: int
    scale_factor: float
    x0: int = 0
    y0: int = 0

class ScreenCapture:
    """Capture the screen to an MP4 video in a background thread.

    The video is written at **logical** resolution so that pixel positions
    in frames correspond 1-to-1 with pynput mouse coordinates.
    """

    def __init__(self, output_path: str, fps: int = 15, monitor_idx: int = 0):
        self.output_path = output_path
        self.fps = fps
        self.monitor_idx = monitor_idx

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._pause_lock = threading.Lock()
        self._paused = False

        self.start_time: float = 0.0
        self.screen_info: ScreenInfo | None = None
        self.frame_count: int = 0

    # -- public API -----------------------------------------------------------

    def start(self) -> ScreenInfo:
        """Start recording.  Blocks until the first frame has been grabbed."""
        self._stop.clear()
        self._ready.clear()
        self._paused = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="screen-capture")
        self._thread.start()
        self._ready.wait(timeout=15)
        if self.screen_info is None:
            raise RuntimeError("Screen capture failed to initialize")
        return self.screen_info

    def pause(self) -> None:
        """Pause recording (stop writing frames)."""
        with self._pause_lock:
            self._paused = True

    def resume(self) -> None:
        """Resume recording."""
        with self._pause_lock:
            self._paused = False

    @property
    def is_paused(self) -> bool:
        with self._pause_lock:
            return self._paused

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    # -- internals ------------------------------------------------------------

    def _loop(self) -> None:
        import mss

        with mss.mss() as sct:
            monitors = sct.monitors
            # monitors[0] = entire virtual screen, [1] = primary, etc.
            idx = min(self.monitor_idx + 1, len(monitors) - 1)
            mon = monitors[idx]
            logical_w: int = mon["width"]
            logical_h: int = mon["height"]

            # Probe physical resolution from one grab
            sample = sct.grab(mon)
            physical_w, physical_h = sample.width, sample.height
            scale = round(physical_w / logical_w, 2) if logical_w else 1.0

            self.screen_info = ScreenInfo(
                logical_width=logical_w,
                logical_height=logical_h,
                physical_width=physical_w,
                physical_height=physical_h,
                scale_factor=scale,
                x0=mon.get("left", 0),
                y0=mon.get("top", 0),
            )

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # MPEG-4 (reliable on all systems)
            # H.264 conversion happens post-recording via ffmpeg
            writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (logical_w, logical_h))
            interval = 1.0 / self.fps

            self.start_time = time.monotonic()
            self._ready.set()

            try:
                while not self._stop.is_set():
                    t0 = time.monotonic()

                    # Pause: skip frame capture
                    if self.is_paused:
                        self._stop.wait(0.1)
                        continue

                    shot = sct.grab(mon)
                    frame = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(
                        shot.height, shot.width, 4
                    )
                    bgr = frame[:, :, :3].copy()

                    # Down-scale Retina / HiDPI to logical size
                    if bgr.shape[1] != logical_w or bgr.shape[0] != logical_h:
                        bgr = cv2.resize(bgr, (logical_w, logical_h), interpolation=cv2.INTER_AREA)

                    writer.write(bgr)
                    self.frame_count += 1

                    remaining = interval - (time.monotonic() - t0)
                    if remaining > 0:
                        self._stop.wait(remaining)
            finally:
                writer.release()
