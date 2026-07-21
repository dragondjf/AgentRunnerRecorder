"""ScreenRecorderApp — main application class for AgentRunner Recorder.

This module contains the full GUI application logic extracted from
recorder_app.py for better modularity and testability.
"""

import os
import sys
import time
import json
import threading
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from PIL import Image, ImageTk

# Import from sibling modules in recorder/ package
from recorder.theme import C, BTN_SIZE, BTN_GAP, get_resample
from recorder.ui_components import Icons, Btn
from recorder.hotkey import HotkeyListener
from recorder.core import RecordingSession
from recorder.report_generator import generate_reports
from recorder.urc_bridge import UIRecorderCoreServer, RecordingConverter
from recorder.platform_utils import open_file, open_folder, get_app_icon, get_editor_candidates

_RESAMPLE = get_resample()


class ScreenRecorderApp:
    """Main application: dark-themed screen recording toolbar.

    Button layout (left to right):
      Idle:    [record] [timer]                    [settings] [log] [folder] [export]
      Record:  [stop]   [timer] [pause]            [settings] [log] [folder] [export]
      Paused:  [stop]   [timer] [resume]           [settings] [log] [folder] [export]

    Hotkeys (while recording):
      Ctrl+Shift+F5  Stop recording
      Ctrl+Shift+F9  Pause / Resume
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window to avoid flicker during UI build
        self.root.title("AgentRunner Recorder")
        self.root.configure(bg=C.BG)
        self.root.resizable(False, False)

        # App icon (cross-platform: Windows=.ico, macOS=.icns, Linux=.png)
        _icon_path = get_app_icon(Path(__file__).parent.parent / "images")
        if _icon_path.exists() and _icon_path.suffix in (".ico", ".icns"):
            self.root.iconbitmap(str(_icon_path))
        else:
            png_icon = Path(__file__).parent.parent / "images" / "app_icon.png"
            if png_icon.exists():
                self.root.iconphoto(True, ImageTk.PhotoImage(
                    Image.open(png_icon).resize((32, 32), _RESAMPLE)
                ))

        # State
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

        # Tk variables
        self._fps = tk.IntVar(value=15)
        self._monitor = tk.IntVar(value=0)
        self._timer_var = tk.StringVar(value="00:00:00")
        self._frame_var = tk.StringVar(value="0")
        self._event_var = tk.StringVar(value="0")
        self._shot_var = tk.StringVar(value="0")
        self._video_sz_var = tk.StringVar(value="0 MB")
        self._log_sz_var = tk.StringVar(value="0 KB")

        # UI control collection related
        self._ui_win_list: list = []
        self._ui_win_var = tk.StringVar(value="不采集（默认）")
        self._guirunner_url = tk.StringVar(value="http://127.0.0.1:60000")
        self._ui_win_combo = None
        self._selected_ui_win = None

        # UIRecorderCore background service
        self._urc_server = UIRecorderCoreServer()
        threading.Thread(target=self._urc_server.start, daemon=True, name="urc-server").start()

        self._build_ui()
        self._refit()
        self._show_top_right()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.deiconify()
        # 处理用户用系统按钮最小化/恢复的场景：恢复时强制重排
        self.root.bind("<Map>", lambda e: self.root.after(50, self._refit))

    # ── UI Build ──────────────────────────────────────────────

    def _build_ui(self):
        self._main = tk.Frame(self.root, bg=C.BG)
        self._main.pack(fill=tk.X)

        # Toolbar
        self._toolbar = tk.Frame(self._main, bg=C.BG)
        self._toolbar.pack(fill=tk.X, padx=12, pady=8)

        left = tk.Frame(self._toolbar, bg=C.BG)
        left.pack(side=tk.LEFT)

        self._record_btn = Btn(left, "record", command=self._toggle_record, tooltip="开始录制")
        self._record_btn.pack(side=tk.LEFT)

        self._timer_lbl = tk.Label(left, textvariable=self._timer_var,
                                   font=("Consolas", 20, "bold"), fg=C.TEXT, bg=C.BG)
        self._timer_lbl.pack(side=tk.LEFT, padx=(14, 0))

        self._pause_wrapper = tk.Frame(self._toolbar, bg=C.BG)
        self._pause_btn = Btn(self._pause_wrapper, "pause", command=self._toggle_pause, tooltip="暂停")
        self._pause_btn.pack()

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

        self._export_menu_open = False
        self._export_btn = tk.Button(right, image=Icons.get("export", 32),
                                     command=self._toggle_export_menu, bg=C.BG,
                                     activebackground=C.SURFACE2, bd=0, cursor="hand2",
                                     width=32, height=32)
        self._export_btn.pack(side=tk.LEFT)
        self._export_btn.bind("<Enter>", lambda e: self._export_btn.configure(bg=C.SURFACE2))
        self._export_btn.bind("<Leave>", lambda e: self._export_btn.configure(bg=C.BG))
        self._export_panel = None

        self._edit_btn = Btn(right, "edit", command=self._edit_in_urc,
                             tooltip="在 UIRecorderCore 中编辑")
        self._edit_btn.pack(side=tk.LEFT, padx=(BTN_GAP, 0))

        # Status bar
        self._status_bar = tk.Frame(self._main, bg=C.SURFACE)
        inner_s = tk.Frame(self._status_bar, bg=C.SURFACE)
        inner_s.pack(fill=tk.X, padx=12, pady=(6, 8))

        for label, var in [("帧", self._frame_var), ("事件", self._event_var),
                           ("截图", self._shot_var), ("视频", self._video_sz_var),
                           ("日志", self._log_sz_var)]:
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

        # Settings panel
        self._settings_frame = tk.Frame(self._main, bg=C.SURFACE)
        inner_set = tk.Frame(self._settings_frame, bg=C.SURFACE)
        inner_set.pack(fill=tk.X, padx=16, pady=12)

        r0 = tk.Frame(inner_set, bg=C.SURFACE); r0.pack(fill=tk.X, pady=(0, 8))
        tk.Label(r0, text="帧率", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._fps_cb = ttk.Combobox(r0, textvariable=self._fps, values=[10,15,20,25,30],
                                    width=4, state="readonly")
        self._fps_cb.pack(side=tk.LEFT, padx=(8, 24))
        tk.Label(r0, text="显示器", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._mon_cb = ttk.Combobox(r0, textvariable=self._monitor, values=[0,1,2],
                                    width=4, state="readonly")
        self._mon_cb.pack(side=tk.LEFT, padx=(8, 0))

        r1 = tk.Frame(inner_set, bg=C.SURFACE); r1.pack(fill=tk.X)
        tk.Label(r1, text="输出目录", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(anchor=tk.W)
        r1b = tk.Frame(r1, bg=C.SURFACE); r1b.pack(fill=tk.X, pady=(4, 0))
        default_dir = str(Path.home() / "Videos" / "ScreenRecordings")
        self._dir_var = tk.StringVar(value=default_dir)
        self._dir_entry = tk.Entry(r1b, textvariable=self._dir_var, font=("", 9),
                                   bg=C.SURFACE2, fg=C.TEXT, insertbackground=C.TEXT,
                                   relief=tk.FLAT, bd=0, highlightthickness=1,
                                   highlightbackground=C.BORDER, highlightcolor=C.ACCENT2)
        self._dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        tk.Button(r1b, text="浏览", font=("", 9), command=self._browse_dir,
                  bg=C.SURFACE2, fg=C.TEXT, relief=tk.FLAT, bd=0,
                  padx=12, pady=3, cursor="hand2",
                  activebackground=C.BORDER, activeforeground=C.TEXT).pack(side=tk.LEFT, padx=(6, 0))

        # UI control collection
        tk.Frame(inner_set, height=1, bg=C.BORDER).pack(fill=tk.X, pady=(14, 10))
        r2 = tk.Frame(inner_set, bg=C.SURFACE); r2.pack(fill=tk.X)
        tk.Label(r2, text="UI控件采集", font=("", 9, "bold"),
                 fg=C.ACCENT2, bg=C.SURFACE).pack(anchor=tk.W)
        r2b = tk.Frame(inner_set, bg=C.SURFACE); r2b.pack(fill=tk.X, pady=(6, 0))
        tk.Label(r2b, text="目标进程", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._ui_win_combo = ttk.Combobox(r2b, textvariable=self._ui_win_var,
                                           values=["不采集（默认）"],
                                           width=36, state="readonly")
        self._ui_win_combo.pack(side=tk.LEFT, padx=(8, 6))
        self._ui_win_combo.bind("<<ComboboxSelected>>", self._on_ui_win_selected)
        refresh_btn = tk.Button(r2b, text="刷新", font=("", 8),
                                command=self._refresh_ui_windows,
                                bg=C.SURFACE2, fg=C.TEXT, relief=tk.FLAT, bd=0,
                                padx=10, pady=2, cursor="hand2",
                                activebackground=C.BORDER, activeforeground=C.TEXT)
        refresh_btn.pack(side=tk.LEFT)

        r2c = tk.Frame(inner_set, bg=C.SURFACE); r2c.pack(fill=tk.X, pady=(4, 0))
        tk.Label(r2c, text="选择目标窗口后，每次鼠标点击将自动采集该窗口的 UI 控件",
                 font=("", 8), fg=C.TEXT2, bg=C.SURFACE).pack(anchor=tk.W)

        # GuiRunner config
        tk.Frame(inner_set, height=1, bg=C.BORDER).pack(fill=tk.X, pady=(14, 10))
        r3 = tk.Frame(inner_set, bg=C.SURFACE); r3.pack(fill=tk.X)
        tk.Label(r3, text="GuiRunner", font=("", 9, "bold"), fg=C.ACCENT2, bg=C.SURFACE).pack(anchor=tk.W)
        r3b = tk.Frame(inner_set, bg=C.SURFACE); r3b.pack(fill=tk.X, pady=(6, 0))
        tk.Label(r3b, text="服务地址", font=("", 9), fg=C.TEXT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._guirunner_entry = tk.Entry(r3b, textvariable=self._guirunner_url, font=("", 9),
                                         bg=C.SURFACE2, fg=C.TEXT, insertbackground=C.TEXT,
                                         relief=tk.FLAT, bd=0, highlightthickness=1,
                                         highlightbackground=C.BORDER, highlightcolor=C.ACCENT2, width=36)
        self._guirunner_entry.pack(side=tk.LEFT, padx=(8, 0), ipady=4)

        # Process picker panel
        self._picker_frame = tk.Frame(self._main, bg=C.SURFACE)
        self._picker_visible = False
        self._picker_load_job = None
        self._picker_gen = 0

        picker_top = tk.Frame(self._picker_frame, bg=C.SURFACE)
        picker_top.pack(fill=tk.X, padx=14, pady=(10, 4))
        tk.Label(picker_top, text="\U0001f3af 选择目标进程（可选）",
                 font=("", 10, "bold"), fg=C.ACCENT2, bg=C.SURFACE).pack(side=tk.LEFT)
        self._picker_search_var = tk.StringVar()
        self._picker_search_entry = tk.Entry(picker_top, textvariable=self._picker_search_var, font=("", 9),
                                            bg=C.SURFACE2, fg=C.TEXT, insertbackground=C.TEXT,
                                            relief=tk.FLAT, bd=0, highlightthickness=1,
                                            highlightbackground=C.BORDER, highlightcolor=C.ACCENT2, width=20)
        self._picker_search_entry.pack(side=tk.RIGHT, padx=(8, 0), ipady=3)

        picker_body = tk.Frame(self._picker_frame, bg=C.SURFACE)
        picker_body.pack(fill=tk.BOTH, expand=True, padx=14, pady=2)
        columns = ("程序", "PID", "窗口标题")
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
        vsb = tk.Scrollbar(picker_list_frame, orient=tk.VERTICAL,
                           command=self._picker_tree.yview,
                           bg=C.SURFACE2, troughcolor=C.BG,
                           activebackground=C.BORDER, bd=0, highlightthickness=0)
        self._picker_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._picker_tree.bind("<Double-1>", self._on_picker_dbl_click)

        picker_btn = tk.Frame(self._picker_frame, bg=C.SURFACE)
        picker_btn.pack(fill=tk.X, padx=14, pady=(6, 10))
        tk.Button(picker_btn, text="跳过（不采集控件）", font=("", 9),
                  command=self._on_picker_skip, bg=C.SURFACE2, fg=C.TEXT2,
                  relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2",
                  activebackground=C.BORDER, activeforeground=C.TEXT).pack(side=tk.LEFT)
        tk.Button(picker_btn, text="取消录制", font=("", 9),
                  command=self._on_picker_cancel, bg=C.SURFACE2, fg=C.TEXT2,
                  relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2",
                  activebackground=C.BORDER, activeforeground=C.TEXT).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(picker_btn, text="✓ 选定并开始录制", font=("", 9, "bold"),
                  command=self._on_picker_confirm, bg=C.ACCENT2, fg=C.WHITE,
                  relief=tk.FLAT, bd=0, padx=16, pady=4, cursor="hand2",
                  activebackground=C.ACCENT_DIM, activeforeground=C.WHITE).pack(side=tk.RIGHT)

        # Log panel
        self._log_frame = tk.Frame(self._main, bg=C.SURFACE)
        inner_log = tk.Frame(self._log_frame, bg=C.SURFACE)
        inner_log.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        self._log_widget = tk.Text(inner_log, height=8, wrap=tk.WORD, state=tk.DISABLED,
                                  font=("Consolas", 9), bg=C.BG, fg=C.TEXT2,
                                  insertbackground=C.TEXT, relief=tk.FLAT, bd=0,
                                  highlightthickness=0, padx=8, pady=6)
        self._log_widget.pack(fill=tk.BOTH, expand=True)
        self._style_ttk()

    def _style_ttk(self):
        style = ttk.Style(); style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=C.SURFACE2, background=C.SURFACE2,
                        foreground=C.TEXT, arrowcolor=C.TEXT,
                        selectbackground=C.ACCENT2, selectforeground=C.WHITE,
                        bordercolor=C.BORDER, darkcolor=C.SURFACE2,
                        lightcolor=C.SURFACE2, relief=tk.FLAT)
        style.map("TCombobox", fieldbackground=[("readonly", C.SURFACE2)],
                  foreground=[("readonly", C.TEXT)])
        style.configure("Treeview", background=C.SURFACE2, foreground=C.TEXT,
                        fieldbackground=C.SURFACE2, bordercolor=C.BORDER, rowheight=24)
        style.map("Treeview", background=[("selected", C.ACCENT2)],
                  foreground=[("selected", C.WHITE)])
        style.configure("Treeview.Heading", background=C.BG, foreground=C.TEXT2,
                        bordercolor=C.BORDER, relief=tk.FLAT, font=("", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", C.SURFACE2)],
                  foreground=[("active", C.TEXT)])
        style.configure("Vertical.TScrollbar", background="#3a3a4a", troughcolor=C.BG,
                        bordercolor=C.BORDER, arrowcolor=C.TEXT2, arrowsize=14,
                        gripcount=0, relief=tk.FLAT)
        style.map("Vertical.TScrollbar", background=[("active", C.BORDER)],
                  arrowcolor=[("active", C.TEXT)])

    # ── Panel toggles ───────────────────────────────────────────

    def _toggle_settings(self):
        if self._settings_visible:
            self._settings_frame.pack_forget()
            self._settings_visible = False
        else:
            after = self._status_bar if self._status_bar.winfo_ismapped() else self._main.winfo_children()[0]
            self._settings_frame.pack(fill=tk.X, padx=12, pady=(0, 6), after=after)
            self._settings_visible = True
            self._ui_win_combo["values"] = ["刷新中..."]
            self._ui_win_var.set("刷新中...")
            self._main.after(50, self._refresh_ui_windows)
        self._refit()

    def _toggle_log(self):
        if self._log_visible:
            self._log_frame.pack_forget()
            self._log_visible = False
        else:
            after = (self._settings_frame if self._settings_visible else
                     (self._status_bar if self._status_bar.winfo_ismapped() else self._main.winfo_children()[0]))
            self._log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8), after=after)
            self._log_visible = True
        self._refit()

    def _open_history(self):
        import urllib.request; import webbrowser
        guirunner_url = self._guirunner_url.get().strip()
        try:
            req = urllib.request.Request(f"{self._urc_server.base_url}/history/api/guirunner-url",
                                        data=json.dumps({"url": guirunner_url}).encode(),
                                        headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass
        webbrowser.open(f"{self._urc_server.base_url}/history/")

    def _toggle_export_menu(self):
        if self._export_menu_open:
            if self._export_panel: self._export_panel.pack_forget()
            self._export_menu_open = False
        else:
            if self._export_panel is None:
                self._export_panel = tk.Frame(self._main, bg=C.SURFACE2, highlightthickness=0)
                items = [("video", "Video", self._open_video), ("md", "Markdown", self._export_markdown),
                         ("json", "JSON", self._export_json), ("html", "HTML", self._export_html),
                         ("word", "Word", self._export_word), ("zip", "ZIP", self._export_zip),
                         ("edit", "GuiRunner", self._export_guirunner)]
                for i in range(0, len(items), 3):
                    row = tk.Frame(self._export_panel, bg=C.SURFACE2)
                    row.pack(anchor="center", pady=4)
                    for icon, label, cmd in items[i:i+3]:
                        tk.Button(row, text=f" {label} ", image=Icons.get(icon, 24),
                                  compound=tk.LEFT, command=cmd, font=("", 9), fg=C.TEXT, bg=C.BG,
                                  activebackground=C.ACCENT2, activeforeground="white",
                                  bd=0, padx=8, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=4, pady=2)
            self._export_panel.pack(fill=tk.X, after=self._toolbar)
            self._export_menu_open = True
        self._refit()

    def _show_top_right(self):
        self.root.deiconify(); self.root.update_idletasks()
        sw = self.root.winfo_screenwidth(); ww = self.root.winfo_width()
        self.root.geometry(f"+{sw - ww - 20}+20")

    def _refit(self):
        self.root.update_idletasks(); self._main.update_idletasks()
        self.root.geometry(f"500x{self._main.winfo_reqheight()}")

    def _center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    # ── Layout states ──────────────────────────────────────────

    def _layout_idle(self):
        self._record_btn.set_icon("record"); self._record_btn._tooltip_text = "开始录制"
        self._pause_wrapper.pack_forget()

    def _layout_recording(self):
        self._record_btn.set_icon("stop"); self._record_btn._tooltip_text = "停止录制"
        self._pause_btn.set_icon("pause"); self._pause_btn._tooltip_text = "暂停"
        self._pause_wrapper.pack(side=tk.LEFT, padx=(10, 0), after=self._timer_lbl.master)

    def _layout_paused(self):
        self._pause_btn.set_icon("resume"); self._pause_btn._tooltip_text = "继续录制"

    # ── Logging ────────────────────────────────────────────────

    def _log(self, msg: str):
        self._log_widget.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.insert(tk.END, f"[{ts}] {msg}\n"); self._log_widget.see(tk.END)
        self._log_widget.configure(state=tk.DISABLED)

    # ── Recording operations ───────────────────────────────────

    def _refresh_ui_windows(self):
        """后台线程执行 enumerate_windows，避免阻塞 GUI。"""
        try:
            self._ui_win_combo["values"] = ["刷新中..."]
            self._ui_win_var.set("刷新中..."); self._ui_win_combo.update_idletasks()
        except Exception:
            pass
        threading.Thread(target=self._refresh_ui_windows_async, daemon=True).start()

    def _refresh_ui_windows_async(self):
        """在后台线程中执行 enumerate_windows。"""
        try:
            from recorder.ui_collector import enumerate_windows
            windows = enumerate_windows(); filtered = []
            for w in windows:
                name = w.name.strip()
                if not name or name in ("桌面", "任务栏", "Program Manager", "Shell_TrayWnd"):
                    continue
                filtered.append(w)
            self._ui_win_list = filtered
            values = ["不采集（默认）"] + [
                f"{w.name[:35]}... (PID:{w.pid})" if len(w.name) > 35 else f"{w.name} (PID:{w.pid})"
                for w in filtered]
            self.root.after(0, self._refresh_ui_windows_done, values, len(filtered))
        except Exception as e:
            self.root.after(0, self._refresh_ui_windows_failed, str(e))

    def _refresh_ui_windows_done(self, values, count):
        """主线程回调：更新下拉列表。"""
        self._ui_win_combo["values"] = values
        self._ui_win_var.set("不采集（默认）")
        self._selected_ui_win = None
        self._log(f"已刷新进程列表: {count} 个可用窗口")

    def _refresh_ui_windows_failed(self, err_msg):
        """主线程回调：刷新失败。"""
        self._ui_win_combo["values"] = ["刷新失败"]
        self._ui_win_var.set("刷新失败")
        self._log(f"刷新进程列表失败: {err_msg}")
    def _on_ui_win_selected(self, event=None):
        idx = self._ui_win_combo.current()
        if idx <= 0 or idx > len(self._ui_win_list):
            self._selected_ui_win = None; self._ui_win_var.set("不采集（默认）")
        else:
            self._selected_ui_win = self._ui_win_list[idx-1]
            win = self._selected_ui_win; self._log(f"已选择目标进程: {win.name} (PID:{win.pid})")

    def _show_picker_panel(self):
        if self._picker_load_job:
            self.root.after_cancel(self._picker_load_job); self._picker_load_job = None
        self._picker_gen += 1; gen = self._picker_gen
        tree = self._picker_tree; tree.delete(*tree.get_children())
        tree.insert("", tk.END, iid="loading", values=("加载中...", "", ""))
        self._picker_search_entry.delete(0, tk.END); self._picker_search_entry.insert(0, "")
        after = self._settings_frame if self._settings_visible else self._toolbar
        self._picker_frame.pack(fill=tk.X, padx=12, pady=(4, 0), after=after)
        self._picker_visible = True; self._picker_search_entry.focus_set(); self._refit()
        self._picker_load_job = self.root.after(200, lambda: self._start_picker_load(gen))

    def _start_picker_load(self, gen: int):
        self._picker_load_job = None
        threading.Thread(target=lambda: self._load_picker_data(gen), daemon=True, name="picker-loader").start()

    def _load_picker_data(self, gen: int):
        filtered = []
        try:
            from recorder.ui_collector import enumerate_windows_fast
            for w in enumerate_windows_fast():
                name = w.name.strip()
                if not name or name in ("桌面", "任务栏", "Program Manager", "Shell_TrayWnd"):
                    continue
                filtered.append(w)
        except Exception:
            pass
        self.root.after(0, lambda g=gen, f=filtered: self._populate_picker(g, f))

    def _populate_picker(self, gen: int, filtered: list):
        if gen != self._picker_gen:
            return
        self._picker_filtered = filtered; tree = self._picker_tree; tree.delete(*tree.get_children())
        def _rebuild(ft=""):
            tree.delete(*tree.get_children()); ft = ft.lower() if ft else ""
            for i, w in enumerate(self._picker_filtered):
                prog = w.name.split(" - ")[0] if " - " in w.name else w.name
                if ft and f"{prog} {w.pid} {w.name}".lower().find(ft) < 0:
                    continue
                tree.insert("", tk.END, iid=str(i), values=(prog[:30], w.pid, w.name))
        self._picker_rebuild = _rebuild; _rebuild()
        try: self._picker_search_entry.unbind("<KeyRelease>")
        except Exception: pass
        self._picker_search_entry.bind("<KeyRelease>", lambda e: self._picker_rebuild(self._picker_search_entry.get()))

    def _hide_picker_panel(self):
        if self._picker_visible:
            self._picker_frame.pack_forget(); self._picker_visible = False
            try: self._picker_search_entry.unbind("<KeyRelease>")
            except Exception: pass
            self._refit()

    def _on_picker_skip(self):
        self._selected_ui_win = None; self._log("UI控件采集已跳过"); self._begin_recording_after_pick()

    def _on_picker_confirm(self):
        sel = self._picker_tree.selection()
        if sel:
            idx = int(sel[0]); self._selected_ui_win = self._picker_filtered[idx]
            self._log(f"已选择目标进程: {self._selected_ui_win.name} (PID:{self._selected_ui_win.pid})")
        else:
            self._selected_ui_win = None
        self._begin_recording_after_pick()

    def _on_picker_cancel(self): self._hide_picker_panel()

    def _on_picker_dbl_click(self, e):
        sel = self._picker_tree.selection()
        if sel:
            idx = int(sel[0]); self._selected_ui_win = self._picker_filtered[idx]
            self._log(f"已选择目标进程: {self._selected_ui_win.name} (PID:{self._selected_ui_win.pid})")
            self._begin_recording_after_pick()

    def _browse_dir(self):
        d = filedialog.askdirectory(title="选择输出目录", initialdir=self._dir_var.get())
        if d: self._dir_var.set(d)

    def _toggle_record(self):
        if self._recording: self._stop_recording()
        elif self._picker_visible: self._hide_picker_panel()
        else: self._start_recording()

    def _start_recording(self):
        base_dir = self._dir_var.get().strip()
        if not base_dir: messagebox.showwarning("提示", "请先设置输出目录"); return
        self._pending_base_dir = base_dir; self._show_picker_panel()

    def _begin_recording_after_pick(self):
        self._hide_picker_panel()
        # 将耗时操作（enumerate_windows）移到后台线程，避免阻塞 GUI 主线程
        threading.Thread(target=self._resolve_and_prepare_recording, daemon=True, name="recording-prep").start()

    def _resolve_and_prepare_recording(self):
        """后台线程：解析完整窗口信息并准备录制会话。"""
        if self._selected_ui_win is not None:
            fast_win = self._selected_ui_win
            try:
                from recorder.ui_collector import enumerate_windows
                for full_win in enumerate_windows():
                    if full_win.pid == fast_win.pid and full_win.name == fast_win.name:
                        self._selected_ui_win = full_win
                        break
            except Exception:
                self._selected_ui_win = fast_win
        # 回到主线程继续 GUI 操作
        self.root.after(0, self._prepare_countdown)

    def _prepare_countdown(self):
        """主线程：设置录制状态并启动倒计时。"""
        if self._selected_ui_win:
            self._log(f"已解析完整窗口信息: {self._selected_ui_win.name} (PID:{self._selected_ui_win.pid})")
        base_dir = self._pending_base_dir
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._project_name = f"recording_{ts}"
        self._output_dir = os.path.join(base_dir, self._project_name)
        self._session = RecordingSession(project_name=self._project_name, output_dir=self._output_dir,
                                          fps=self._fps.get(), monitor_idx=self._monitor.get(), ui_win=self._selected_ui_win)
        if self._selected_ui_win:
            self._log(f"UI控件采集已启用: {self._selected_ui_win.name} (PID:{self._selected_ui_win.pid})")
        self._recording = True; self._paused = False; self._countdown = 5
        self._layout_recording()
        self._status_bar.pack(fill=tk.X, padx=12, pady=(0, 4), after=self._toolbar); self._refit()
        self._log(f"录制将在 5 秒后开始...")
        self._log(f"输出目录  {self._output_dir}")
        self._timer_var.set(f"0{self._countdown}:00")
        self._hotkey = HotkeyListener(on_stop=lambda: self.root.after(0, self._stop_recording),
                                      on_pause_toggle=lambda: self.root.after(0, self._cancel_countdown_or_stop))
        self._hotkey.start(); self._countdown_loop()

    def _countdown_loop(self):
        if not self._recording: return
        if self._countdown > 0:
            self._timer_var.set(f"0{self._countdown}:00"); self._countdown -= 1
            self._countdown_job = self.root.after(1000, self._countdown_loop)
        else: self._begin_capture()

    def _begin_capture(self):
        # 将 session.start()（内部阻塞等待首帧）移到后台线程，避免冻结 GUI
        threading.Thread(target=self._begin_capture_async, daemon=True, name="capture-starter").start()

    def _begin_capture_async(self):
        """后台线程：启动录屏捕获（ScreenCapture.start 会阻塞等待首帧）。"""
        try:
            info = self._session.start()
        except Exception as e:
            self.root.after(0, lambda: self._on_capture_failed(e))
            return
        self.root.after(0, lambda i=info: self._on_capture_started(i))

    def _on_capture_failed(self, e):
        """主线程：处理启动录制失败。"""
        messagebox.showerror("错误", f"启动录制失败:\n{e}")
        self._session = None; self._recording = False; self._layout_idle()
        self._status_bar.pack_forget(); self._refit()

    def _on_capture_started(self, info):
        """主线程：录屏已成功启动，进入录制状态。"""
        self._log(f"开始录制  {info.logical_width}x{info.logical_height}  @ {self._fps.get()} fps")
        self.root.iconify(); self._update_status_loop()

    def _cancel_countdown_or_stop(self):
        if self._countdown > 0:
            if hasattr(self, '_countdown_job') and self._countdown_job:
                self.root.after_cancel(self._countdown_job); self._countdown_job = None
            self._recording = False
            if self._hotkey: self._hotkey.stop(); self._hotkey = None
            self._session = None; self._layout_idle(); self._status_bar.pack_forget(); self._refit()
            self._log("已取消录制")
        else: self._stop_recording()

    def _stop_recording(self):
        self._show_top_right()
        if self._countdown_job: self.root.after_cancel(self._countdown_job); self._countdown_job = None
        if self._hotkey: self._hotkey.stop(); self._hotkey = None
        if self._session: self._session.stop()
        self._recording = False; self._paused = False
        if self._update_job: self.root.after_cancel(self._update_job); self._update_job = None
        self._countdown = 0; self._countdown_job = None
        self._layout_idle(); self._status_bar.pack_forget(); self._refit()
        # 强制多帧刷新以修正 iconify 后的几何缓存
        self.root.after(50, self._refit)
        if self._session:
            stats = self._session.stats()
            self._log(f"录制完成  时长 {self._fmt_time(stats.duration_s)}  |  "
                      f"{stats.event_count} 事件  |  {stats.screenshot_count} 截图  |  "
                      f"视频 {self._fmt_size(stats.video_size)}  |  日志 {self._fmt_size(stats.log_size)}")
            self._timer_var.set(self._fmt_time(stats.duration_s)); self._event_var.set(str(stats.event_count))
            self._shot_var.set(str(stats.screenshot_count)); self._video_sz_var.set(self._fmt_size(stats.video_size))
            self._log_sz_var.set(self._fmt_size(stats.log_size))
            if self._session._ui_stats:
                ui = self._session._ui_stats
                self._log(f"UI控件采集  共 {ui['total_controls']} 个控件 |  "
                          f"{ui['captures']} 次采集 |  跳过 {ui['skipped']} 次")
            self._generate_reports()
        self._session = None

    def _toggle_pause(self):
        if not self._session: return
        if self._paused:
            self._session.resume(); self._paused = False; self._layout_recording()
            self._log("继续录制"); self.root.after(500, lambda: self.root.iconify())
        else:
            self._session.pause(); self._paused = True; self._layout_paused()
            self._log("暂停录制"); self.root.deiconify(); self.root.lift()
            # 恢复后强制重排，避免 DPI/最小化/恢复后布局错位
            self.root.after(50, self._refit)

    def _update_status_loop(self):
        if not self._recording or not self._session: return
        dur = time.monotonic() - self._session.start_monotonic() if self._session.start_monotonic() else 0
        self._timer_var.set(self._fmt_time(dur)); self._event_var.set(str(self._session.event_count()))
        self._shot_var.set(str(self._session.screenshot_count()))
        if self._session._capture: self._frame_var.set(str(self._session._capture.frame_count))
        inputs = Path(self._output_dir) / "inputs"
        vp = inputs / f"{self._project_name}.mp4"; lp = inputs / f"input_log_{self._project_name}.txt"
        self._video_sz_var.set(self._fmt_size(vp.stat().st_size if vp.exists() else 0))
        self._log_sz_var.set(self._fmt_size(lp.stat().st_size if lp.exists() else 0))
        self._update_job = self.root.after(500, self._update_status_loop)

    # ── File operations ────────────────────────────────────────

    def _open_dir(self):
        target = self._output_dir if (self._output_dir and os.path.isdir(self._output_dir)) else self._dir_var.get()
        if target and os.path.isdir(target):
            self._open_folder(target); self._log(f"打开目录  {target}")
        else: messagebox.showinfo("提示", "输出目录尚不存在，请先录制一次")

    def _generate_reports(self):
        inputs_dir = os.path.join(self._output_dir, "inputs")
        log_file = os.path.join(inputs_dir, f"input_log_{self._project_name}.txt")
        ss_dir = os.path.join(inputs_dir, "screenshots")
        if not os.path.exists(log_file): return
        video = os.path.join(inputs_dir, f"{self._project_name}.mp4")
        self._log("正在生成操作报告（后台）..."); self._generating = True
        def _gen():
            from recorder.report_generator import parse_log, generate_markdown, generate_html, generate_word, generate_json, generate_click_icons
            try:
                events = parse_log(log_file)
                if not events:
                    self.root.after(0, lambda: self._log("  无操作事件，跳过报告生成")); return
                md_path = os.path.join(inputs_dir, f"report_{self._project_name}.md")
                self.root.after(0, lambda: self._log("  [1/5] 正在生成 Markdown..."))
                generate_markdown(events, ss_dir, md_path, self._project_name, video)
                self.root.after(0, lambda: self._log("  [1/5] Markdown 已生成"))
                html_path = os.path.join(inputs_dir, f"report_{self._project_name}.html")
                self.root.after(0, lambda: self._log("  [2/5] 正在生成 HTML..."))
                generate_html(events, ss_dir, html_path, self._project_name, video)
                self.root.after(0, lambda: self._log("  [2/5] HTML 已生成"))
                docx_path = os.path.join(inputs_dir, f"report_{self._project_name}.docx")
                self.root.after(0, lambda: self._log("  [3/5] 正在生成 Word..."))
                generate_word(events, ss_dir, docx_path, self._project_name, video)
                self.root.after(0, lambda: self._log("  [3/5] Word 已生成"))
                json_path = os.path.join(inputs_dir, f"report_{self._project_name}.json")
                self.root.after(0, lambda: self._log("  [4/5] 正在生成 JSON..."))
                generate_json(events, ss_dir, json_path, self._project_name, video)
                self.root.after(0, lambda: self._log("  [4/5] JSON 已生成"))
                self.root.after(0, lambda: self._log("  [5/5] 正在提取点击图标..."))
                icons_result = generate_click_icons(inputs_dir, self._project_name)
                if icons_result and icons_result.get("ok"):
                    self.root.after(0, lambda: self._log(
                        f"  [5/5] 点击图标已生成 ({icons_result['hits']} 命中 / {icons_result['misses']} 未命中)"))
                else:
                    msg = icons_result.get("error", "无可用数据") if icons_result else "模块加载失败"
                    self.root.after(0, lambda: self._log(f"  [5/5] 点击图标: {msg}"))
                self.root.after(0, lambda: self._log("所有报告生成完成"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"  报告生成失败: {e}"))
            finally: self._generating = False
        threading.Thread(target=_gen, daemon=True, name="report-gen").start()

    # ── Export helpers ─────────────────────────────────────────

    def _get_report_dir(self):
        if self._output_dir and os.path.isdir(self._output_dir): return os.path.join(self._output_dir, "inputs")
        return None

    def _ensure_reports(self):
        inputs = self._get_report_dir()
        if not inputs: messagebox.showinfo("提示", "没有可导出的录制项目，请先完成一次录制"); return None
        log_file = os.path.join(inputs, f"input_log_{self._project_name}.txt")
        if not os.path.exists(log_file): messagebox.showinfo("提示", "札找到操作日志文件"); return None
        html_path = os.path.join(inputs, f"report_{self._project_name}.html")
        json_path = os.path.join(inputs, f"report_{self._project_name}.json")
        if not os.path.exists(html_path) or not os.path.exists(json_path):
            try: self._generate_reports()
            except Exception: pass
        return inputs

    def _export_file(self, ext: str, fmt_name: str, description: str):
        inputs = self._ensure_reports()
        if not inputs: return
        src = os.path.join(inputs, f"report_{self._project_name}.{ext}")
        if not os.path.exists(src):
            self._log(f"正在生成 {fmt_name} 报告...")
            try:
                self.root.config(cursor="watch"); self.root.update()
                ss_dir = os.path.join(inputs, "screenshots")
                log_file = os.path.join(inputs, f"input_log_{self._project_name}.txt")
                from recorder.report_generator import parse_log, generate_markdown, generate_html, generate_word, generate_json
                events = parse_log(log_file)
                {"md": generate_markdown, "html": generate_html, "docx": generate_word, "json": generate_json}[ext](
                    events, ss_dir, src, self._project_name, os.path.join(inputs, f"{self._project_name}.mp4"))
                self._log(f"  {fmt_name} 报告已生成")
            except Exception as e:
                messagebox.showerror("生成失败", f"生成 {fmt_name} 报告失败:\n{e}"); return
            finally: self.root.config(cursor="")
        save_path = filedialog.asksaveasfilename(title=f"导出 {description}", defaultextension=f".{ext}",
                                                filetypes=[(description, f"*.{ext}")],
                                                initialfile=f"{self._project_name}_report.{ext}",
                                                initialdir=os.path.dirname(self._output_dir))
        if not save_path: return
        import shutil
        try:
            shutil.copy2(src, save_path); sz = os.path.getsize(save_path)
            self._log(f"导出完成  {os.path.basename(save_path)}  ({self._fmt_size(sz)})"); open_file(save_path)
        except Exception as e: messagebox.showerror("导出失败", str(e))

    def _open_report(self, ext: str, name: str, editor: bool=False) -> None:
        inputs = self._ensure_reports()
        if not inputs: return
        path = os.path.join(inputs, f"report_{self._project_name}.{ext}")
        if not os.path.exists(path): messagebox.showinfo("提示", f"札找到 {name} 报告文件:\n{path}"); return
        self._log(f"打开  {os.path.basename(path)}")
        if editor:
            for editor_cmd in get_editor_candidates():
                try: subprocess.Popen([editor_cmd, path]); return
                except FileNotFoundError: continue
        open_file(path)

    def _export_json(self): self._open_report("json", "JSON", editor=True)

    def _open_video(self):
        if not self._output_dir: messagebox.showinfo("提示", "没有可用的录制项目"); return
        video = os.path.join(self._output_dir, "inputs", f"{self._project_name}.mp4")
        if os.path.exists(video):
            self._log(f"打开  {os.path.basename(video)}")
            try: open_file(video)
            except OSError: messagebox.showwarning("提示", "找不到可用的视频播放器")
        else: messagebox.showinfo("提示", f"视频文件不存在:\n{video}")

    def _export_markdown(self): self._open_report("md", "Markdown", editor=True)
    def _export_html(self): self._open_report("html", "HTML")
    def _export_word(self): self._open_report("docx", "Word")

    def _export_zip(self):
        if not self._output_dir or not os.path.isdir(self._output_dir):
            messagebox.showinfo("提示", "没有可导出的录制项目，请先完成一次录制"); return
        self._ensure_reports()
        zip_path = filedialog.asksaveasfilename(title="导出录制工程 (ZIP)", defaultextension=".zip",
                                                filetypes=[("ZIP 压缩包", "*.zip")],
                                                initialfile=f"{self._project_name}.zip",
                                                initialdir=os.path.dirname(self._output_dir))
        if not zip_path: return
        try:
            self._log("正在导出 ZIP..."); self.root.config(cursor="watch"); self.root.update()
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root_dir, dirs, files in os.walk(self._output_dir):
                    for f in files:
                        fp = os.path.join(root_dir, f); zf.write(fp, os.path.relpath(fp, os.path.dirname(self._output_dir)))
            zs = os.path.getsize(zip_path)
            self._log(f"导出完成  {os.path.basename(zip_path)}  ({self._fmt_size(zs)})")
            messagebox.showinfo("导出成功", f"已导出到:\n{zip_path}\n大小: {self._fmt_size(zs)}")
        except Exception as e: messagebox.showerror("导出失败", str(e))
        finally: self.root.config(cursor="")

    def _export_guirunner(self):
        inputs = self._ensure_reports(); 
        if not inputs: return
        mapping_path = os.path.join(inputs, "clicked_icons", "mapping.json")
        if not os.path.exists(mapping_path):
            self._log("正在生成点击图标和 HAR...")
            from recorder.report_generator import generate_click_icons
            result = generate_click_icons(inputs, self._project_name)
            if not result or not result.get("ok"):
                messagebox.showwarning("提示", "无法生成点击图标，请先录制"); return
        output_dir = os.path.join(inputs, "clicked_icons")
        har_path = os.path.join(output_dir, "default.har")
        if not os.path.exists(har_path):
            from recorder.click_icon_extractor import load_report_json, generate_har, read_target_app, find_input_log
            report_json = os.path.join(inputs, f"report_{self._project_name}.json")
            if not os.path.exists(report_json):
                messagebox.showwarning("提示", "札找到 report JSON"); return
            with open(mapping_path, "r", encoding="utf-8") as f: mapping = json.load(f)
            input_log = find_input_log(inputs); target_app = read_target_app(input_log) if input_log else None
            har_path = generate_har(report_json, mapping, target_app, output_dir, self._project_name)
            if not har_path: messagebox.showwarning("提示", "HAR 生成失败"); return
        guirunner_url = self._guirunner_url.get().strip()
        self._log(f"正在推送到 GuiRunner ({guirunner_url})...")
        self.root.config(cursor="watch"); self.root.update()
        try:
            from recorder.click_icon_extractor import push_har_to_guirunner
            ok = push_har_to_guirunner(har_path, self._project_name, base_url=guirunner_url)
            if ok:
                editor_url = guirunner_url.rstrip("/") + "/static/webeditor/index.html#/?project=" + self._project_name
                self._log(f"GuiRunner 工程已创建/更新: {editor_url}")
                # 直接在默认浏览器打开 editor 页面，避免弹出 messagebox
                try:
                    import webbrowser
                    webbrowser.open_new_tab(editor_url)
                except Exception as wb_err:
                    self._log(f"浏览器打开失败: {wb_err}")
                    messagebox.showinfo("成功", f"GuiRunner 工程已推送：\n{editor_url}")
            else:
                self._log("GuiRunner 推送失败（后端可能未启动）")
                messagebox.showwarning("提示", f"推送失败，请确认 GuiRunner 后端已启动\n({guirunner_url})")
        except Exception as e:
            self._log(f"GuiRunner 推送异常: {e}"); messagebox.showerror("错误", f"推送失败:\n{e}")
        finally: self.root.config(cursor="")

    def _edit_in_urc(self):
        if not self._output_dir or not os.path.isdir(self._output_dir):
            messagebox.showinfo("提示", "没有可编辑的录制项目，请先完成一次录制"); return
        if not self._urc_server.is_ready:
            self._log("等待 UIRecorderCore 服务就绪..."); self.root.update()
            if not self._urc_server.start(wait_ready=True, timeout=15):
                messagebox.showerror("错误", "UIRecorderCore 服务启动失败"); return
        self._log("正在转换录制项目到 UIRecorderCore...")
        self.root.config(cursor="watch"); self.root.update()
        try: project = RecordingConverter.convert(self._output_dir)
        except Exception as e:
            self._log(f"转换失败: {e}"); messagebox.showerror("转换失败", str(e)); return
        finally: self.root.config(cursor="")
        if not project: messagebox.showerror("错误", "转换失败，未找到录制数据"); return
        from recorder.urc_bridge import _call_urc_api
        self._log(f"正在加载项目: {project}")
        ok = _call_urc_api("/api/v1/loadproject", {"project": project, "mode": "view"})
        if not ok: self._log("加载项目 API 调用失败，仍将打开编辑器")
        import webbrowser; import urllib.parse
        webbrowser.open(f"{self._urc_server.base_url}/?project={urllib.parse.quote(project)}")
        self._log(f"已打开 UIRecorderCore 编辑器 - 项目: {project}")

    def _on_close(self):
        if self._recording:
            if messagebox.askyesno("确认", "正在录制中，确定要退出吗?"):
                self._stop_recording(); self.root.destroy()
        else: self.root.destroy()

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _fmt_time(s: float) -> str:
        s = int(s); m, s = divmod(s, 60); h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _fmt_size(n: int) -> str:
        if n < 1024: return f"{n} B"
        if n < 1024 * 1024: return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.1f} MB"

    @staticmethod
    def _open_folder(path: str): open_folder(path)

    def run(self): self.root.mainloop()