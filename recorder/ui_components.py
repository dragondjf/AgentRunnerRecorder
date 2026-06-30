"""Recorder UI components — icon loader (Icons) and icon button (Btn)."""

import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

from recorder.theme import C, BTN_SIZE, get_resample

_RESAMPLE = get_resample()


class Icons:
    """Load and cache PNG icons as PhotoImage.

    Priority: color/ subdirectory > parent directory.
    """

    _cache: dict[str, ImageTk.PhotoImage] = {}
    _dir: Path = Path(__file__).parent.parent / "images" / "icons_64"
    _color_dir: Path = _dir / "color"

    @classmethod
    def get(cls, name: str, size: int = BTN_SIZE) -> ImageTk.PhotoImage:
        key = f"{name}@{size}"
        if key not in cls._cache:
            color_path = cls._color_dir / f"{name}.png"
            if color_path.exists():
                img = Image.open(color_path)
            else:
                img = Image.open(cls._dir / f"{name}.png")
            img = img.resize((size, size), _RESAMPLE)
            cls._cache[key] = ImageTk.PhotoImage(img)
        return cls._cache[key]

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached icons (useful for theme switching in future)."""
        cls._cache.clear()


class Btn(tk.Label):
    """Uniform icon button: Label + PhotoImage, hover bg switch + tooltip."""

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

    def set_tooltip(self, text: str):
        self._tooltip_text = text

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
