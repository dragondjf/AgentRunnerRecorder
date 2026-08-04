# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import Entry, filedialog
from PIL import Image, ImageGrab, ImageTk, ImageDraw, ImageFilter, ImageFont
import os
import time
import math
import threading

# OCR 为可选功能：优先使用 urecorder/guiocr（wechat_ocr / rapidocr_openvino），
# 失败时回退到 pytesseract，均不可用则 OCR 按钮自动隐藏。
# OCR 函数统一返回结构化结果，便于在全屏绘制每个文字框：
#   {'ocrResult': [{'text': str, 'location': {'left','top','right','bottom'}}, ...]}
def _load_ocr_engine():
    """按优先级加载 OCR 引擎，返回可调用的 ocr(image_path)->dict 函数，或 None"""
    # 1) urecorder/guiocr.gui_ocr（本地图片路径，output='json' 返回 ocrResult 结构）
    try:
        import sys
        sys.path.insert(0, '../')
        from urecorder.guiocr import gui_ocr

        def _guiocr_ocr(img_path, lang=None):
            return gui_ocr(img_path, output='json')
        return _guiocr_ocr
    except Exception:
        pass
    # 2) pytesseract（image_to_data 拿每个词/行的 bounding box）
    try:
        import pytesseract

        def _tesseract_ocr(img_path, lang=None):
            data = pytesseract.image_to_data(
                img_path, lang='chi_sim+eng', output_type=pytesseract.Output.DICT)
            items = []
            n = len(data.get('text', []))
            for i in range(n):
                text = (data.get('text') or [])[i] or ''
                text = text.strip()
                conf = (data.get('conf') or [])[i]
                if not text:
                    continue
                try:
                    conf_f = float(conf)
                except Exception:
                    conf_f = 0.0
                if conf_f < 0:
                    continue  # 过滤置信度无效的词
                x, y = data['left'][i], data['top'][i]
                w, h = data['width'][i], data['height'][i]
                items.append({
                    'text': text,
                    'confidence': conf_f,
                    'location': {
                        'left': x, 'top': y,
                        'right': x + w, 'bottom': y + h,
                    },
                })
            return {'ocrResult': items}
        return _tesseract_ocr
    except Exception:
        pass
    return None


_OCR_FUNC = _load_ocr_engine()
OCR_AVAILABLE = _OCR_FUNC is not None


class WeChatStyleScreenshot:
    """
    参考微信截图交互风格的截图工具，支持标注工具条：
    1. 全屏暗色遮罩（半透明黑），选区内部恢复原图亮度
    2. 拖动任意方向画选区，实时显示 宽x高 尺寸
    3. 松开后：选区内部可移动、边缘可调整大小
    4. 底部工具条：矩形 / 椭圆 / 箭头 / 画笔 / 文字 / 马赛克 / 撤销 / OCR
    5. 标注矢量层与背景分离，保存时合成到最终截图
    6. Esc 退出 / 右键退出 / 双击 或 Enter 保存
    """
    MASK_ALPHA = 150          # 遮罩透明度（0-255），微信约 150
    BORDER_COLOR = '#07c160'  # 微信绿边框
    ANNO_COLOR = '#fa5151'    # 标注默认红色（微信标注色）
    TOOLBAR_H = 46            # 工具条高度

    def __init__(self, parent=None, on_done=None):
        """截图工具。

        parent : tk.Tk  | 已有的 Tk 根窗口（API 方式集成时传入）。
                 传入后使用 tk.Toplevel 作为截图窗口，与调用方共享事件循环，
                 不会新建 Tk() 根，也不阻塞调用方 mainloop。
                 为 None 时自建 Tk()（独立运行）。
        on_done: callable | 截图结束回调 on_done(success: bool, image: PIL.Image|None)。
                 确定 -> on_done(True, 合成后的截图)；取消/失败 -> on_done(False, None)。
        """
        self._on_done = on_done
        self._parent = parent
        if parent is not None:
            self.root = tk.Toplevel(parent)
        else:
            self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        self.root.configure(bg='black')

        # 截取整屏原图作为背景
        self.screen = ImageGrab.grab()
        self.screen_w, self.screen_h = self.screen.size

        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 预生成带遮罩的背景图（选区部分挖洞显示原图）
        self.masked_bg = self._build_masked_bg(0, 0, 0, 0)
        self.bg_image = ImageTk.PhotoImage(self.masked_bg)
        self.canvas.create_image(0, 0, anchor='nw', image=self.bg_image)

        # 选区状态
        self.x1 = self.y1 = self.x2 = self.y2 = None  # 最终选区
        self.drag = None          # None / 'new' / 'move' / 'nw','n','ne','w','e','sw','s','se'
        self.drag_origin = None   # 拖动起始坐标

        # 临时绘制对象（选区边框 / 尺寸 / 控制点）
        self.rect_item = None
        self.size_item = None
        self.handle_items = []

        # 标注层状态
        self.tool = None          # 当前激活工具: rect/ellipse/arrow/pen/text/mosaic
        self.annos = []           # 已完成的标注（dict 列表，支持撤销）
        self.undo_stack = []      # 撤销栈
        self.cur_anno = None      # 正在绘制的标注
        self.cur_items = []       # 当前标注对应的 canvas item，便于取消
        self.pen_points = []      # 画笔点序列
        self.text_entry = None    # 文字输入框
        self.anno_color = self.ANNO_COLOR

        # OCR 异步识别状态（后台线程避免阻塞 GUI）
        self._ocr_running = False
        self._ocr_thread = None
        self._ocr_status = None   # OCR 进行中提示的 canvas item
        self._ocr_text = ''       # 最近一次 OCR 识别的文字（供复制按钮使用）

        # 构建工具条
        self._build_toolbar()

        # 事件绑定
        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Motion>', self.on_motion)
        self.canvas.bind('<Leave>', self.on_leave)
        self.canvas.bind('<Double-Button-1>', lambda e: self.save_and_quit())
        self.root.bind('<Return>', lambda e: self.save_and_quit())
        self.root.bind('<Escape>', lambda e: self.cancel())
        self.canvas.bind('<Button-3>', lambda e: self.cancel())
        # Ctrl+Z 撤销
        self.root.bind('<Control-z>', lambda e: self.undo())
        self.root.bind('<Control-Z>', lambda e: self.undo())

        self.coord_item = None
        self._tooltip = None

        # API 集成（传入 parent）时，不阻塞调用方事件循环；
        # 独立运行时由外部（或入口）调用 self.root.mainloop()。
        if self._parent is None:
            self.root.mainloop()

    # ---------- 遮罩背景 ----------
    def _build_masked_bg(self, x1, y1, x2, y2):
        """生成背景：全屏变暗，选区矩形范围内恢复原图亮度"""
        dark = self.screen.convert('RGBA').point(
            lambda p: int(p * (255 - self.MASK_ALPHA) / 255))
        img = dark.copy()
        # 坐标可能为 None（未完成选区），做防御避免崩溃
        if (x1 is not None and y1 is not None
                and x2 is not None and y2 is not None
                and x2 > x1 and y2 > y1):
            region = self.screen.crop((x1, y1, x2, y2))
            img.paste(region, (x1, y1))
        return img.convert('RGB')

    def _refresh_bg(self):
        """重绘遮罩背景（选区改变时调用）"""
        # 坐标未就绪时只渲染全屏暗色遮罩，不绘制选区
        if (self.x1 is None or self.y1 is None
                or self.x2 is None or self.y2 is None
                or self.x2 <= self.x1 or self.y2 <= self.y1):
            dark = self.screen.convert('RGBA').point(
                lambda p: int(p * (255 - self.MASK_ALPHA) / 255)).convert('RGB')
            self.masked_bg = dark
        else:
            self.masked_bg = self._build_masked_bg(
                self.x1, self.y1, self.x2, self.y2)
        self.bg_image = ImageTk.PhotoImage(self.masked_bg)
        self.canvas.create_image(0, 0, anchor='nw', image=self.bg_image)

    # ---------- 工具条 ----------
    def _build_toolbar(self):
        """底部居中浅色圆角工具条"""
        # 生成高清图标图片
        self._make_icons()
        # 左侧标注工具：矩形、椭圆、箭头、画笔、文字、马赛克
        tools = ['rect', 'ellipse', 'arrow', 'pen', 'text', 'mosaic']
        # 右侧操作按钮：OCR、复制文字、撤销、下载、取消、确定
        actions = ['ocr', 'copy', 'undo', 'save', 'cancel', 'ok']
        if not OCR_AVAILABLE:
            actions = ['undo', 'save', 'cancel', 'ok']

        btn_w, gap = 36, 2
        group_gap = 10
        n_tools = len(tools)
        n_actions = len(actions)
        pad = 8
        tw = (n_tools * (btn_w + gap) + group_gap +
              n_actions * (btn_w + gap) + pad)
        th = self.TOOLBAR_H
        tx = (self.screen_w - tw) // 2
        ty = self.screen_h - th - 16

        self.toolbar = tk.Frame(self.root, bg='#ffffff',
                                highlightthickness=0, bd=0)
        self.toolbar.place(x=tx, y=ty, width=tw, height=th)
        # 给 Frame 加圆角：用 Canvas 当背景
        self.toolbar_bg = tk.Canvas(self.toolbar, bg='#ffffff',
                                    highlightthickness=0, bd=0)
        self.toolbar_bg.place(x=0, y=0, width=tw, height=th)
        r = 8
        self.toolbar_bg.create_oval(0, 0, r*2, r*2, fill='white', outline='white')
        self.toolbar_bg.create_oval(tw-r*2, 0, tw, r*2, fill='white', outline='white')
        self.toolbar_bg.create_oval(0, th-r*2, r*2, th, fill='white', outline='white')
        self.toolbar_bg.create_oval(tw-r*2, th-r*2, tw, th, fill='white', outline='white')
        self.toolbar_bg.create_rectangle(r, 0, tw-r, th, fill='white', outline='white')
        self.toolbar_bg.create_rectangle(0, r, tw, th-r, fill='white', outline='white')
        self.toolbar_bg.create_line(0, th-1, tw, th-1, fill='#e0e0e0')

        # 左侧标注工具：每个按钮是一个 Canvas，背景随状态重绘，
        # 图标用 Canvas 矢量绘制（矩形为正正方形），避免文本图标错位/消失
        self.tool_tips = {
            'rect': '矩形', 'ellipse': '椭圆', 'arrow': '箭头',
            'pen': '画笔', 'text': '文字', 'mosaic': '马赛克',
            'ocr': '文字识别', 'copy': '复制文字', 'undo': '撤销',
            'save': '下载', 'cancel': '取消', 'ok': '确定',
        }
        self.tool_buttons = {}
        x = pad // 2
        for key in tools:
            btn = tk.Label(self.toolbar, bg='#ffffff', cursor='hand2')
            btn.image = self.icons[key]['normal']
            btn.config(image=btn.image)
            btn.place(x=x, y=(th - 32) // 2, width=btn_w, height=32)
            btn.bind('<Button-1>', lambda e, k=key: self.select_tool(k))
            btn.bind('<Enter>', lambda e, b=btn, k=key: (
                b.config(bg='#f0f0f0'),
                self._show_tooltip(b, self.tool_tips[k])))
            btn.bind('<Leave>', lambda e, b=btn, k=key: (
                b.config(bg='#07c160' if self.tool == k else '#ffffff'),
                self._hide_tooltip()))
            btn._key = key
            self.tool_buttons[key] = btn
            x += btn_w + gap

        # 操作按钮
        x += group_gap
        self.action_buttons = {}
        for key in actions:
            btn = tk.Label(self.toolbar, cursor='hand2')
            is_ok = (key == 'ok')
            btn.image = self.icons[key]['sel' if is_ok else 'normal']
            btn.config(image=btn.image, bg='#07c160' if is_ok else '#ffffff')
            btn.place(x=x, y=(th - 32) // 2, width=btn_w, height=32)
            btn.bind('<Button-1>', lambda e, k=key: self.on_action(k))
            btn.bind('<Enter>', lambda e, b=btn, k=key: (
                b.config(bg='#06ad56' if k == 'ok' else '#f0f0f0'),
                self._show_tooltip(b, self.tool_tips[k])))
            btn.bind('<Leave>', lambda e, b=btn, k=key: (
                b.config(bg='#07c160' if k == 'ok' else '#ffffff'),
                self._hide_tooltip()))
            self.action_buttons[key] = btn
            x += btn_w + gap

    def _on_btn_enter(self, c, key):
        self._show_tooltip(c, self.tool_tips[key])

    def _on_btn_leave(self, c):
        self._hide_tooltip()

    def _show_tooltip(self, widget, text):
        """在鼠标位置上方显示 tooltip 标签"""
        self._hide_tooltip()
        try:
            ax = widget.winfo_rootx()
            ay = widget.winfo_rooty()
        except Exception:
            return
        tip = tk.Toplevel(self.root)
        tip.wm_overrideredirect(True)
        tip.wm_attributes('-topmost', True)
        tip.configure(bg='#333333')
        lbl = tk.Label(tip, text=text, bg='#333333', fg='white',
                       font=('Microsoft YaHei', 11), padx=6, pady=2)
        lbl.pack()
        # 定位到按钮正上方居中
        self.root.update_idletasks()
        w = tip.winfo_width()
        h = tip.winfo_height()
        bx = ax + (widget.winfo_width() - w) // 2
        by = ay - h - 6
        tip.wm_geometry(f'+{bx}+{by}')
        self._tooltip = tip

    def _hide_tooltip(self):
        if getattr(self, '_tooltip', None):
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    # ---------- 图标生成（PIL 高清，透明背景） ----------
    def _make_icons(self):
        """用 PIL 生成所有按钮图标为 PhotoImage（normal 深色 / sel 白色）"""
        S = 96  # 高分辨率绘制画布，缩小到 24 更清晰
        OUT = (24, 24)
        self.icons = {}
        dark = (51, 51, 51, 255)
        white = (255, 255, 255, 255)

        def draw_icon(drawer):
            img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            drawer(d, (51, 51, 51, 255))
            n = ImageTk.PhotoImage(img.resize(OUT, Image.LANCZOS))
            # 白色版本
            img2 = Image.new('RGBA', (S, S), (0, 0, 0, 0))
            d2 = ImageDraw.Draw(img2)
            drawer(d2, white)
            s = ImageTk.PhotoImage(img2.resize(OUT, Image.LANCZOS))
            return {'normal': n, 'sel': s}

        # 矩形
        self.icons['rect'] = draw_icon(
            lambda d, c: d.rectangle([22, 22, 74, 74], outline=c, width=9))
        # 椭圆
        self.icons['ellipse'] = draw_icon(
            lambda d, c: d.ellipse([20, 22, 76, 74], outline=c, width=9))
        # 箭头：标准对角粗线 + 对称实心三角箭头头（顶点在末端）
        def arrow_drawer(d, c):
            x1, y1, x2, y2 = 22, 74, 74, 22
            d.line([x1, y1, x2, y2], fill=c, width=11, joint='curve')
            # 三角箭头头：以末端为顶点，垂直于主线两侧展开
            import math as _m
            ang = _m.atan2(y1 - y2, x1 - x2)  # 指向末端方向
            head = 26
            half = _m.radians(26)
            bx, by = x2, y2
            p1 = (bx + head * _m.cos(ang - half), by + head * _m.sin(ang - half))
            p2 = (bx + head * _m.cos(ang + half), by + head * _m.sin(ang + half))
            d.polygon([(bx, by), p1, p2], fill=c)
        self.icons['arrow'] = draw_icon(arrow_drawer)
        # 画笔：标准铅笔（笔尖朝右上，笔身斜放）
        def pen_drawer(d, c):
            # 笔身主轴：从笔尾(左下)到笔尖(右上)
            x1, y1, x2, y2 = 26, 72, 70, 28
            import math as _m
            ang = _m.atan2(y2 - y1, x2 - x1)
            w = 9  # 笔身半宽
            nx, ny = -_m.sin(ang), _m.cos(ang)
            # 笔身四边形
            b1 = (x1 + nx*w, y1 + ny*w)
            b2 = (x1 - nx*w, y1 - ny*w)
            tip_base = (x2 - (x2-x1)*0.30, y2 - (y2-y1)*0.30)  # 笔尖起点
            b3 = (tip_base[0] - nx*w, tip_base[1] - ny*w)
            b4 = (tip_base[0] + nx*w, tip_base[1] + ny*w)
            d.polygon([b1, b4, b3, b2], fill=c)
            # 笔尖三角
            d.polygon([b4, (x2, y2), b3], fill=c)
        self.icons['pen'] = draw_icon(pen_drawer)
        # 文字 A
        self.icons['text'] = draw_icon(
            lambda d, c: d.text((48, 44), 'A', fill=c,
                                anchor='mm', font=self._icon_font(60)))
        # 马赛克 3x3
        def mosaic_drawer(d, c):
            for i in range(3):
                for j in range(3):
                    shade = 150 + (i * 3 + j) * 12
                    col = (shade, shade, shade, 255)
                    d.rectangle([24 + i*18, 24 + j*18, 24 + i*18 + 15,
                                 24 + j*18 + 15], fill=col,
                                outline=(255, 255, 255, 255))
        self.icons['mosaic'] = draw_icon(mosaic_drawer)
        # OCR（放大镜 + A 文字，表示文字识别）——放大镜画大画粗，缩小后仍清晰
        def ocr_drawer(d, c):
            d.ellipse([18, 18, 66, 66], outline=c, width=10)
            d.line([62, 62, 82, 82], fill=c, width=13, joint='curve')
            d.text((42, 54), 'A', fill=c, anchor='mm', font=self._icon_font(36))
        self.icons['ocr'] = draw_icon(ocr_drawer)
        # 复制文字（两个叠放的矩形，表示复制到剪贴板）
        def copy_drawer(d, c):
            d.rectangle([28, 22, 70, 62], outline=c, width=7)
            d.rectangle([22, 34, 64, 74], outline=c, width=7)
        self.icons['copy'] = draw_icon(copy_drawer)
        # 撤销（弯箭头）
        self.icons['undo'] = draw_icon(
            lambda d, c: d.arc([26, 28, 70, 72], start=30, end=300,
                               fill=c, width=9))
        # 下载（箭头向下 + 横线）
        def save_drawer(d, c):
            d.line([48, 26, 48, 64], fill=c, width=9)
            d.polygon([48, 68, 32, 54, 64, 54], fill=c)
            d.line([30, 74, 66, 74], fill=c, width=9)
        self.icons['save'] = draw_icon(save_drawer)
        # 取消（叉）
        self.icons['cancel'] = draw_icon(
            lambda d, c: d.line([30, 30, 66, 66], fill=c, width=10) or
                         d.line([66, 30, 30, 66], fill=c, width=10))
        # 确定（勾）
        self.icons['ok'] = draw_icon(
            lambda d, c: d.line([28, 48, 44, 64, 72, 28], fill=c, width=10,
                                joint='curve'))

    def _icon_font(self, size):
        try:
            return ImageFont.truetype('msyh.ttc', size)
        except Exception:
            return ImageFont.load_default()

    def select_tool(self, key):
        """切换当前标注工具；再次点击同一工具则取消"""
        self._commit_text()
        if self.tool == key:
            self.tool = None
        else:
            self.tool = key
        for k, btn in self.tool_buttons.items():
            sel = (self.tool == k)
            btn.config(image=self.icons[k]['sel' if sel else 'normal'],
                       bg='#07c160' if sel else '#ffffff')
        if self.tool:
            self.canvas.config(cursor='cross')
        else:
            self.canvas.config(cursor='arrow')

    def on_action(self, key):
        """处理右侧操作按钮"""
        if key == 'ocr':
            self.do_ocr()
        elif key == 'copy':
            self.copy_ocr_text()
        elif key == 'undo':
            self.undo()
        elif key == 'save':
            self.save_and_quit()
        elif key == 'cancel':
            self.cancel()
        elif key == 'ok':
            self.copy_image_and_quit()

    # ---------- 事件处理（选区 + 标注） ----------
    def _in_toolbar(self, x, y):
        try:
            tx, ty = self.toolbar.winfo_x(), self.toolbar.winfo_y()
            tw, th = self.toolbar.winfo_width(), self.toolbar.winfo_height()
            return tx <= x <= tx + tw and ty <= y <= ty + th
        except Exception:
            return False

    def on_motion(self, event):
        """鼠标移动：更新坐标显示 + 边角/选区光标形态"""
        x, y = event.x, event.y
        if self._in_toolbar(x, y):
            if self.coord_item:
                self.canvas.delete(self.coord_item)
                self.coord_item = None
            return
        # 边角/边缘：根据方向显示调整大小光标
        if self.x1 is not None:
            handle = self._hit_handle(x, y)
            if handle:
                self._set_cursor(self._handle_cursor(handle))
                self._draw_coord(x, y)
                return
            # 选区内部：移动光标
            if self.x1 < x < self.x2 and self.y1 < y < self.y2:
                self._set_cursor('fleur')
                self._draw_coord(x, y)
                return
        # 默认光标：工具激活为 cross，否则 arrow
        self._set_cursor('cross' if self.tool else 'arrow')
        self._draw_coord(x, y)

    def _set_cursor(self, name):
        """安全设置光标，避免不支持的 cursor 名导致 TclError 崩溃"""
        try:
            self.canvas.config(cursor=name)
        except tk.TclError:
            try:
                self.canvas.config(cursor='arrow')
            except Exception:
                pass

    def _handle_cursor(self, handle):
        """边角/边缘对应的调整大小光标"""
        return {
            'nw': 'size_nw_se', 'se': 'size_nw_se',
            'ne': 'size_ne_sw', 'sw': 'size_ne_sw',
            'n': 'size_ns', 's': 'size_ns',
            'e': 'size_we', 'w': 'size_we',
        }.get(handle, 'arrow')

    def _draw_coord(self, x, y):
        text = f'({x}, {y})'
        if self.coord_item:
            self.canvas.delete(self.coord_item)
        self.coord_item = self.canvas.create_text(
            x + 12, y + 12, anchor='nw', text=text,
            fill='#07c160', font=('Microsoft YaHei', 11, 'bold'))

    def on_leave(self, event):
        """鼠标离开画布时清除坐标显示"""
        if self.coord_item:
            self.canvas.delete(self.coord_item)
            self.coord_item = None

    def on_press(self, event):
        x, y = event.x, event.y
        if self._in_toolbar(x, y):
            return  # 点击工具条不触发任何画布操作
        # 文字输入中，先提交
        self._commit_text()

        # 若已激活标注工具，且点击在选区内 → 在选区内绘制标注
        if self.tool and self.x1 is not None:
            in_sel = self.x1 < x < self.x2 and self.y1 < y < self.y2
            if self.tool == 'text':
                if in_sel:
                    self._start_text(x, y)
                    return
                return
            if not in_sel:
                # 标注必须先有选区，且从选区内开始
                return
            if self.tool in ('pen', 'mosaic'):
                self.cur_anno = {'type': self.tool, 'color': self.anno_color,
                                 'points': [(x, y)]}
                self.pen_points = [(x, y)]
            else:
                self.cur_anno = {'type': self.tool, 'color': self.anno_color,
                                 'start': (x, y), 'end': (x, y)}
            self.cur_items = []
            return

        # 否则走选区逻辑
        # 点击选区内部 → 移动选区（未激活工具时）
        if self.x1 is not None and self.x1 < x < self.x2 and self.y1 < y < self.y2:
            if not self.tool:
                self.drag = 'move'
                self.drag_origin = (x - self.x1, y - self.y1)
            return
        # 点击边缘控制点 → 调整大小
        handle = self._hit_handle(x, y)
        if handle:
            self.drag = handle
            self.drag_origin = (self.x1, self.y1, self.x2, self.y2, x, y)
            self._set_cursor(self._handle_cursor(handle))
            return
        # 否则 → 开始新选区
        self._clear_overlay()
        self._clear_annos()
        self.drag = 'new'
        self.x1 = self.y1 = self.x2 = self.y2 = None
        self.drag_origin = (x, y)

    def on_drag(self, event):
        x, y = event.x, event.y
        if self.cur_anno is not None:
            self._draw_current_anno(x, y)
            return
        if self.drag == 'new':
            sx, sy = self.drag_origin
            self.x1, self.x2 = sorted((sx, x))
            self.y1, self.y2 = sorted((sy, y))
        elif self.drag == 'move':
            if (self.x1 is None or self.y1 is None
                    or self.x2 is None or self.y2 is None):
                return  # 选区未建立，忽略移动
            ox, oy = self.drag_origin
            w, h = self.x2 - self.x1, self.y2 - self.y1
            nx, ny = x - ox, y - oy
            nx = max(0, min(nx, self.screen_w - w))
            ny = max(0, min(ny, self.screen_h - h))
            self.x1, self.y1 = nx, ny
            self.x2, self.y2 = nx + w, ny + h
        elif self.drag in ('nw', 'n', 'ne', 'w', 'e', 'sw', 's', 'se'):
            ox1, oy1, ox2, oy2, sx, sy = self.drag_origin
            if 'w' in self.drag:
                self.x1 = x
                self.x2 = ox2
            if 'e' in self.drag:
                self.x1 = ox1
                self.x2 = x
            if 'n' in self.drag:
                self.y1 = y
                self.y2 = oy2
            if 's' in self.drag:
                self.y1 = oy1
                self.y2 = y
            self.x1, self.x2 = sorted((self.x1, self.x2))
            self.y1, self.y2 = sorted((self.y1, self.y2))
        self._draw_selection()

    def on_release(self, event):
        if self.cur_anno is not None:
            self._finish_current_anno()
            return
        self.drag = None
        if self.x1 is not None and (self.x2 - self.x1 < 3 or self.y2 - self.y1 < 3):
            self.x1 = self.y1 = self.x2 = self.y2 = None
            self._draw_selection()

    # ---------- 当前标注绘制 ----------
    def _draw_current_anno(self, x, y):
        """实时绘制正在进行的标注"""
        a = self.cur_anno
        if a['type'] in ('pen', 'mosaic'):
            a['points'].append((x, y))
            self.pen_points.append((x, y))
            # 实时增量绘制
            if len(self.pen_points) >= 2:
                p0, p1 = self.pen_points[-2], self.pen_points[-1]
                if a['type'] == 'pen':
                    item = self.canvas.create_line(
                        p0[0], p0[1], p1[0], p1[1],
                        fill=a['color'], width=3, capstyle=tk.ROUND,
                        smooth=True)
                else:
                    # 马赛克实时预览用半透明色块近似
                    item = self.canvas.create_line(
                        p0[0], p0[1], p1[0], p1[1],
                        fill='#cccccc', width=12, capstyle=tk.ROUND)
                self.cur_items.append(item)
        else:
            a['end'] = (x, y)
            # 清除旧预览，重画
            for it in self.cur_items:
                self.canvas.delete(it)
            self.cur_items = []
            items = self._canvas_draw_anno(a, preview=True)
            if items:
                self.cur_items.extend(items if isinstance(items, list) else [items])

    def _finish_current_anno(self):
        a = self.cur_anno
        # 过滤无效标注
        if a['type'] in ('rect', 'ellipse', 'arrow'):
            sx, sy = a['start']
            ex, ey = a['end']
            if abs(ex - sx) < 3 and abs(ey - sy) < 3:
                # 太小，丢弃
                for it in self.cur_items:
                    self.canvas.delete(it)
                self.cur_anno = None
                self.cur_items = []
                return
        # 完成：将 canvas item 保留，记录标注数据用于最终合成
        a['items'] = list(self.cur_items)
        self._add_annotation(a)
        self.cur_anno = None
        self.cur_items = []
        self.pen_points = []

    # ---------- 标注绘制到画布 ----------
    def _canvas_draw_anno(self, a, preview=False):
        """根据标注 dict 在 canvas 上绘制（返回 item id 列表）"""
        t = a['type']
        color = a['color']
        if t == 'rect':
            sx, sy = a['start']
            ex, ey = a['end']
            return [self.canvas.create_rectangle(sx, sy, ex, ey,
                                                 outline=color, width=3)]
        if t == 'ellipse':
            sx, sy = a['start']
            ex, ey = a['end']
            return [self.canvas.create_oval(sx, sy, ex, ey,
                                            outline=color, width=3)]
        if t == 'arrow':
            return self._draw_arrow(a['start'], a['end'], color)
        if t == 'pen':
            pts = a['points']
            if len(pts) < 2:
                return None
            item = self.canvas.create_line(
                *[coord for p in pts for coord in p],
                fill=color, width=3, capstyle=tk.ROUND, smooth=True)
            return [item]
        if t == 'mosaic':
            # 预览阶段已在 on_drag 增量绘制，完成时无需重复
            return None
        return None

    def _draw_arrow(self, start, end, color, width=3):
        """绘制箭头，返回所有 canvas item 列表（含头部）"""
        sx, sy = start
        ex, ey = end
        items = []
        items.append(self.canvas.create_line(sx, sy, ex, ey, fill=color,
                                              width=width, capstyle=tk.ROUND))
        # 箭头头部：两条线收敛到末端 ex,ey，朝指向 end 方向
        angle = math.atan2(ey - sy, ex - sx)
        head = 12
        ah = math.pi / 6
        p1 = (ex - head * math.cos(angle - ah),
              ey - head * math.sin(angle - ah))
        p2 = (ex - head * math.cos(angle + ah),
              ey - head * math.sin(angle + ah))
        items.append(self.canvas.create_line(ex, ey, *p1, fill=color,
                                              width=width, capstyle=tk.ROUND))
        items.append(self.canvas.create_line(ex, ey, *p2, fill=color,
                                              width=width, capstyle=tk.ROUND))
        return items

    # ---------- 文字标注 ----------
    def _start_text(self, x, y):
        # 在点击位置放置一个 Entry 用于输入
        self._commit_text()
        entry = Entry(self.root, bg='white', fg='black',
                      font=('Microsoft YaHei', 14), bd=1,
                      insertbackground='black')
        entry.place(x=x, y=y, width=160, height=24)
        entry.focus_set()
        entry.bind('<Return>', lambda e: self._commit_text())
        entry.bind('<FocusOut>', lambda e: self._commit_text())
        self.text_entry = {'widget': entry, 'x': x, 'y': y}
        self.canvas.config(cursor='xterm')

    def _commit_text(self):
        if self.text_entry:
            te = self.text_entry
            self.text_entry = None
            text = te['widget'].get().strip()
            te['widget'].destroy()
            if text:
                self._add_annotation({'type': 'text', 'color': self.anno_color,
                                      'pos': (te['x'], te['y']), 'text': text})
            self.canvas.config(cursor='cross' if self.tool else 'arrow')

    def _add_annotation(self, a):
        """添加标注并清空 redo 栈"""
        if a['type'] == 'text':
            item = self.canvas.create_text(
                a['pos'][0], a['pos'][1], anchor='nw', text=a['text'],
                fill=a['color'], font=('Microsoft YaHei', 14, 'bold'))
            a['items'] = [item]
        elif a['type'] == 'ocr':
            # 全屏绘制所有 OCR 矩形框（仅显示框，不显示文字）
            items = []
            for b in a['boxes']:
                x1, y1, x2, y2 = b['box']
                items.append(self.canvas.create_rectangle(
                    x1, y1, x2, y2, outline=a['color'], width=1))
            a['items'] = items
        self.annos.append(a)
        self.undo_stack.clear()

    # ---------- 撤销 / 重做 / 清除 ----------
    def undo(self):
        """撤销上一步标注"""
        self._commit_text()
        if self.annos:
            a = self.annos.pop()
            for it in a.get('items', []):
                if it:
                    self.canvas.delete(it)
            self.undo_stack.append(a)

    def redo(self):
        """重做一步标注"""
        self._commit_text()
        if self.undo_stack:
            a = self.undo_stack.pop()
            if a['type'] in ('rect', 'ellipse', 'arrow'):
                items = self._canvas_draw_anno(a)
                a['items'] = items if items else []
            elif a['type'] == 'pen':
                pts = a['points']
                item = self.canvas.create_line(
                    *[coord for p in pts for coord in p],
                    fill=a['color'], width=3, capstyle=tk.ROUND, smooth=True)
                a['items'] = [item]
            elif a['type'] == 'mosaic':
                # 重做时重新绘制马赛克预览线
                pts = a['points']
                items = []
                for i in range(len(pts) - 1):
                    item = self.canvas.create_line(
                        pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                        fill='#cccccc', width=12, capstyle=tk.ROUND)
                    items.append(item)
                a['items'] = items
            elif a['type'] == 'text':
                item = self.canvas.create_text(
                    a['pos'][0], a['pos'][1], anchor='nw', text=a['text'],
                    fill=a['color'], font=('Microsoft YaHei', 14, 'bold'))
                a['items'] = [item]
            elif a['type'] == 'ocr':
                items = []
                for b in a['boxes']:
                    x1, y1, x2, y2 = b['box']
                    items.append(self.canvas.create_rectangle(
                        x1, y1, x2, y2, outline=a['color'], width=1))
                a['items'] = items
            self.annos.append(a)

    def _clear_annos(self):
        for a in self.annos:
            for it in a.get('items', []):
                if it:
                    self.canvas.delete(it)
        self.annos = []
        if self.cur_anno:
            for it in self.cur_items:
                self.canvas.delete(it)
            self.cur_anno = None
            self.cur_items = []

    # ---------- OCR / 复制 / 钉图 / 分享 ----------
    def do_ocr(self):
        if not OCR_AVAILABLE:
            return
        # 记录本次选区：未拖拽选区时对全屏做 OCR
        if (self.x1 is None or self.x2 - self.x1 < 1 or self.y2 - self.y1 < 1):
            x1, y1, x2, y2 = 0, 0, self.screen_w, self.screen_h
        else:
            x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        # OCR 是耗时操作（wechat_ocr 加载引擎 / rapidocr 加载模型），
        # 放到后台线程执行，避免阻塞 tkinter 主线程导致界面/终端卡住。
        # 期间显示"识别中"提示，完成后回到主线程绘制文字框。
        if getattr(self, '_ocr_running', False):
            return  # 上一次识别仍在进行，忽略重复点击
        self._ocr_running = True

        # 记录本次选区（后台线程期间选区可能变化，用快照）
        sub = self.screen.crop((x1, y1, x2, y2))
        self._show_ocr_status('OCR 识别中…')
        self._ocr_thread = threading.Thread(
            target=self._do_ocr_worker, args=(sub, x1, y1), daemon=True)
        self._ocr_thread.start()

    def _do_ocr_worker(self, sub, x1, y1):
        """后台线程执行 OCR 识别（不触碰 tkinter UI，避免跨线程卡顿）"""
        result = None
        tmp_path = None
        try:
            import tempfile
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(
                tmp_dir, f'screenshot_ocr_{int(time.time() * 1000)}.png')
            sub.save(tmp_path)
            result = _OCR_FUNC(tmp_path)
        except Exception as e:
            result = None
            print(f'⚠ OCR 识别失败: {e}')
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        # 回到主线程绘制结果
        self.root.after(0, lambda: self._finish_ocr(result, x1, y1))

    def _finish_ocr(self, result, x1, y1):
        """主线程：解析 OCR 结果并全屏绘制所有文字框"""
        self._ocr_running = False
        self._hide_ocr_status()
        if not isinstance(result, dict):
            return
        boxes = []
        for item in result.get('ocrResult') or []:
            if not isinstance(item, dict):
                continue
            loc = item.get('location') or {}
            left = loc.get('left')
            top = loc.get('top')
            right = loc.get('right')
            bottom = loc.get('bottom')
            if left is None or top is None or right is None or bottom is None:
                continue
            boxes.append({
                'text': item.get('text', ''),
                'box': (x1 + int(left), y1 + int(top),
                        x1 + int(right), y1 + int(bottom)),
            })

        if boxes:
            # 保存本次识别文字，供"复制文字"按钮使用（按框顺序逐行拼接）
            self._ocr_text = '\n'.join(
                b['text'] for b in boxes if b['text']) or ''
            # 作为单个可撤销的 OCR 标注：全屏绘制所有文字框
            self._add_annotation({'type': 'ocr', 'color': '#ff0000', 'boxes': boxes})
            texts = ' | '.join(b['text'] for b in boxes if b['text'])
            print(f'📝 OCR 识别到 {len(boxes)} 个文字框:\n{texts}')
        else:
            self._ocr_text = ''
            print('📝 OCR 未识别到文字')

    def copy_ocr_text(self):
        """一键复制最近一次 OCR 识别的文字到剪贴板（写入系统剪贴板）"""
        text = getattr(self, '_ocr_text', '')
        if not text:
            self._show_ocr_status('暂无可复制的文字')
            self.root.after(1200, self._hide_ocr_status)
            return
        ok = False
        # 优先用 win32clipboard 写入系统剪贴板（比 tkinter 剪贴板更可靠）
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            ok = True
        except Exception:
            ok = False
        if not ok:
            # 回退：tkinter 剪贴板
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update()
                ok = True
            except Exception:
                ok = False
        if ok:
            self._show_ocr_status('已复制到剪贴板')
            self.root.after(1200, self._hide_ocr_status)
            print(f'📋 已复制 {len(text)} 字符到剪贴板')
        else:
            self._show_ocr_status('复制失败')
            self.root.after(1200, self._hide_ocr_status)
            print('⚠ 复制失败')

    def _show_ocr_status(self, text):
        """在画布顶部中央显示 OCR 进行中提示（透明背景，深色文字保证任意截图上可读）"""
        self._hide_ocr_status()
        # 透明背景：不绘制色块，用 tag 归组的白描边 + 深色主体文字提升可读性
        tag = '_ocr_status_tag'
        x, y = self.screen_w // 2, 40
        font = ('Microsoft YaHei', 14, 'bold')
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.canvas.create_text(x + dx, y + dy, anchor='n', text=text,
                                    fill='white', font=font, tags=tag)
        self._ocr_status = self.canvas.create_text(
            x, y, anchor='n', text=text, fill='#07c160', font=font, tags=tag)

    def _hide_ocr_status(self):
        if getattr(self, '_ocr_status', None):
            try:
                self.canvas.delete('_ocr_status_tag')
            except Exception:
                pass
            self._ocr_status = None

    def _get_final_image(self):
        """获取带标注的合成截图"""
        self._commit_text()
        if self.x1 is None or self.x2 - self.x1 < 1 or self.y2 - self.y1 < 1:
            return None
        self.root.withdraw()
        self.root.update()
        time.sleep(0.05)
        x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        if self.annos:
            screenshot = self._compose_annotations(screenshot)
        self.root.deiconify()
        return screenshot

    # ---------- 选区绘制 ----------
    def _hit_handle(self, x, y):
        if self.x1 is None:
            return None
        r = 6
        corners = {
            'nw': (self.x1, self.y1), 'n': ((self.x1 + self.x2)//2, self.y1),
            'ne': (self.x2, self.y1), 'e': (self.x2, (self.y1+self.y2)//2),
            'se': (self.x2, self.y2), 's': ((self.x1+self.x2)//2, self.y2),
            'sw': (self.x1, self.y2), 'w': (self.x1, (self.y1+self.y2)//2),
        }
        for name, (cx, cy) in corners.items():
            if abs(x - cx) <= r and abs(y - cy) <= r:
                return name
        return None

    def _draw_selection(self):
        self._refresh_bg()
        self._clear_overlay()
        if self.x1 is None:
            return
        x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        self.rect_item = self.canvas.create_rectangle(
            x1, y1, x2, y2, outline=self.BORDER_COLOR, width=2)
        w, h = x2 - x1, y2 - y1
        ty = y1 - 4 if y1 - 4 > 14 else y2 + 4
        self.size_item = self.canvas.create_text(
            x1, ty, anchor='sw', text=f'{w} × {h}',
            fill='white', font=('Microsoft YaHei', 12, 'bold'))
        for hx, hy in self._handles():
            self.handle_items.append(
                self.canvas.create_rectangle(
                    hx-3, hy-3, hx+3, hy+3,
                    fill=self.BORDER_COLOR, outline='white'))

    def _handles(self):
        x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        return [(x1, y1), (cx, y1), (x2, y1),
                (x2, cy), (x2, y2), (cx, y2),
                (x1, y2), (x1, cy)]

    def _clear_overlay(self):
        for item in [self.rect_item, self.size_item] + self.handle_items:
            if item:
                self.canvas.delete(item)
        self.rect_item = self.size_item = None
        self.handle_items = []

    # ---------- 合成标注到最终图片 ----------
    def _compose_annotations(self, img):
        """将 annos 用 PIL 绘制到最终截图上（画布坐标 = 图片坐标）"""
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype('msyh.ttc', 14)
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
        for a in self.annos:
            t = a['type']
            color = a['color']
            if t == 'rect':
                sx, sy = a['start']
                ex, ey = a['end']
                draw.rectangle([sx, sy, ex, ey], outline=color, width=3)
            elif t == 'ellipse':
                sx, sy = a['start']
                ex, ey = a['end']
                draw.ellipse([sx, sy, ex, ey], outline=color, width=3)
            elif t == 'arrow':
                sx, sy = a['start']
                ex, ey = a['end']
                draw.line([sx, sy, ex, ey], fill=color, width=3)
                angle = math.atan2(ey - sy, ex - sx)
                head = 12
                ah = math.pi / 6
                p1 = (ex - head * math.cos(angle - ah),
                      ey - head * math.sin(angle - ah))
                p2 = (ex - head * math.cos(angle + ah),
                      ey - head * math.sin(angle + ah))
                draw.line([ex, ey, int(p1[0]), int(p1[1])], fill=color, width=3)
                draw.line([ex, ey, int(p2[0]), int(p2[1])], fill=color, width=3)
            elif t == 'pen':
                pts = a['points']
                if len(pts) >= 2:
                    draw.line(pts, fill=color, width=3, joint='curve')
            elif t == 'mosaic':
                self._apply_mosaic(img, a['points'])
            elif t == 'text':
                draw.text(a['pos'], a['text'], fill=color, font=font)
            elif t == 'ocr':
                # 框坐标为全屏坐标，img 为选区局部图，需减选区起点偏移
                # 仅绘制矩形框，不显示文字
                ox, oy = self.x1, self.y1
                for b in a['boxes']:
                    bx1, by1, bx2, by2 = b['box']
                    draw.rectangle(
                        [bx1 - ox, by1 - oy, bx2 - ox, by2 - oy],
                        outline=color, width=1)
        return img

    def _apply_mosaic(self, img, points):
        """对画笔轨迹经过的区域做马赛克模糊"""
        if not points:
            return
        minx = max(0, min(p[0] for p in points) - 8)
        maxx = min(img.width, max(p[0] for p in points) + 8)
        miny = max(0, min(p[1] for p in points) - 8)
        maxy = min(img.height, max(p[1] for p in points) + 8)
        if maxx <= minx or maxy <= miny:
            return
        region = img.crop((minx, miny, maxx, maxy))
        # 缩小再放大实现马赛克
        small = region.resize((max(1, (maxx - minx) // 8),
                               max(1, (maxy - miny) // 8)),
                              Image.NEAREST)
        mosaic = small.resize((maxx - minx, maxy - miny), Image.NEAREST)
        img.paste(mosaic, (minx, miny))

    # ---------- 保存 / 取消 ----------
    def save_and_quit(self):
        self._commit_text()
        if self.x1 is None or self.x2 - self.x1 < 1 or self.y2 - self.y1 < 1:
            return
        # 临时取消置顶（不隐藏窗口/工具条），让 filedialog 能正常显示在最前
        was_topmost = False
        try:
            was_topmost = bool(self.root.attributes('-topmost'))
        except Exception:
            pass
        self.root.attributes('-topmost', False)
        self.root.update()
        # 弹出“另存为”对话框选择目录与文件名
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        filepath = filedialog.asksaveasfilename(
            title='保存截图',
            initialdir=desktop,
            initialfile='screenshot.png',
            defaultextension='.png',
            filetypes=[('PNG 图片', '*.png'),
                       ('JPEG 图片', '*.jpg;*.jpeg'),
                       ('所有文件', '*.*')])
        if not filepath:
            # 用户取消：恢复截图窗口置顶，保留选区继续编辑
            self.root.attributes('-topmost', True)
            self.root.lift()
            return
        # 保存成功后由 _reset_state 处理窗口状态
        time.sleep(0.05)
        x1, y1, x2, y2 = self.x1, self.y1, self.x2, self.y2
        screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        if self.annos:
            screenshot = self._compose_annotations(screenshot)
        screenshot.save(filepath)
        print(f'✅ 截图已保存至: {filepath}')
        # 保存成功：回到初始状态，支持连续截图（不退出工具，也不触发宿主还原）
        # 只有真正退出（确定复制/取消）时才调用 on_done 让宿主还原窗口
        self._reset_state()

    def _reset_state(self):
        """重置截图工具到初始状态（清空选区/标注/撤销栈），支持连续截图。"""
        # 清除主 canvas 上所有绘制（背景、选区、标注、OCR 提示等）。
        # 工具条是独立 tk.Frame，不在主 canvas 上，保留。
        self.canvas.delete('all')
        # 重建全屏暗色遮罩背景（无选区）
        self.masked_bg = self._build_masked_bg(0, 0, 0, 0)
        self.bg_image = ImageTk.PhotoImage(self.masked_bg)
        self.canvas.create_image(0, 0, anchor='nw', image=self.bg_image)
        # 重置选区状态
        self.x1 = self.y1 = self.x2 = self.y2 = None
        self.drag = None
        self.drag_origin = None
        # 重置临时绘制对象
        self.rect_item = None
        self.size_item = None
        self.handle_items = []
        # 重置标注层状态
        self.tool = None
        self.annos = []
        self.undo_stack = []
        self.cur_anno = None
        self.cur_items = []
        self.pen_points = []
        self.text_entry = None
        self.anno_color = self.ANNO_COLOR
        # 重置 OCR 状态
        self._ocr_running = False
        self._ocr_thread = None
        self._ocr_status = None
        self._ocr_text = ''
        self.coord_item = None
        # 恢复截图窗口置顶并聚焦（窗口本身未隐藏，工具条保持显示）
        try:
            self.root.attributes('-topmost', True)
            self.root.lift()
        except Exception:
            pass

    def copy_image_and_quit(self):
        """确定：把合成后的选区截图复制到系统剪贴板并退出"""
        if self.x1 is None or self.x2 - self.x1 < 1 or self.y2 - self.y1 < 1:
            return
        img = self._get_final_image()
        if img is None:
            return
        try:
            self._copy_image_to_clipboard(img)
            self.root.destroy()
            print('✅ 截图已复制到剪贴板')
        except Exception as e:
            print(f'⚠ 复制图片到剪贴板失败: {e}')
            self._show_ocr_status('复制图片失败')
            self.root.after(1500, self._hide_ocr_status)
            return
        if self._on_done:
            try:
                self._on_done(True, img)
            except Exception as e:
                print(f'⚠ 截图完成回调失败: {e}')

    def _copy_image_to_clipboard(self, img):
        """把 PIL Image 写入系统剪贴板（CF_DIB 格式），优先 win32clipboard"""
        import io
        try:
            import win32clipboard
            # PIL Image 转 DIB（去掉 BMP 文件头，保留信息头+像素）
            buf = io.BytesIO()
            img.convert('RGB').save(buf, 'BMP')
            bmp = buf.getvalue()
            dib = bmp[14:]  # 去掉 BITMAPFILEHEADER(14字节)，得到 BITMAPINFOHEADER+像素
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(
                    win32clipboard.CF_DIB, dib)
            finally:
                win32clipboard.CloseClipboard()
            return
        except Exception:
            pass
        # 回退：tkinter 剪贴板（先转成 PNG 字节再写入）
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        data = buf.getvalue()
        self.root.clipboard_clear()
        self.root.clipboard_append(data)
        self.root.update()

    def cancel(self):
        self._commit_text()
        self.root.destroy()
        if self._on_done:
            try:
                self._on_done(False, None)
            except Exception as e:
                print(f'⚠ 截图取消回调失败: {e}')


class ScreenshotController:
    """截图工具 API 控制器：供宿主程序（如 recorder/app.py）在已有 Tk 环境内调用。

    用法:
        ctrl = ScreenshotController(parent_root)
        ctrl.run(on_done=lambda success, img: print(success, img))
        # 宿主程序无需再 mainloop，截图工具与宿主共享事件循环。
    """

    def __init__(self, parent=None):
        self.parent = parent
        self.shot = None
        self.busy = False

    def run(self, on_done=None):
        """启动截图。on_done(success, image) 在截图结束（确定/取消）时被调用。"""
        if self.busy:
            return
        self.busy = True
        self.shot = WeChatStyleScreenshot(parent=self.parent, on_done=self._wrapped(on_done))

    def _wrapped(self, on_done):
        def wrapper(success, image):
            self.busy = False
            if on_done:
                try:
                    on_done(success, image)
                except Exception as e:
                    print(f'⚠ 截图回调异常: {e}')
        return wrapper

    def cancel(self):
        """主动取消当前截图。"""
        if self.shot is not None:
            self.shot.cancel()


def main():
    """独立运行入口：自建 Tk 根窗口并进入 mainloop。"""
    import sys
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    WeChatStyleScreenshot()


if __name__ == '__main__':
    main()
