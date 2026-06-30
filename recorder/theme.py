"""Recorder UI theme constants — dark theme color palette & sizing."""

from pathlib import Path

# Pillow 10+ 用 LANCZOS，旧版用 ANTIALIAS
from PIL import Image
_RESAMPLE = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", None))


class C:
    """Dark theme color palette."""
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


# Sizing
BTN_SIZE   = 36   # All buttons uniform display size
BTN_GAP    = 8    # Button spacing


def get_resample():
    """Return the best image resampling filter for current Pillow version."""
    return _RESAMPLE
