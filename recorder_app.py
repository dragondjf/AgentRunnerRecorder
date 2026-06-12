from __future__ import annotations

"""
Simple Screen Recorder — 简易录屏工具
======================================
暗色主题 · PNG图标 · 折叠面板

按钮栏布局（从左到右）：
  空闲态：  [record] [timer]                    [settings] [log] [folder] [export]
  录制态：  [stop]   [timer]  [pause]            [settings] [log] [folder] [export]
  暂停态：  [stop]   [timer]  [resume]           [settings] [log] [folder] [export]

快捷键（录制中）：
  Ctrl+Shift+F5  停止录制
  Ctrl+Shift+F9  暂停/继续
"""

import os
import sys
import time
import threading
import zipfile
import subprocess
import platform
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

# Pillow 10+ 用 LANCZOS，旧版用 ANTIALIAS
_RESAMPLE = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", None))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recorder.core import RecordingSession
from recorder.report_generator import generate_reports

# ══════════════════════════════════════════════════════════════════════
# 配色
# ══════════════════════════════════════════════════════════════════════

class C:
    BG          = "#0f0f14"
    SURFACE     = "#1a1a24"
    SURFACE2    = "#22222e"
    BORDER      = "#2a2a3a"
    TEXT        = "#ffffff"
    TEXT2       = "#ffffff"
    ACCENT      = "#ff4757"
    ACCENT_DIM  = "#cc3344"
    ACCENT2     = "#7c8aff"
    GREEN       = "#2ed573"
    YELLOW      = "#ffa502"
    WHITE       = "#ffffff"
    RED_DOT     = "#ff4757"

BTN_SIZE   = 36   # 所有按钮统一显示尺寸
BTN_GAP    = 8    # 按钮间距

# ══════════════════════════════════════════════════════════════════════
# 图标加载器
# ══════════════════════════════════════════════════════════════════════

class Icons:
    """加载并缓存 PNG 图标为 PhotoImage。优先从 color 子目录加载，不存在时回退到父目录。"""
    _cache = {}
    _dir: Path = Path(__file__).parent / "images" / "icons_64"
    _color_dir: Path = _dir / "color"

    @classmethod
    def get(cls, name: str, size: int = BTN_SIZE) -> ImageTk.PhotoImage:
        key = f"{name}@{size}"
        if key not in cls._cache:
            # 优先从 color 子目录加载
            color_path = cls._color_dir / f"{name}.png"
            if color_path.exists():
                img = Image.open(color_path)
            else:
                img = Image.open(cls._dir / f"{name}.png")
            img = img.resize((size, size), _RESAMPLE)
            cls._cache[key] = ImageTk.PhotoImage(img)
        return cls._cache[key]

# ══════════════════════════════════════════════════════════════════════
# 图标按钮
# ══════════════════════════════════════════════════════════════════════

class Btn(tk.Label):
    """统一图标按钮：32x32 Label + PhotoImage，hover 背景切换 + tooltip。"""

    def __init__(self, parent, icon_name: str, command=None, tooltip="",
                 size=BTN_SIZE, **kw):
        self._img = Icons.get(icon_name, size)
        super().__init__(
            parent, image=self._img,
            bg=C.BG, width=size, height=size,
            highlightthickness=0, bd=0, cursor="hand2",
            **kw,
        )
        self._cmd = command
        self._size = size
        self._tooltip_text = tooltip
        self._tip_win = None
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def set_icon(self, name: str):
        self._img = Icons.get(name, self._size)
        self.configure(image=self._img)

    def _enter(self, e):
        self.configure(bg=C.SURFACE2)
        if self._tooltip_text:
            self._tip_win = tw = tk.Toplevel(self)
            tw.wm_overrideredirect(True)
            tw.configure(bg=C.SURFACE2)
            tw.attributes("-topmost", True)
            tk.Label(tw, text=self._tooltip_text, bg=C.SURFACE2, fg=C.TEXT,
                     font=("", 9), padx=10, pady=4).pack()
            tw.update_idletasks()
            x = self.winfo_rootx() + self._size // 2 - tw.winfo_reqwidth() // 2
            y = self.winfo_rooty() + self._size + 6
            tw.wm_geometry(f"+{x}+{y}")

    def _leave(self, e):
        self.configure(bg=C.BG)
        if self._tip_win:
            self._tip_win.destroy()
            self._tip_win = None

    def _click(self, e):
        if self._cmd:
            self._cmd()

# ══════════════════════════════════════════════════════════════════════
# 全局热键
# ══════════════════════════════════════════════════════════════════════

class HotkeyListener:
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

# ══════════════════════════════════════════════════════════════════════
# 主应用
# ══════════════════════════════════════════════════════════════════════

class ScreenRecorderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AgentRunner Recorder")
        self.root.configure(bg=C.BG)
        self.root.resizable(False, False)

        # 应用图标
        _icon_path = Path(__file__).parent / "images" / "app_icon.ico"
        if _icon_path.exists():
            self.root.iconbitmap(str(_icon_path))
        else:
            self.root.iconphoto(True, ImageTk.PhotoImage(
                Image.open(Path(__file__).parent / "images" / "app_icon.png").resize((32, 32), _RESAMPLE)
            ))

        # 状态
        self._session = None
        self._hotkey = None
        self._recording = False
        self._paused = False
        self._project_name = ""
        self._output_dir = ""
        self._settings_visible = False
        self._log_visible = False
        self._update_job = None
        self._countdown = 0
        self._countdown_job = None

        # Tk 变量
        self._fps = tk.IntVar(value=15)
        self._monitor = tk.IntVar(value=0)
        self._timer_var = tk.StringVar(value="00:00:00")
        self._frame_var = tk.StringVar(value="0")
        self._event_var = tk.StringVar(value="0")
        self._shot_var = tk.StringVar(value="0")
        self._video_sz_var = tk.StringVar(value="0 MB")
        self._log_sz_var = tk.StringVar(value="0 KB")

        self._build_ui()
        self._refit()
        self._show_top_right()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ──────────────────────────────────────────────────

    def _build_ui(self):
        self._main = tk.Frame(self.root, bg=C.BG)
        self._main.pack(fill=tk.X)

        # ═══════════════════════════════════════════════════════════
        # 按钮栏：[录制/停止] [计时器] [暂停/恢复] ... [设置][日志][目录][导出]
        # ═══════════════════════════════════════════════════════════
        self._toolbar = tk.Frame(self._main, bg=C.BG)
        self._toolbar.pack(fill=tk.X, padx=12, pady=8)

        # ─ 左区：录制/停止 + 计时器 ─
        left = tk.Frame(self._toolbar, bg=C.BG)
        left.pack(side=tk.LEFT)

        # 录制/停止按钮
        self._record_btn = Btn(left, "record", command=self._toggle_record, tooltip="开始录制")
        self._record_btn.pack(side=tk.LEFT)

        # 计时器
        self._timer_lbl = tk.Label(
            left, textvariable=self._timer_var,
            font=("Consolas", 20, "bold"), fg=C.TEXT, bg=C.BG,
        )
        self._timer_lbl.pack(side=tk.LEFT, padx=(14, 0))

        # ─ 中区：暂停/恢复（仅录制中显示） ─
        self._pause_wrapper = tk.Frame(self._toolbar, bg=C.BG)
        self._pause_btn = Btn(self._pause_wrapper, "pause", command=self._toggle_pause, tooltip="暂停")
        self._pause_btn.pack()

        # ─ 右区：功能按钮 ─
        right = tk.Frame(self._toolbar, bg=C.BG)
        right.pack(side=tk.RIGHT)

        self._settings_btn = Btn(right, "settings", command=self._toggle_settings, tooltip="设置")
        self._settings_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        self._log_btn = Btn(right, "log", command=self._toggle_log, tooltip="日志")
        self._log_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        self._folder_btn = Btn(right, "folder", command=self._open_dir, tooltip="打开目录")
        self._folder_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        self._history_btn = Btn(right, "history", command=self._open_history, tooltip="历史")
        self._history_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        # Export: icon button + lazy-loaded expandable bar
        self._history_server = None
        self._export_menu_open = False
        self._export_btn = tk.Button(right, image=Icons.get("export", 32),
                                         command=self._toggle_export_menu, bg=C.BG,
                                         activebackground=C.SURFACE2, bd=0, cursor="hand2",
                                         width=32, height=32)
        self._export_btn.pack(side=tk.LEFT)
        self._export_btn.bind("<Enter>", lambda e: self._export_btn.configure(bg=C.SURFACE2))
        self._export_btn.bind("<Leave>", lambda e: self._export_btn.configure(bg=C.BG))
        self._export_panel = None

        # ═══ 状态栏（录制中显示）═══
        self._status_bar = tk.Frame(self._main, bg=C.SURFACE)
        inner_s = tk.Frame(self._status_bar, bg=C.SURFACE)
        inner_s.pack(fill=tk.X, padx=12, pady=(6, 8))

        for label, var in [
            ("帧", self._frame_var), ("事件", self._event_var),
            ("截图", self._shot_var), ("视频", self._video_sz_var),
            ("日志", self._log_sz_var),
        ]:
            col = tk.Frame(inner_s, bg=C.SURFACE)
            col.pack(side=tk.LEFT, padx=(0, 20))
            tk.Label(col, text=label, font=("", 8), fg=C.TEXT2, bg=C.SURFACE).pack(anchor=tk.W)
            tk.Label(col, textvariable=var, font=("", 10, "bold"), fg=C.TEXT, bg=C.SURFACE).pack(anchor=tk.W)

        sf = tk.Frame(inner_s, bg=C.SURFACE)
        sf.pack(side=tk.RIGHT)
        self._status_dot = tk.Canvas(sf, width=10, height=10, bg=C.SURFACE, highlightthickness=0)
        self._status_dot.pack(side=tk.LEFT, padx=(0, 6))
        self._status_dot.create_oval(1, 1, 9, 9, fill=C.RED_DOT, outline="", tags="dot")
        self._status_lbl = tk.Label(sf, text="REC", font=("", 9, "bold"), fg=C.RED_DOT, bg=C.SURFACE)
        self._status_lbl.pack(side=tk.LEFT)

        # ═══ 设置面板 ═══
        self._settings_frame = tk.Frame(self._main, bg=C.SURFACE)
        inner_set = tk.Frame(self._settings_frame, bg=C.SURFACE)
        inner_set.pack(fill=tk.X, padx=16, pady=12)

        r0 = tk.Frame(inner_set, bg=C.SURFACE)
        r0.pack(fill=tk.X, pady=(0, 8))
        tk.Label(r0, text="帧率", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._fps_cb = ttk.Combobox(
            r0, textvariable=self._fps, values=[10, 15, 20, 25, 30],
            width=4, state="readonly",
        )
        self._fps_cb.pack(side=tk.LEFT, padx=(8, 24))
        tk.Label(r0, text="显示器", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._mon_cb = ttk.Combobox(
            r0, textvariable=self._monitor, values=[0, 1, 2],
            width=4, state="readonly",
        )
        self._mon_cb.pack(side=tk.LEFT, padx=(8, 0))

        r1 = tk.Frame(inner_set, bg=C.SURFACE)
        r1.pack(fill=tk.X)
        tk.Label(r1, text="输出目录", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(anchor=tk.W)
        r1b = tk.Frame(r1, bg=C.SURFACE)
        r1b.pack(fill=tk.X, pady=(4, 0))
        default_dir = str(Path.home() / "Videos" / "ScreenRecordings")
        self._dir_var = tk.StringVar(value=default_dir)
        self._dir_entry = tk.Entry(
            r1b, textvariable=self._dir_var, font=("", 9),
            bg=C.SURFACE2, fg=C.TEXT, insertbackground=C.TEXT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=C.BORDER, highlightcolor=C.ACCENT2,
        )
        self._dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        tk.Button(
            r1b, text="浏览", font=("", 9), command=self._browse_dir,
            bg=C.SURFACE2, fg=C.TEXT, relief=tk.FLAT, bd=0,
            padx=12, pady=3, cursor="hand2",
            activebackground=C.BORDER, activeforeground=C.TEXT,
        ).pack(side=tk.LEFT, padx=(6, 0))

        # ═══ 日志面板 ═══
        self._log_frame = tk.Frame(self._main, bg=C.SURFACE)
        inner_log = tk.Frame(self._log_frame, bg=C.SURFACE)
        inner_log.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        self._log_widget = tk.Text(
            inner_log, height=8, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9), bg=C.BG, fg=C.TEXT2,
            insertbackground=C.TEXT, relief=tk.FLAT, bd=0,
            highlightthickness=0, padx=8, pady=6,
        )
        self._log_widget.pack(fill=tk.BOTH, expand=True)

        # ttk 暗色样式
        self._style_ttk()

    def _style_ttk(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=C.SURFACE2, background=C.SURFACE2,
                        foreground=C.TEXT, arrowcolor=C.TEXT,
                        selectbackground=C.ACCENT2, selectforeground=C.WHITE,
                        bordercolor=C.BORDER, darkcolor=C.SURFACE2,
                        lightcolor=C.SURFACE2, relief=tk.FLAT)
        style.map("TCombobox",
                  fieldbackground=[("readonly", C.SURFACE2)],
                  foreground=[("readonly", C.TEXT)])

    # ── 面板折叠 ─────────────────────────────────────────────────

    def _toggle_settings(self):
        if self._settings_visible:
            self._settings_frame.pack_forget()
            self._settings_visible = False
        else:
            after = self._status_bar if self._status_bar.winfo_ismapped() else self._main.winfo_children()[0]
            self._settings_frame.pack(fill=tk.X, padx=12, pady=(0, 6), after=after)
            self._settings_visible = True
        self._refit()

    def _toggle_log(self):
        if self._log_visible:
            self._log_frame.pack_forget()
            self._log_visible = False
        else:
            after = self._settings_frame if self._settings_visible else (
                self._status_bar if self._status_bar.winfo_ismapped() else self._main.winfo_children()[0]
            )
            self._log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8), after=after)
            self._log_visible = True
        self._refit()

    def _open_history(self):
        """Open web history server."""
        from recorder.history_server import start_server
        if not self._history_server or not self._history_server.running:
            self._history_server = start_server(open_browser=True)
        else:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{self._history_server.port}")

    def _toggle_export_menu(self):
        """Toggle the export sub-icon bar below the toolbar."""
        if self._export_menu_open:
            if self._export_panel:
                self._export_panel.pack_forget()
            self._export_menu_open = False
        else:
            if self._export_panel is None:
                self._export_panel = tk.Frame(self._main, bg=C.SURFACE2, highlightthickness=0)
                items = [("video", "Video", self._open_video),
                         ("md", "Markdown", self._export_markdown),
                         ("json", "JSON", self._export_json),
                         ("html", "HTML", self._export_html),
                         ("word", "Word", self._export_word),
                         ("zip", "ZIP", self._export_zip)]
                for i in range(0, len(items), 3):
                    row = tk.Frame(self._export_panel, bg=C.SURFACE2)
                    row.pack(anchor="center", pady=4)
                    for icon, label, cmd in items[i:i+3]:
                        tk.Button(row, text=f" {label} ", image=Icons.get(icon, 24),
                                  compound=tk.LEFT, command=cmd,
                                  font=("", 9), fg=C.TEXT, bg=C.BG,
                                  activebackground=C.ACCENT2, activeforeground="white",
                                  bd=0, padx=8, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=4, pady=2)
            self._export_panel.pack(fill=tk.X, after=self._toolbar)
            self._export_menu_open = True
        self._refit()

    def _show_top_right(self):
        """Restore window and position at screen top-right."""
        self.root.deiconify()
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        ww = self.root.winfo_width()
        self.root.geometry(f"+{sw - ww - 20}+20")

    def _refit(self):
        self.root.update_idletasks()
        self._main.update_idletasks()
        req_h = self._main.winfo_reqheight()
        self.root.geometry(f"420x{req_h}")

    def _center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── 状态切换：按钮栏布局变化 ─────────────────────────────────

    def _layout_idle(self):
        """空闲态：[record] [timer]                    [settings][log][folder][export]"""
        self._record_btn.set_icon("record")
        self._record_btn._tooltip_text = "开始录制"
        self._pause_wrapper.pack_forget()

    def _layout_recording(self):
        """录制态：[stop] [timer] [pause]              [settings][log][folder][export]"""
        self._record_btn.set_icon("stop")
        self._record_btn._tooltip_text = "停止录制"
        self._pause_btn.set_icon("pause")
        self._pause_btn._tooltip_text = "暂停"
        # 暂停按钮插入计时器后面
        self._pause_wrapper.pack(side=tk.LEFT, padx=(10, 0), after=self._timer_lbl.master)

    def _layout_paused(self):
        """暂停态：[stop] [timer] [resume]             [settings][log][folder][export]"""
        self._pause_btn.set_icon("resume")
        self._pause_btn._tooltip_text = "继续录制"

    # ── 日志 ─────────────────────────────────────────────────────

    def _log(self, msg: str):
        self._log_widget.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.insert(tk.END, f"[{ts}] {msg}\n")
        self._log_widget.see(tk.END)
        self._log_widget.configure(state=tk.DISABLED)

    # ── 录制操作 ─────────────────────────────────────────────────

    def _browse_dir(self):
        d = filedialog.askdirectory(title="选择输出目录", initialdir=self._dir_var.get())
        if d:
            self._dir_var.set(d)

    def _toggle_record(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        base_dir = self._dir_var.get().strip()
        if not base_dir:
            messagebox.showwarning("提示", "请先设置输出目录")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._project_name = f"recording_{ts}"
        self._output_dir = os.path.join(base_dir, self._project_name)

        self._session = RecordingSession(
            project_name=self._project_name,
            output_dir=self._output_dir,
            fps=self._fps.get(),
            monitor_idx=self._monitor.get(),
        )

        # Pre-create session (don't start capture yet)
        self._recording = True
        self._paused = False
        self._countdown = 5
        self._layout_recording()
        self._status_bar.pack(fill=tk.X, padx=12, pady=(0, 4), after=self._toolbar)
        self._refit()

        self._log(f"录制将在 5 秒后开始...")
        self._log(f"输出目录  {self._output_dir}")
        self._timer_var.set(f"0{self._countdown}:00")

        self._hotkey = HotkeyListener(
            on_stop=lambda: self.root.after(0, self._stop_recording),
            on_pause_toggle=lambda: self.root.after(0, self._cancel_countdown_or_stop),
        )
        self._hotkey.start()
        self._countdown_loop()

    def _countdown_loop(self):
        """5-second countdown before recording starts."""
        if not self._recording:
            return
        if self._countdown > 0:
            self._timer_var.set(f"0{self._countdown}:00")
            self._countdown -= 1
            self._countdown_job = self.root.after(1000, self._countdown_loop)
        else:
            self._begin_capture()

    def _begin_capture(self):
        """Actually start the capture after countdown, then minimize window."""
        try:
            info = self._session.start()
        except Exception as e:
            messagebox.showerror("错误", f"启动录制失败:\n{e}")
            self._session = None
            self._recording = False
            self._layout_idle()
            self._status_bar.pack_forget()
            self._refit()
            return

        self._log(f"开始录制  {info.logical_width}x{info.logical_height}  @ {self._fps.get()} fps")

        # Minimize to avoid recording the app itself
        self.root.iconify()

        self._update_status_loop()

    def _cancel_countdown_or_stop(self):
        """During countdown: cancel it. During recording: stop."""
        if self._countdown > 0:
            # Cancel countdown, reset to idle
            if hasattr(self, '_countdown_job') and self._countdown_job:
                self.root.after_cancel(self._countdown_job)
                self._countdown_job = None
            self._recording = False
            if self._hotkey:
                self._hotkey.stop()
                self._hotkey = None
            self._session = None
            self._layout_idle()
            self._status_bar.pack_forget()
            self._refit()
            self._log("已取消录制")
            # Restore hotkey for normal operation
        else:
            self._stop_recording()

    def _stop_recording(self):
        # Restore window if minimized
        self._show_top_right()

        if self._countdown_job:
            self.root.after_cancel(self._countdown_job)
            self._countdown_job = None
        if self._hotkey:
            self._hotkey.stop()
            self._hotkey = None
        if self._session:
            self._session.stop()

        self._recording = False
        self._paused = False

        if self._update_job:
            self.root.after_cancel(self._update_job)
            self._update_job = None
        self._countdown = 0
        self._countdown_job = None

        self._layout_idle()
        self._status_bar.pack_forget()
        self._refit()

        if self._session:
            stats = self._session.stats()
            self._log(
                f"录制完成  时长 {self._fmt_time(stats.duration_s)}  |  "
                f"{stats.event_count} 事件  |  {stats.screenshot_count} 截图  |  "
                f"视频 {self._fmt_size(stats.video_size)}  |  日志 {self._fmt_size(stats.log_size)}"
            )
            self._timer_var.set(self._fmt_time(stats.duration_s))
            self._event_var.set(str(stats.event_count))
            self._shot_var.set(str(stats.screenshot_count))
            self._video_sz_var.set(self._fmt_size(stats.video_size))
            self._log_sz_var.set(self._fmt_size(stats.log_size))

            # Auto-generate operation reports (MD / HTML / Word)
            self._generate_reports()

        self._session = None

    def _toggle_pause(self):
        if not self._session:
            return
        if self._paused:
            # Resume: minimize window and continue recording
            self._session.resume()
            self._paused = False
            self._layout_recording()
            self._log("继续录制")
            self.root.after(500, lambda: self.root.iconify())
        else:
            # Pause: show window so user can interact
            self._session.pause()
            self._paused = True
            self._layout_paused()
            self._log("暂停录制")
            self.root.deiconify()
            self.root.lift()

    def _update_status_loop(self):
        if not self._recording or not self._session:
            return
        dur = time.monotonic() - self._session.start_monotonic() if self._session.start_monotonic() else 0
        self._timer_var.set(self._fmt_time(dur))
        self._event_var.set(str(self._session.event_count()))
        self._shot_var.set(str(self._session.screenshot_count()))

        if self._session._capture:
            self._frame_var.set(str(self._session._capture.frame_count))

        inputs = Path(self._output_dir) / "inputs"
        vp = inputs / f"{self._project_name}.mp4"
        lp = inputs / f"input_log_{self._project_name}.txt"
        self._video_sz_var.set(self._fmt_size(vp.stat().st_size if vp.exists() else 0))
        self._log_sz_var.set(self._fmt_size(lp.stat().st_size if lp.exists() else 0))

        self._update_job = self.root.after(500, self._update_status_loop)

    # ── 文件操作 ─────────────────────────────────────────────────

    def _open_dir(self):
        target = self._output_dir if (self._output_dir and os.path.isdir(self._output_dir)) else self._dir_var.get()
        if target and os.path.isdir(target):
            self._open_folder(target)
            self._log(f"打开目录  {target}")
        else:
            messagebox.showinfo("提示", "输出目录尚不存在，请先录制一次")

    def _generate_reports(self):
        """Auto-generate reports in background thread after recording stops."""
        inputs_dir = os.path.join(self._output_dir, "inputs")
        log_file = os.path.join(inputs_dir, f"input_log_{self._project_name}.txt")
        ss_dir = os.path.join(inputs_dir, "screenshots")

        if not os.path.exists(log_file):
            return

        video = os.path.join(inputs_dir, f"{self._project_name}.mp4")
        self._log("正在生成操作报告（后台）...")
        self._generating = True

        def _gen():
            from recorder.report_generator import parse_log, generate_markdown, generate_html, generate_word, generate_json
            try:
                events = parse_log(log_file)
                if not events:
                    self.root.after(0, lambda: self._log("  无操作事件，跳过报告生成"))
                    return

                # 1. Markdown
                md_path = os.path.join(inputs_dir, f"report_{self._project_name}.md")
                self.root.after(0, lambda: self._log("  [1/4] 正在生成 Markdown..."))
                generate_markdown(events, ss_dir, md_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [1/4] Markdown 已生成"))

                # 2. HTML
                html_path = os.path.join(inputs_dir, f"report_{self._project_name}.html")
                self.root.after(0, lambda: self._log("  [2/4] 正在生成 HTML..."))
                generate_html(events, ss_dir, html_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [2/4] HTML 已生成"))

                # 3. Word
                docx_path = os.path.join(inputs_dir, f"report_{self._project_name}.docx")
                self.root.after(0, lambda: self._log("  [3/4] 正在生成 Word..."))
                generate_word(events, ss_dir, docx_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [3/4] Word 已生成"))

                # 4. JSON
                json_path = os.path.join(inputs_dir, f"report_{self._project_name}.json")
                self.root.after(0, lambda: self._log("  [4/4] 正在生成 JSON..."))
                generate_json(events, ss_dir, json_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [4/4] JSON 已生成"))

                self.root.after(0, lambda: self._log("所有报告生成完成"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"  报告生成失败: {e}"))
            finally:
                self._generating = False

        threading.Thread(target=_gen, daemon=True, name="report-gen").start()

    # ── Export helpers ──────────────────────────────────────────

    def _get_report_dir(self):
        """Return inputs dir if exists, else None."""
        if self._output_dir and os.path.isdir(self._output_dir):
            return os.path.join(self._output_dir, "inputs")
        return None

    def _ensure_reports(self):
        """Generate reports if not yet generated, return inputs dir."""
        inputs = self._get_report_dir()
        if not inputs:
            messagebox.showinfo("提示", "没有可导出的录制项目，请先完成一次录制")
            return None
        log_file = os.path.join(inputs, f"input_log_{self._project_name}.txt")
        if not os.path.exists(log_file):
            messagebox.showinfo("提示", "未找到操作日志文件")
            return None
        # Check if HTML report exists; if not, generate all
        html_path = os.path.join(inputs, f"report_{self._project_name}.html")
        json_path = os.path.join(inputs, f"report_{self._project_name}.json")
        if not os.path.exists(html_path) or not os.path.exists(json_path):
            try:
                self._generate_reports()
            except Exception:
                pass
        return inputs

    def _export_file(self, ext: str, fmt_name: str, description: str):
        """Generic export: pick a file from inputs/ and save to user-chosen location."""
        inputs = self._ensure_reports()
        if not inputs:
            return
        src = os.path.join(inputs, f"report_{self._project_name}.{ext}")
        if not os.path.exists(src):
            # Try to generate just this format
            self._log(f"正在生成 {fmt_name} 报告...")
            try:
                self.root.config(cursor="watch")
                self.root.update()
                ss_dir = os.path.join(inputs, "screenshots")
                log_file = os.path.join(inputs, f"input_log_{self._project_name}.txt")
                from recorder.report_generator import parse_log, generate_markdown, generate_html, generate_word, generate_json
                events = parse_log(log_file)
                if ext == "md":
                    generate_markdown(events, ss_dir, src, self._project_name,
                                      os.path.join(inputs, f"{self._project_name}.mp4"))
                elif ext == "html":
                    generate_html(events, ss_dir, src, self._project_name,
                                  os.path.join(inputs, f"{self._project_name}.mp4"))
                elif ext == "docx":
                    generate_word(events, ss_dir, src, self._project_name,
                                  os.path.join(inputs, f"{self._project_name}.mp4"))
                elif ext == "json":
                    generate_json(events, ss_dir, src, self._project_name,
                                  os.path.join(inputs, f"{self._project_name}.mp4"))
                self._log(f"  {fmt_name} 报告已生成")
            except Exception as e:
                messagebox.showerror("生成失败", f"生成 {fmt_name} 报告失败:\n{e}")
                return
            finally:
                self.root.config(cursor="")

        save_path = filedialog.asksaveasfilename(
            title=f"导出 {description}",
            defaultextension=f".{ext}",
            filetypes=[(description, f"*.{ext}")],
            initialfile=f"{self._project_name}_report.{ext}",
            initialdir=os.path.dirname(self._output_dir),
        )
        if not save_path:
            return
        import shutil
        try:
            shutil.copy2(src, save_path)
            sz = os.path.getsize(save_path)
            self._log(f"导出完成  {os.path.basename(save_path)}  ({self._fmt_size(sz)})")
            os.startfile(save_path)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _open_report(self, ext: str, name: str, editor: bool = False) -> None:
        """Ensure report exists, then open it."""
        inputs = self._ensure_reports()
        if not inputs:
            return
        path = os.path.join(inputs, f"report_{self._project_name}.{ext}")
        if not os.path.exists(path):
            messagebox.showinfo("提示", f"未找到 {name} 报告文件:\n{path}")
            return
        self._log(f"打开  {os.path.basename(path)}")
        if editor:
            # Try code editor first (VS Code, then Notepad)
            for editor_cmd in ["code", "notepad"]:
                try:
                    import subprocess
                    subprocess.Popen([editor_cmd, path])
                    return
                except FileNotFoundError:
                    continue
        os.startfile(path)

    def _export_json(self):
        """Export JSON report and open it."""
        self._open_report("json", "JSON", editor=True)

    def _open_video(self):
        """Open the recorded video file."""
        if not self._output_dir:
            messagebox.showinfo("提示", "没有可用的录制项目")
            return
        video = os.path.join(self._output_dir, "inputs", f"{self._project_name}.mp4")
        if os.path.exists(video):
            self._log(f"打开  {os.path.basename(video)}")
            try:
                os.startfile(video)
            except OSError:
                messagebox.showwarning("提示", "找不到可用的视频播放器")
        else:
            messagebox.showinfo("提示", f"视频文件不存在:\n{video}")
    def _export_markdown(self):
        self._open_report("md", "Markdown", editor=True)

    def _export_html(self):
        self._open_report("html", "HTML")

    def _export_word(self):
        self._open_report("docx", "Word")

    def _export_zip(self):
        if not self._output_dir or not os.path.isdir(self._output_dir):
            messagebox.showinfo("提示", "没有可导出的录制项目，请先完成一次录制")
            return
        # Ensure reports exist before zipping
        self._ensure_reports()
        zip_path = filedialog.asksaveasfilename(
            title="导出录制工程 (ZIP)",
            defaultextension=".zip",
            filetypes=[("ZIP 压缩包", "*.zip")],
            initialfile=f"{self._project_name}.zip",
            initialdir=os.path.dirname(self._output_dir),
        )
        if not zip_path:
            return
        try:
            self._log("正在导出 ZIP...")
            self.root.config(cursor="watch")
            self.root.update()
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root_dir, dirs, files in os.walk(self._output_dir):
                    for f in files:
                        fp = os.path.join(root_dir, f)
                        zf.write(fp, os.path.relpath(fp, os.path.dirname(self._output_dir)))
            zs = os.path.getsize(zip_path)
            self._log(f"导出完成  {os.path.basename(zip_path)}  ({self._fmt_size(zs)})")
            messagebox.showinfo("导出成功", f"已导出到:\n{zip_path}\n大小: {self._fmt_size(zs)}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
        finally:
            self.root.config(cursor="")

    def _on_close(self):
        if self._recording:
            if messagebox.askyesno("确认", "正在录制中，确定要退出吗？"):
                self._stop_recording()
                self.root.destroy()
        else:
            self.root.destroy()

    # ── 工具 ─────────────────────────────────────────────────────

    @staticmethod
    def _fmt_time(s: float) -> str:
        s = int(s)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _fmt_size(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.1f} MB"

    @staticmethod
    def _open_folder(path: str):
        s = platform.system()
        if s == "Darwin":
            subprocess.Popen(["open", path])
        elif s == "Windows":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def run(self):
        self.root.mainloop()


def main():
    ScreenRecorderApp().run()


if __name__ == "__main__":
    main()
