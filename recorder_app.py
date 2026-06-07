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
    """加载并缓存 PNG 图标为 PhotoImage。"""
    _cache = {}
    _dir: Path = Path(__file__).parent / "images" / "icons_64"

    @classmethod
    def get(cls, name: str, size: int = BTN_SIZE) -> ImageTk.PhotoImage:
        key = f"{name}@{size}"
        if key not in cls._cache:
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
        self._center_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ──────────────────────────────────────────────────

    def _build_ui(self):
        self._main = tk.Frame(self.root, bg=C.BG)
        self._main.pack(fill=tk.X)

        # ═══════════════════════════════════════════════════════════
        # 按钮栏：[录制/停止] [计时器] [暂停/恢复] ... [设置][日志][目录][导出]
        # ═══════════════════════════════════════════════════════════
        toolbar = tk.Frame(self._main, bg=C.BG)
        toolbar.pack(fill=tk.X, padx=12, pady=8)

        # ─ 左区：录制/停止 + 计时器 ─
        left = tk.Frame(toolbar, bg=C.BG)
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
        self._pause_wrapper = tk.Frame(toolbar, bg=C.BG)
        self._pause_btn = Btn(self._pause_wrapper, "pause", command=self._toggle_pause, tooltip="暂停")
        self._pause_btn.pack()

        # ─ 右区：功能按钮 ─
        right = tk.Frame(toolbar, bg=C.BG)
        right.pack(side=tk.RIGHT)

        self._settings_btn = Btn(right, "settings", command=self._toggle_settings, tooltip="设置")
        self._settings_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        self._log_btn = Btn(right, "log", command=self._toggle_log, tooltip="日志")
        self._log_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        self._folder_btn = Btn(right, "folder", command=self._open_dir, tooltip="打开目录")
        self._folder_btn.pack(side=tk.LEFT, padx=(0, BTN_GAP))

        self._export_btn = Btn(right, "export", command=self._export_zip, tooltip="导出 ZIP")
        self._export_btn.pack(side=tk.LEFT)

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
        try:
            info = self._session.start()
        except Exception as e:
            messagebox.showerror("错误", f"启动录制失败:\n{e}")
            self._session = None
            return

        self._recording = True
        self._paused = False

        self._layout_recording()

        # 显示状态栏
        self._status_bar.pack(fill=tk.X, padx=12, pady=(0, 4), after=self._main.winfo_children()[0])
        self._refit()

        self._log(f"开始录制  {info.logical_width}x{info.logical_height}  @ {self._fps.get()} fps")
        self._log(f"输出目录  {self._output_dir}")

        self._hotkey = HotkeyListener(
            on_stop=lambda: self.root.after(0, self._stop_recording),
            on_pause_toggle=lambda: self.root.after(0, self._toggle_pause),
        )
        self._hotkey.start()
        self._update_status_loop()

    def _stop_recording(self):
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

        self._session = None

    def _toggle_pause(self):
        if not self._session:
            return
        if self._paused:
            self._session.resume()
            self._paused = False
            self._layout_recording()
            self._log("继续录制")
        else:
            self._session.pause()
            self._paused = True
            self._layout_paused()
            self._log("暂停录制")

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

    def _export_zip(self):
        if not self._output_dir or not os.path.isdir(self._output_dir):
            messagebox.showinfo("提示", "没有可导出的录制项目，请先完成一次录制")
            return
        zip_path = filedialog.asksaveasfilename(
            title="导出录制工程", defaultextension=".zip",
            filetypes=[("ZIP 压缩包", "*.zip")],
            initialfile=f"{self._project_name}.zip",
            initialdir=os.path.dirname(self._output_dir),
        )
        if not zip_path:
            return
        try:
            self._log("正在导出...")
            self.root.config(cursor="watch")
            self.root.update()
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root_dir, dirs, files in os.walk(self._output_dir):
                    for f in files:
                        fp = os.path.join(root_dir, f)
                        zf.write(fp, os.path.relpath(fp, os.path.dirname(self._output_dir)))
            zs = os.path.getsize(zip_path)
            self._log(f"导出完成  {zip_path}  ({self._fmt_size(zs)})")
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
