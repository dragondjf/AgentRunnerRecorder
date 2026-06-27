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
import json
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
from recorder.urc_bridge import UIRecorderCoreServer, RecordingConverter
from recorder.platform_utils import open_file, open_folder, get_app_icon, get_editor_candidates

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
        self.root.withdraw()  # 隐藏窗口，避免构建 UI 时闪烁
        self.root.title("AgentRunner Recorder")
        self.root.configure(bg=C.BG)
        self.root.resizable(False, False)

        # 应用图标（跨平台：Windows=.ico, macOS=.icns, Linux=.png）
        _icon_path = get_app_icon(Path(__file__).parent / "images")
        if _icon_path.exists() and _icon_path.suffix in (".ico", ".icns"):
            self.root.iconbitmap(str(_icon_path))
        else:
            # 回退到 PNG
            png_icon = Path(__file__).parent / "images" / "app_icon.png"
            if png_icon.exists():
                self.root.iconphoto(True, ImageTk.PhotoImage(
                    Image.open(png_icon).resize((32, 32), _RESAMPLE)
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

        # UI 控件采集相关
        self._ui_win_list: list = []       # WindowInfo 对象列表
        self._ui_win_var = tk.StringVar(value="不采集（默认）")
        self._guirunner_url = tk.StringVar(value="http://127.0.0.1:60000")
        self._ui_win_combo = None           # Combobox widget
        self._selected_ui_win = None        # 选中的 WindowInfo 或 None

        # UIRecorderCore 后台服务
        self._urc_server = UIRecorderCoreServer()
        threading.Thread(
            target=self._urc_server.start,
            daemon=True,
            name="urc-server",
        ).start()

        self._build_ui()
        self._refit()
        self._show_top_right()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.deiconify()  # 窗口已就绪，显示

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

        # ── 编辑按钮（一键跳转 UIRecorderCore） ──
        self._edit_btn = Btn(right, "edit", command=self._edit_in_urc, tooltip="在 UIRecorderCore 中编辑")
        self._edit_btn.pack(side=tk.LEFT, padx=(BTN_GAP, 0))

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

        # ═══ UI控件采集 ═══
        # 分隔线
        tk.Frame(inner_set, height=1, bg=C.BORDER).pack(fill=tk.X, pady=(14, 10))

        r2 = tk.Frame(inner_set, bg=C.SURFACE)
        r2.pack(fill=tk.X)
        tk.Label(r2, text="UI控件采集", font=("", 9, "bold"), fg=C.ACCENT2, bg=C.SURFACE).pack(anchor=tk.W)

        r2b = tk.Frame(inner_set, bg=C.SURFACE)
        r2b.pack(fill=tk.X, pady=(6, 0))
        tk.Label(r2b, text="目标进程", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)

        self._ui_win_combo = ttk.Combobox(
            r2b, textvariable=self._ui_win_var,
            values=["不采集（默认）"],
            width=36, state="readonly",
        )
        self._ui_win_combo.pack(side=tk.LEFT, padx=(8, 6))
        self._ui_win_combo.bind("<<ComboboxSelected>>", self._on_ui_win_selected)

        # 刷新按钮
        refresh_btn = tk.Button(
            r2b, text="刷新", font=("", 8),
            command=self._refresh_ui_windows,
            bg=C.SURFACE2, fg=C.TEXT, relief=tk.FLAT, bd=0,
            padx=10, pady=2, cursor="hand2",
            activebackground=C.BORDER, activeforeground=C.TEXT,
        )
        refresh_btn.pack(side=tk.LEFT)

        r2c = tk.Frame(inner_set, bg=C.SURFACE)
        r2c.pack(fill=tk.X, pady=(4, 0))
        tk.Label(
            r2c,
            text="选择目标窗口后，每次鼠标点击将自动采集该窗口的 UI 控件",
            font=("", 8), fg=C.TEXT2, bg=C.SURFACE,
        ).pack(anchor=tk.W)

        # ═══ GuiRunner 配置 ═══
        # 分隔线
        tk.Frame(inner_set, height=1, bg=C.BORDER).pack(fill=tk.X, pady=(14, 10))

        r3 = tk.Frame(inner_set, bg=C.SURFACE)
        r3.pack(fill=tk.X)
        tk.Label(r3, text="GuiRunner", font=("", 9, "bold"), fg=C.ACCENT2, bg=C.SURFACE).pack(anchor=tk.W)

        r3b = tk.Frame(inner_set, bg=C.SURFACE)
        r3b.pack(fill=tk.X, pady=(6, 0))
        tk.Label(r3b, text="服务地址", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._guirunner_entry = tk.Entry(
            r3b, textvariable=self._guirunner_url, font=("", 9),
            bg=C.SURFACE2, fg=C.TEXT, insertbackground=C.TEXT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=C.BORDER, highlightcolor=C.ACCENT2,
            width=36,
        )
        self._guirunner_entry.pack(side=tk.LEFT, padx=(8, 0), ipady=4)

        # ═══ 进程选择面板（点击录制时展开）═══
        self._picker_frame = tk.Frame(self._main, bg=C.SURFACE)
        self._picker_visible = False
        self._picker_load_job = None  # 防抖 after ID
        self._picker_gen = 0          # 版本号，丢弃过期回调

        # ─ 搜索框 ─
        picker_top = tk.Frame(self._picker_frame, bg=C.SURFACE)
        picker_top.pack(fill=tk.X, padx=14, pady=(10, 4))
        tk.Label(picker_top, text="🎯 选择目标进程（可选）", font=("", 10, "bold"),
                 fg=C.ACCENT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._picker_search_var = tk.StringVar()
        self._picker_search_entry = tk.Entry(
            picker_top, textvariable=self._picker_search_var, font=("", 9),
            bg=C.SURFACE2, fg=C.TEXT, insertbackground=C.TEXT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=C.BORDER, highlightcolor=C.ACCENT2, width=20,
        )
        self._picker_search_entry.pack(side=tk.RIGHT, padx=(8, 0), ipady=3)

        # ─ 列表 ─
        picker_body = tk.Frame(self._picker_frame, bg=C.SURFACE)
        picker_body.pack(fill=tk.BOTH, expand=True, padx=14, pady=2)
        columns = ("程序", "PID", "窗口标题")
        # 用 Frame 包裹 Treeview + 原生 Scrollbar 确保滚动条可见
        picker_list_frame = tk.Frame(picker_body, bg=C.SURFACE)
        picker_list_frame.pack(fill=tk.BOTH, expand=True)
        self._picker_tree = ttk.Treeview(picker_list_frame, columns=columns, show="headings",
                                         selectmode="browse", height=6)
        self._picker_tree.heading("程序", text="程序", anchor=tk.W)
        self._picker_tree.heading("PID", text="PID", anchor=tk.W)
        self._picker_tree.heading("窗口标题", text="窗口标题", anchor=tk.W)
        self._picker_tree.column("程序", width=100, minwidth=80)
        self._picker_tree.column("PID", width=60, minwidth=50)
        self._picker_tree.column("窗口标题", width=320, minwidth=150)
        self._picker_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # 原生 tk Scrollbar — 始终可见
        vsb = tk.Scrollbar(picker_list_frame, orient=tk.VERTICAL,
                           command=self._picker_tree.yview,
                           bg=C.SURFACE2, troughcolor=C.BG,
                           activebackground=C.BORDER,
                           bd=0, highlightthickness=0)
        self._picker_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击即选择
        self._picker_tree.bind("<Double-1>", self._on_picker_dbl_click)

        # ─ 按钮栏 ─
        picker_btn = tk.Frame(self._picker_frame, bg=C.SURFACE)
        picker_btn.pack(fill=tk.X, padx=14, pady=(6, 10))
        tk.Button(picker_btn, text="跳过（不采集控件）", font=("", 9),
                  command=self._on_picker_skip,
                  bg=C.SURFACE2, fg=C.TEXT2, relief=tk.FLAT, bd=0,
                  padx=12, pady=4, cursor="hand2",
                  activebackground=C.BORDER, activeforeground=C.TEXT,
                  ).pack(side=tk.LEFT)
        tk.Button(picker_btn, text="取消录制", font=("", 9),
                  command=self._on_picker_cancel,
                  bg=C.SURFACE2, fg=C.TEXT2, relief=tk.FLAT, bd=0,
                  padx=12, pady=4, cursor="hand2",
                  activebackground=C.BORDER, activeforeground=C.TEXT,
                  ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(picker_btn, text="✓ 选定并开始录制", font=("", 9, "bold"),
                  command=self._on_picker_confirm,
                  bg=C.ACCENT2, fg=C.WHITE, relief=tk.FLAT, bd=0,
                  padx=16, pady=4, cursor="hand2",
                  activebackground=C.ACCENT_DIM, activeforeground=C.WHITE,
                  ).pack(side=tk.RIGHT)

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

        # Treeview 暗色样式
        style.configure("Treeview",
                        background=C.SURFACE2,
                        foreground=C.TEXT,
                        fieldbackground=C.SURFACE2,
                        bordercolor=C.BORDER,
                        rowheight=24)
        style.map("Treeview",
                  background=[("selected", C.ACCENT2)],
                  foreground=[("selected", C.WHITE)])
        style.configure("Treeview.Heading",
                        background=C.BG,
                        foreground=C.TEXT2,
                        bordercolor=C.BORDER,
                        relief=tk.FLAT,
                        font=("", 9, "bold"))
        style.map("Treeview.Heading",
                  background=[("active", C.SURFACE2)],
                  foreground=[("active", C.TEXT)])

        # 垂直滚动条暗色样式
        style.configure("Vertical.TScrollbar",
                        background="#3a3a4a",
                        troughcolor=C.BG,
                        bordercolor=C.BORDER,
                        arrowcolor=C.TEXT2,
                        arrowsize=14,
                        gripcount=0,
                        relief=tk.FLAT)
        style.map("Vertical.TScrollbar",
                  background=[("active", C.BORDER)],
                  arrowcolor=[("active", C.TEXT)])

    # ── 面板折叠 ─────────────────────────────────────────────────

    def _toggle_settings(self):
        if self._settings_visible:
            self._settings_frame.pack_forget()
            self._settings_visible = False
        else:
            after = self._status_bar if self._status_bar.winfo_ismapped() else self._main.winfo_children()[0]
            self._settings_frame.pack(fill=tk.X, padx=12, pady=(0, 6), after=after)
            self._settings_visible = True
            # 先显示加载状态，异步刷新窗口列表（避免 enumerate_windows 阻塞 UI 首帧渲染）
            self._ui_win_combo["values"] = ["刷新中..."]
            self._ui_win_var.set("刷新中...")
            self._main.after(50, self._refresh_ui_windows)
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
        import recorder.history_server as hs_mod
        if not self._history_server or not self._history_server.running:
            hs_mod._guirunner_url = self._guirunner_url.get().strip()
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
                         ("zip", "ZIP", self._export_zip),
                         ("edit", "GuiRunner", self._export_guirunner)]
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
        self.root.geometry(f"500x{req_h}")

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

    def _refresh_ui_windows(self):
        """刷新可用窗口列表"""
        # 先显示加载状态（无论来自 toggle 还是刷新按钮）
        try:
            self._ui_win_combo["values"] = ["刷新中..."]
            self._ui_win_var.set("刷新中...")
            self._ui_win_combo.update_idletasks()
        except Exception:
            pass

        try:
            from recorder.ui_collector import enumerate_windows
            windows = enumerate_windows()
            # 过滤无意义窗口
            filtered = []
            for w in windows:
                name = w.name.strip()
                if not name:
                    continue
                if name in ("桌面", "任务栏", "Program Manager", "Shell_TrayWnd"):
                    continue
                filtered.append(w)

            self._ui_win_list = filtered
            values = ["不采集（默认）"] + [
                f"{w.name[:35]}... (PID:{w.pid})" if len(w.name) > 35 else f"{w.name} (PID:{w.pid})"
                for w in filtered
            ]
            self._ui_win_combo["values"] = values
            self._ui_win_var.set("不采集（默认）")
            self._selected_ui_win = None
            self._log(f"已刷新进程列表: {len(filtered)} 个可用窗口")
        except Exception as e:
            self._ui_win_combo["values"] = ["刷新失败"]
            self._ui_win_var.set("刷新失败")
            self._log(f"刷新进程列表失败: {e}")
            import traceback
            traceback.print_exc()

    def _on_ui_win_selected(self, event=None):
        """下拉框选择事件"""
        idx = self._ui_win_combo.current()
        if idx <= 0 or idx > len(self._ui_win_list):
            self._selected_ui_win = None
            self._ui_win_var.set("不采集（默认）")
        else:
            self._selected_ui_win = self._ui_win_list[idx - 1]
            win = self._selected_ui_win
            self._log(f"已选择目标进程: {win.name} (PID:{win.pid})")

    def _show_picker_panel(self):
        """展开内联进程选择面板 — 面板瞬间展示，200ms 防抖后子线程异步加载。"""
        # 取消之前等待中的加载任务（防抖）
        if self._picker_load_job:
            self.root.after_cancel(self._picker_load_job)
            self._picker_load_job = None

        # 递增版本号，之后到达的过期回调会被丢弃
        self._picker_gen += 1
        gen = self._picker_gen

        # 1. 清空列表显示"加载中"，立即展开面板
        tree = self._picker_tree
        tree.delete(*tree.get_children())
        tree.insert("", tk.END, iid="loading",
                    values=("加载中...", "", ""))

        # 清空搜索框（直接用 Entry.delete/insert 避免触发 StringVar trace）
        self._picker_search_entry.delete(0, tk.END)
        self._picker_search_entry.insert(0, "")

        after = self._settings_frame if self._settings_visible else self._toolbar
        self._picker_frame.pack(fill=tk.X, padx=12, pady=(4, 0), after=after)
        self._picker_visible = True
        self._picker_search_entry.focus_set()
        self._refit()

        # 2. 200ms 防抖后子线程加载进程列表
        self._picker_load_job = self.root.after(200, lambda: self._start_picker_load(gen))

    def _start_picker_load(self, gen: int):
        """防抖计时到期，启动子线程加载进程列表。"""
        self._picker_load_job = None
        threading.Thread(
            target=lambda: self._load_picker_data(gen),
            daemon=True, name="picker-loader"
        ).start()

    def _load_picker_data(self, gen: int):
        """子线程中获取进程列表（Win32 快速枚举），完成后切回主线程填充 Treeview。"""
        filtered = []
        try:
            from recorder.ui_collector import enumerate_windows_fast
            windows = enumerate_windows_fast()
            for w in windows:
                name = w.name.strip()
                if not name or name in ("桌面", "任务栏", "Program Manager", "Shell_TrayWnd"):
                    continue
                filtered.append(w)
        except Exception:
            pass

        # 切回主线程更新 UI（携带版本号，过期丢弃）
        self.root.after(0, lambda g=gen, f=filtered: self._populate_picker(g, f))

    def _populate_picker(self, gen: int, filtered: list):
        """在主线程中将进程列表填充到 Treeview（仅当 gen 为最新版本号时生效）。"""
        if gen != self._picker_gen:
            return  # 过期回调，丢弃

        self._picker_filtered = filtered
        tree = self._picker_tree
        tree.delete(*tree.get_children())

        # 搜索过滤回调（存为实例变量，防止 GC）
        def _rebuild(ft=""):
            tree.delete(*tree.get_children())
            ft = ft.lower() if ft else ""
            for i, w in enumerate(self._picker_filtered):
                prog = w.name.split(" - ")[0] if " - " in w.name else w.name
                if ft:
                    combined = f"{prog} {w.pid} {w.name}".lower()
                    if ft not in combined:
                        continue
                tree.insert("", tk.END, iid=str(i),
                            values=(prog[:30], w.pid, w.name))

        self._picker_rebuild = _rebuild  # 保持引用避免 GC
        _rebuild()

        # 搜索联动 — 用 Entry <KeyRelease> 代替 StringVar trace，避免 Tcl 命令失效
        try:
            self._picker_search_entry.unbind("<KeyRelease>")
        except Exception:
            pass
        self._picker_search_entry.bind("<KeyRelease>",
            lambda e: self._picker_rebuild(self._picker_search_entry.get()))

    def _hide_picker_panel(self):
        """隐藏进程选择面板。"""
        if self._picker_visible:
            self._picker_frame.pack_forget()
            self._picker_visible = False
            try:
                self._picker_search_entry.unbind("<KeyRelease>")
            except Exception:
                pass
            self._refit()

    # ── 选择面板按钮回调 ──

    def _on_picker_skip(self):
        self._selected_ui_win = None
        self._log("UI控件采集已跳过")
        self._begin_recording_after_pick()

    def _on_picker_confirm(self):
        sel = self._picker_tree.selection()
        if sel:
            idx = int(sel[0])
            self._selected_ui_win = self._picker_filtered[idx]
            self._log(f"已选择目标进程: {self._selected_ui_win.name} "
                      f"(PID:{self._selected_ui_win.pid})")
        else:
            self._selected_ui_win = None
        self._begin_recording_after_pick()

    def _on_picker_cancel(self):
        self._hide_picker_panel()

    def _on_picker_dbl_click(self, e):
        sel = self._picker_tree.selection()
        if sel:
            idx = int(sel[0])
            self._selected_ui_win = self._picker_filtered[idx]
            self._log(f"已选择目标进程: {self._selected_ui_win.name} "
                      f"(PID:{self._selected_ui_win.pid})")
            self._begin_recording_after_pick()

    def _browse_dir(self):
        d = filedialog.askdirectory(title="选择输出目录", initialdir=self._dir_var.get())
        if d:
            self._dir_var.set(d)

    def _toggle_record(self):
        if self._recording:
            self._stop_recording()
        elif self._picker_visible:
            # 进程选择面板已展开但尚未启动录制 → 收起面板
            self._hide_picker_panel()
        else:
            self._start_recording()

    def _start_recording(self):
        base_dir = self._dir_var.get().strip()
        if not base_dir:
            messagebox.showwarning("提示", "请先设置输出目录")
            return

        # 暂存 base_dir，展开进程选择面板
        self._pending_base_dir = base_dir
        self._show_picker_panel()

    def _begin_recording_after_pick(self):
        """进程选择完成后，开始录制流程。"""
        self._hide_picker_panel()

        # 如果选择了窗口，用完整 enumerate_windows() 重新匹配以获得 _ctrl + exe
        if self._selected_ui_win is not None:
            fast_win = self._selected_ui_win
            try:
                from recorder.ui_collector import enumerate_windows
                for full_win in enumerate_windows():
                    if full_win.pid == fast_win.pid and full_win.name == fast_win.name:
                        self._selected_ui_win = full_win
                        self._log(f"已解析完整窗口信息: {full_win.name} (PID:{full_win.pid})")
                        break
            except Exception:
                self._selected_ui_win = fast_win  # 回退

        base_dir = self._pending_base_dir
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._project_name = f"recording_{ts}"
        self._output_dir = os.path.join(base_dir, self._project_name)

        self._session = RecordingSession(
            project_name=self._project_name,
            output_dir=self._output_dir,
            fps=self._fps.get(),
            monitor_idx=self._monitor.get(),
            ui_win=self._selected_ui_win,
        )

        if self._selected_ui_win:
            self._log(f"UI控件采集已启用: {self._selected_ui_win.name} "
                      f"(PID:{self._selected_ui_win.pid})")

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

            # UI 控件采集统计
            if self._session._ui_stats:
                ui = self._session._ui_stats
                self._log(
                    f"UI控件采集  共 {ui['total_controls']} 个控件 |  "
                    f"{ui['captures']} 次采集 |  跳过 {ui['skipped']} 次"
                )

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
            from recorder.report_generator import parse_log, generate_markdown, generate_html, generate_word, generate_json, generate_click_icons
            try:
                events = parse_log(log_file)
                if not events:
                    self.root.after(0, lambda: self._log("  无操作事件，跳过报告生成"))
                    return

                # 1. Markdown
                md_path = os.path.join(inputs_dir, f"report_{self._project_name}.md")
                self.root.after(0, lambda: self._log("  [1/5] 正在生成 Markdown..."))
                generate_markdown(events, ss_dir, md_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [1/5] Markdown 已生成"))

                # 2. HTML
                html_path = os.path.join(inputs_dir, f"report_{self._project_name}.html")
                self.root.after(0, lambda: self._log("  [2/5] 正在生成 HTML..."))
                generate_html(events, ss_dir, html_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [2/5] HTML 已生成"))

                # 3. Word
                docx_path = os.path.join(inputs_dir, f"report_{self._project_name}.docx")
                self.root.after(0, lambda: self._log("  [3/5] 正在生成 Word..."))
                generate_word(events, ss_dir, docx_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [3/5] Word 已生成"))

                # 4. JSON
                json_path = os.path.join(inputs_dir, f"report_{self._project_name}.json")
                self.root.after(0, lambda: self._log("  [4/5] 正在生成 JSON..."))
                generate_json(events, ss_dir, json_path, self._project_name, video)
                self.root.after(0, lambda: self._log(f"  [4/5] JSON 已生成"))

                # 5. Clicked Icons（点击坐标图标自动提取）
                self.root.after(0, lambda: self._log("  [5/5] 正在提取点击图标..."))
                icons_result = generate_click_icons(inputs_dir, self._project_name)
                if icons_result and icons_result.get("ok"):
                    self.root.after(0, lambda: self._log(
                        f"  [5/5] 点击图标已生成 ({icons_result['hits']} 命中 / {icons_result['misses']} 未命中)"
                    ))
                else:
                    msg = icons_result.get("error", "无可用数据") if icons_result else "模块加载失败"
                    self.root.after(0, lambda: self._log(f"  [5/5] 点击图标: {msg}"))

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
            open_file(save_path)
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
            # Try code editor first (跨平台回退列表)
            for editor_cmd in get_editor_candidates():
                try:
                    subprocess.Popen([editor_cmd, path])
                    return
                except FileNotFoundError:
                    continue
        open_file(path)

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
                open_file(video)
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

    def _export_guirunner(self):
        """一键生成 HAR 并推送到 GuiRunner 创建脚本工程。"""
        # 1. 确保报告已生成
        inputs = self._ensure_reports()
        if not inputs:
            return

        # 2. 确保 mapping.json 存在（含 clicked_icons）
        mapping_path = os.path.join(inputs, "clicked_icons", "mapping.json")
        if not os.path.exists(mapping_path):
            self._log("正在生成点击图标和 HAR...")
            from recorder.report_generator import generate_click_icons
            result = generate_click_icons(inputs, self._project_name)
            if not result or not result.get("ok"):
                messagebox.showwarning("提示", "无法生成点击图标，请先录制")
                return

        # 3. 确保 HAR 存在
        output_dir = os.path.join(inputs, "clicked_icons")
        har_path = os.path.join(output_dir, "default.har")
        if not os.path.exists(har_path):
            from recorder.click_icon_extractor import load_report_json, generate_har, read_target_app, find_input_log
            report_json = os.path.join(inputs, f"report_{self._project_name}.json")
            if not os.path.exists(report_json):
                messagebox.showwarning("提示", "未找到 report JSON")
                return

            # 读取 mapping + target_app
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)

            input_log = find_input_log(inputs)
            target_app = read_target_app(input_log) if input_log else None

            har_path = generate_har(report_json, mapping, target_app, output_dir, self._project_name)
            if not har_path:
                messagebox.showwarning("提示", "HAR 生成失败")
                return

        # 4. 推送到 GuiRunner
        guirunner_url = self._guirunner_url.get().strip()
        self._log(f"正在推送到 GuiRunner ({guirunner_url})...")
        self.root.config(cursor="watch")
        self.root.update()
        try:
            from recorder.click_icon_extractor import push_har_to_guirunner
            ok = push_har_to_guirunner(har_path, self._project_name, base_url=guirunner_url)
            if ok:
                self._log("GuiRunner 脚本工程已创建/更新")
                messagebox.showinfo("成功", f"GuiRunner 工程 '{self._project_name}' 已推送")
            else:
                self._log("GuiRunner 推送失败（后端可能未启动）")
                messagebox.showwarning("提示", f"推送失败，请确认 GuiRunner 后端已启动\n({guirunner_url})")
        except Exception as e:
            self._log(f"GuiRunner 推送异常: {e}")
            messagebox.showerror("错误", f"推送失败:\n{e}")
        finally:
            self.root.config(cursor="")

    def _edit_in_urc(self):
        """一键编辑：转换录制 → 加载项目 → 打开浏览器。"""
        # 1. 检查是否有录制
        if not self._output_dir or not os.path.isdir(self._output_dir):
            messagebox.showinfo("提示", "没有可编辑的录制项目，请先完成一次录制")
            return

        # 2. 等待 UIRecorderCore 就绪
        if not self._urc_server.is_ready:
            self._log("等待 UIRecorderCore 服务就绪...")
            self.root.update()
            if not self._urc_server.start(wait_ready=True, timeout=15):
                messagebox.showerror("错误", "UIRecorderCore 服务启动失败")
                return

        # 3. 转换录制
        self._log("正在转换录制项目到 UIRecorderCore...")
        self.root.config(cursor="watch")
        self.root.update()
        try:
            project = RecordingConverter.convert(self._output_dir)
        except Exception as e:
            self._log(f"转换失败: {e}")
            messagebox.showerror("转换失败", str(e))
            return
        finally:
            self.root.config(cursor="")

        if not project:
            messagebox.showerror("错误", "转换失败，未找到录制数据")
            return

        # 4. 调用 URC API 加载项目
        from recorder.urc_bridge import _call_urc_api
        self._log(f"正在加载项目: {project}")
        ok = _call_urc_api("/api/v1/loadproject", {"project": project, "mode": "view"})
        if not ok:
            self._log("加载项目 API 调用失败，仍将打开编辑器")

        # 5. 打开浏览器（带 project 参数）
        import webbrowser
        import urllib.parse
        webbrowser.open(f"{self._urc_server.base_url}/?project={urllib.parse.quote(project)}")
        self._log(f"已打开 UIRecorderCore 编辑器 - 项目: {project}")

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
        open_folder(path)

    def run(self):
        self.root.mainloop()


def main():
    ScreenRecorderApp().run()


if __name__ == "__main__":
    main()
