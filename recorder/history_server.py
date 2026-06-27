"""
AgentRunner Recorder — Web History Server
Serves recording history with list/detail views.
Lightweight single-thread HTTP server, no external dependencies.
"""

import io
import json
import mimetypes
import os
import re
import socketserver
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

from recorder.platform_utils import open_file, open_folder, get_default_recordings_dir

# ── UIRecorderCore 桥接（惰性导入，避免启动时加载 Flask 依赖） ──
_urc_converter = None
# ── GuiRunner 配置（由 recorder_app 设置） ──
_guirunner_url = "http://127.0.0.1:60000"
def _resolve_path(rel_path: str) -> str | None:
    """Resolve a relative web path to an absolute filesystem path, preventing traversal."""
    safe = os.path.normpath(rel_path).lstrip(os.sep)
    abs_path = os.path.join(RECORDINGS_ROOT, safe)
    abs_path = os.path.normpath(abs_path)
    if not abs_path.startswith(os.path.normpath(RECORDINGS_ROOT)):
        return None
    return abs_path


def _get_converter():
    global _urc_converter
    if _urc_converter is None:
        from recorder.urc_bridge import RecordingConverter, URC_BASE
        _urc_converter = (RecordingConverter, URC_BASE)
    return _urc_converter


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

RECORDINGS_ROOT = os.environ.get(
    "SCREENRECORDINGS_DIR",
    get_default_recordings_dir(),
)
PORT_RANGE = range(8080, 8091)


def _to_web_path(path: str) -> str:
    """Convert an absolute Windows path to a web-relative path.

    E.g. 'C:/Users/YFJZ/Videos/ScreenRecordings/recording_X/inputs/vid.mp4'
         -> 'recording_X/inputs/vid.mp4'

    If the path is outside RECORDINGS_ROOT, returns a forward-slash version
    of the original (fallback for edge cases).
    """
    norm_root = os.path.normpath(RECORDINGS_ROOT)
    norm_path = os.path.normpath(path)
    if norm_path.startswith(norm_root):
        rel = os.path.relpath(norm_path, norm_root)
    else:
        rel = path
    return rel.replace(os.sep, "/")


_server: "HistoryServer | None" = None


# ═══════════════════════════════════════════════════════════════
# Data scanning
# ═══════════════════════════════════════════════════════════════

def _scan_recordings() -> list:
    """Scan RECORDINGS_ROOT and return sorted recording list (newest first)."""
    items = []
    base = Path(RECORDINGS_ROOT)
    if not base.is_dir():
        return items

    for d in sorted(base.iterdir()):
        if not d.is_dir() or not d.name.startswith("recording_"):
            continue
        info = _parse_recording(d)
        items.append(info)

    # Newest first
    items.sort(key=lambda x: x["created_ts"], reverse=True)
    # Assign sequence numbers (1-based, reversed so newest = highest)
    for i, item in enumerate(reversed(items), 1):
        item["seq"] = i
    return items


def _parse_recording(dirpath: Path) -> dict:
    """Parse a single recording directory into metadata dict."""
    name = dirpath.name
    inputs = dirpath / "inputs"

    info = {
        "id": name,
        "dir": str(dirpath),
        "name": name,
        "created": "",
        "created_ts": 0,
        "duration": "",
        "duration_sec": 0,
        "events": 0,
        "screenshots": 0,
        "video_size": 0,
        "video_file": "",
        "reports": {},
        "thumbnail": "",
        "valid": False,
    }

    # Parse directory name: recording_YYYYMMDD_HHMMSS
    m = re.match(r"recording_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", name)
    if m:
        parts = m.groups()
        dt_str = f"{parts[0]}-{parts[1]}-{parts[2]} {parts[3]}:{parts[4]}:{parts[5]}"
        info["created"] = dt_str
        try:
            info["created_ts"] = datetime.strptime(
                f"{parts[0]}{parts[1]}{parts[2]}{parts[3]}{parts[4]}{parts[5]}",
                "%Y%m%d%H%M%S",
            ).timestamp()
        except ValueError:
            pass

    if not inputs.is_dir():
        return info

    # Scan files
    log_events = []
    ss_dir = inputs / "screenshots"

    for f in inputs.iterdir():
        if f.is_file():
            ext = f.suffix.lower()
            fn = f.name
            if ext == ".mp4":
                info["video_size"] = f.stat().st_size
                info["video_file"] = str(f)
            elif ext == ".txt" and fn.startswith("input_log"):
                try:
                    log_events = _parse_log_file(f)
                    info["events"] = len(log_events)
                except Exception:
                    pass
            elif fn.startswith("report_"):
                fmt = ext.lstrip(".")
                info["reports"][fmt] = str(f)

    # Screenshots
    if ss_dir.is_dir():
        ss_files = sorted([f for f in ss_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")])
        info["screenshots"] = len(ss_files)
        if ss_files:
            info["thumbnail"] = str(ss_files[0])

    # Duration from log timestamps
    if log_events:
        first_ts = log_events[0].get("timestamp", "00:00:00.000")
        last_ts = log_events[-1].get("timestamp", "00:00:00.000")
        info["duration"] = f"{first_ts} ~ {last_ts}"
        try:
            sec1 = _ts_to_sec(first_ts)
            sec2 = _ts_to_sec(last_ts)
            info["duration_sec"] = round(sec2 - sec1, 1)
        except Exception:
            pass

    info["valid"] = inputs.is_dir()
    return info


def _parse_log_file(filepath: Path) -> list:
    """Read input log and return list of event dicts."""
    events = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _ts_to_sec(ts: str) -> float:
    """Convert 'HH:MM:SS.mmm' to seconds."""
    parts = ts.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def _fmt_size(size: int) -> str:
    """Format bytes to human readable."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    else:
        return f"{size / 1024 / 1024 / 1024:.1f} GB"


# MP4 faststart cache: {abs_path: reorganized_bytes}
def _scan_screenshots(inputs_dir: str) -> list:
    """Return list of screenshot file dicts for detail view."""
    ss_dir = Path(inputs_dir) / "screenshots"
    log_file = None
    inputs = Path(inputs_dir)

    for f in inputs.iterdir():
        if f.is_file() and f.name.startswith("input_log"):
            log_file = f
            break

    log_events = _parse_log_file(log_file) if log_file else []

    screenshots = []
    if ss_dir.is_dir():
        for f in sorted(ss_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                # Find matching event by step number from filename
                step_num = 0
                m = re.match(r"(\d+)", f.name)
                if m:
                    step_num = int(m.group(1))

                event = None
                screenshot_events = [e for e in log_events if "screenshot" in e]
                if step_num <= len(screenshot_events):
                    event = screenshot_events[step_num - 1] if step_num > 0 else None

                screenshots.append({
                    "file": str(f),
                    "name": f.name,
                    "step": step_num,
                    "timestamp": event.get("timestamp", "") if event else "",
                    "message": event.get("message", "") if event else "",
                    "window": event.get("window", "") if event else "",
                })

    return screenshots


# ═══════════════════════════════════════════════════════════════
# HTML templates
# ═══════════════════════════════════════════════════════════════




def _html_list_page(recordings: list, page: int = 1, total_pages: int = 1, total: int = 0, view_mode: str = "card") -> str:
    """Generate the history list page HTML — Apifox design with light/dark theme, card/list modes, pagination."""
    cards_html = ""
    for r in recordings:
        if r["thumbnail"]:
            thumb_src = _to_web_path(r["thumbnail"])
            thumb_html = f'<img src="/file/{thumb_src}" alt="screenshot" class="thumb">'
        else:
            thumb_html = '<div class="thumb-placeholder">N/A</div>'

        dur = r["duration_sec"]
        if dur > 0:
            mins = int(dur) // 60
            secs = int(dur) % 60
            dur_text = f"{mins:02d}:{secs:02d}"
        else:
            dur_text = "--:--"

        badges = ""
        for fmt, label, color in [("html", "HTML", "indigo"), ("md", "MD", "green"), ("docx", "Word", "lavender"), ("json", "JSON", "violet")]:
            if fmt in r["reports"]:
                badges += f'<span class="badge badge-{color}">{label}</span>'

        vid_sz = _fmt_size(r["video_size"]) if r["video_size"] > 0 else "-"

        # Card mode
        card_html = f"""
        <div class="recording-item" data-id="{r['id']}">
          <div class="item-thumb">
            {thumb_html}
            <div class="item-seq">#{r['seq']:03d}</div>
          </div>
          <div class="item-body">
            <div class="item-row item-row-top">
              <span class="item-time">{r['created']}</span>
              <div class="item-meta">
                <span class="meta-chip">{dur_text}</span>
                <span class="meta-chip">{r['screenshots']} 截图</span>
                <span class="meta-chip">{r['events']} 事件</span>
                <span class="meta-chip">{vid_sz}</span>
              </div>
            </div>
            <div class="item-row item-tags">{badges if badges else '<span class="tag-empty">无报告</span>'}</div>
          </div>
          <div class="item-actions">
            <button class="btn btn-ghost btn-detail" onclick="event.stopPropagation(); location.href='/recording/{r['id']}'" title="查看详情">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              <span>详情</span>
            </button>
            <button class="btn btn-ghost btn-edit" onclick="event.stopPropagation(); editRecording('{r['id']}')" title="编辑">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              <span>编辑</span>
            </button>
            <button class="btn btn-ghost btn-folder" onclick="event.stopPropagation(); openFolder('{r['id']}')" title="打开文件夹">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              <span>文件夹</span>
            </button>
            <div class="export-wrap">
              <button class="btn btn-ghost btn-export" onclick="event.stopPropagation(); toggleExportMenu(this)" title="导出">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                <span>导出</span>
              </button>
              <div class="export-menu">
                <a onclick="event.stopPropagation(); exportFormat('{r['id']}','video')">Video</a>
                <a onclick="event.stopPropagation(); exportFormat('{r['id']}','md')">Markdown</a>
                <a onclick="event.stopPropagation(); exportFormat('{r['id']}','json')">JSON</a>
                <a onclick="event.stopPropagation(); exportFormat('{r['id']}','html')">HTML</a>
                <a onclick="event.stopPropagation(); exportFormat('{r['id']}','docx')">Word</a>
                <a onclick="event.stopPropagation(); exportFormat('{r['id']}','zip')">ZIP</a>
              </div>
            </div>
          </div>
        </div>"""
        cards_html += card_html

    # Pagination
    pagination_html = ""
    if total_pages > 1:
        pages_html = ""
        # Previous
        prev_disabled = "disabled" if page <= 1 else ""
        pages_html += f'<button class="page-btn" onclick="goPage({page-1})" {prev_disabled}>&lsaquo;</button>'
        # Page numbers
        start_p = max(1, page - 2)
        end_p = min(total_pages, page + 2)
        if start_p > 1:
            pages_html += f'<button class="page-btn" onclick="goPage(1)">1</button>'
            if start_p > 2:
                pages_html += '<span class="page-ellipsis">...</span>'
        for p in range(start_p, end_p + 1):
            active = "active" if p == page else ""
            pages_html += f'<button class="page-btn {active}" onclick="goPage({p})">{p}</button>'
        if end_p < total_pages:
            if end_p < total_pages - 1:
                pages_html += '<span class="page-ellipsis">...</span>'
            pages_html += f'<button class="page-btn" onclick="goPage({total_pages})">{total_pages}</button>'
        # Next
        next_disabled = "disabled" if page >= total_pages else ""
        pages_html += f'<button class="page-btn" onclick="goPage({page+1})" {next_disabled}>&rsaquo;</button>'

        pagination_html = f"""
        <div class="pagination">
          <div class="page-info">第 {page}/{total_pages} 页，共 {total} 条</div>
          <div class="page-btns">{pages_html}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>录制历史 — AgentRunner Recorder</title>
<style>
/* ========== Design Tokens (Dark) ========== */
:root {{
  --color-canvas: #0f1117;
  --color-surface: #181b23;
  --color-surface2: #1f2330;
  --color-surface3: #282d3e;
  --color-border: #2a2e3b;
  --color-hairline: #1e2230;
  --color-text: #e8edf5;
  --color-text-secondary: #8b95a8;
  --color-text-muted: #5c6478;
  --color-indigo: #6366F1;
  --color-violet: #7C6EF5;
  --color-lavender: #A58CFF;
  --color-lavender-wash: rgba(99,102,241,0.10);
  --color-lavender-border: rgba(99,102,241,0.25);
  --color-green: #3fb950;
  --color-red: #f85149;
  --color-orange: #f0883e;
  --gradient-brand: linear-gradient(135deg, #6366F1, #A58CFF);
  --font-primary: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: "SF Mono", "Fira Code", "Consolas", monospace;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-default: 8px;
  --radius-lg: 12px;
  --shadow-xs: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.25);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.3);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.4);
  --shadow-glow: 0 4px 20px rgba(99,102,241,0.15);
}}

/* ========== Design Tokens (Light) ========== */
[data-theme="light"] {{
  --color-canvas: #f5f7fa;
  --color-surface: #ffffff;
  --color-surface2: #f0f2f5;
  --color-surface3: #e8ecf1;
  --color-border: #d0d5dd;
  --color-hairline: #e2e6ed;
  --color-text: #1a1d23;
  --color-text-secondary: #5c6478;
  --color-text-muted: #9ca3af;
  --color-indigo: #4f46e5;
  --color-violet: #7c3aed;
  --color-lavender: #8b5cf6;
  --color-lavender-wash: rgba(79,70,229,0.08);
  --color-lavender-border: rgba(79,70,229,0.20);
  --color-green: #16a34a;
  --color-red: #dc2626;
  --color-orange: #ea580c;
  --gradient-brand: linear-gradient(135deg, #4f46e5, #8b5cf6);
  --shadow-xs: 0 1px 2px rgba(0,0,0,0.06);
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.12);
  --shadow-glow: 0 4px 20px rgba(79,70,229,0.12);
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: var(--font-primary);
  background: var(--color-canvas);
  color: var(--color-text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  transition: background 0.3s, color 0.3s;
}}
a {{ color: var(--color-indigo); text-decoration: none; }}
a:hover {{ color: var(--color-violet); }}
button {{ font-family: inherit; cursor: pointer; outline: none; }}
::selection {{ background: var(--color-lavender-wash); color: var(--color-indigo); }}

/* ========== Nav ========== */
.nav {{
  position: sticky; top: 0; z-index: 100;
  height: 60px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-hairline);
  display: flex; align-items: center;
  padding: 0 28px;
  gap: 16px;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}
.nav-brand {{
  display: flex; align-items: center; gap: 10px;
  font-size: 16px; font-weight: 700;
  color: var(--color-text);
  white-space: nowrap;
  letter-spacing: -0.01em;
}}
.nav-brand-dot {{
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--gradient-brand);
}}
.nav-count {{
  font-size: 11px; font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-surface2);
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid var(--color-hairline);
}}
.nav-search {{
  flex: 1; max-width: 340px;
  position: relative;
}}
.nav-search input {{
  width: 100%;
  height: 34px;
  padding: 0 14px 0 36px;
  background: var(--color-canvas);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.3s;
}}
.nav-search input:focus {{
  border-color: var(--color-indigo);
  box-shadow: 0 0 0 3px var(--color-lavender-wash);
  background: var(--color-surface);
}}
.nav-search-icon {{
  position: absolute; left: 12px; top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-muted);
  font-size: 14px;
  pointer-events: none;
}}
.nav-actions {{
  display: flex; align-items: center; gap: 6px;
  margin-left: auto;
}}

/* ========== View Toggle ========== */
.view-toggle {{
  display: flex; gap: 2px;
  background: var(--color-surface2);
  padding: 3px;
  border-radius: var(--radius-default);
  border: 1px solid var(--color-hairline);
}}
.view-btn {{
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px;
  font-size: 11px; font-weight: 500;
  border: none; border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s;
}}
.view-btn:hover {{ color: var(--color-text); }}
.view-btn.active {{
  background: var(--color-lavender-wash);
  color: var(--color-indigo);
  box-shadow: var(--shadow-xs);
}}

/* ========== Theme Toggle ========== */
.theme-btn {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s;
}}
.theme-btn:hover {{
  border-color: var(--color-indigo);
  color: var(--color-indigo);
  background: var(--color-lavender-wash);
}}

/* ========== Filter Tabs ========== */
.filter-bar {{
  position: sticky; top: 60px; z-index: 99;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 28px;
  background: var(--color-canvas);
  border-bottom: 1px solid var(--color-hairline);
}}
.filter-tabs {{
  display: flex; gap: 2px;
  background: var(--color-surface2);
  padding: 3px;
  border-radius: var(--radius-default);
}}
.filter-tab {{
  padding: 5px 14px;
  font-size: 12px; font-weight: 500;
  border: none; border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s;
}}
.filter-tab:hover {{ color: var(--color-text); }}
.filter-tab.active {{
  background: var(--color-lavender-wash);
  color: var(--color-indigo);
  box-shadow: var(--shadow-xs);
}}
.filter-count {{
  font-size: 11px; color: var(--color-text-muted);
  margin-left: auto;
}}

/* ========== Container ========== */
.container {{
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px 28px;
}}
.empty {{
  text-align: center;
  padding: 80px 20px;
  color: var(--color-text-muted);
  font-size: 14px;
}}

/* ========== Card Mode ========== */
.recording-item {{
  display: flex;
  background: var(--color-surface);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  margin-bottom: 10px;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.3s;
  overflow: hidden;
}}
.recording-item:hover {{
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}}
.item-thumb {{
  width: 150px; min-height: 88px;
  flex-shrink: 0;
  overflow: hidden;
  background: var(--color-surface2);
  display: flex; align-items: center; justify-content: center;
  position: relative;
}}
.item-thumb img {{
  width: 100%; height: 100%; object-fit: cover;
}}
.thumb-placeholder {{
  color: var(--color-text-muted);
  font-size: 11px;
}}
.item-seq {{
  position: absolute;
  top: 6px; left: 6px;
  font-size: 10px; font-weight: 700;
  font-family: var(--font-mono);
  color: #fff;
  background: rgba(0,0,0,0.6);
  padding: 1px 6px;
  border-radius: 4px;
  backdrop-filter: blur(4px);
}}
.item-body {{
  flex: 1;
  min-width: 0;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}}
.item-row {{
  display: flex; align-items: center; gap: 8px;
}}
.item-row-top {{
  flex-wrap: wrap;
}}
.item-time {{
  font-size: 12px; font-weight: 500;
  color: var(--color-text-secondary);
}}
.item-meta {{
  display: flex; align-items: center; gap: 4px;
  flex-wrap: wrap;
}}
.meta-chip {{
  font-size: 10px; font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-surface2);
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--color-hairline);
}}
.item-tags {{
  display: flex; gap: 4px; flex-wrap: wrap;
}}
.badge {{
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  letter-spacing: 0.02em;
}}
.badge-indigo {{ background: var(--color-lavender-wash); color: var(--color-indigo); }}
.badge-green {{ background: rgba(63,185,80,0.12); color: var(--color-green); }}
.badge-lavender {{ background: rgba(165,140,255,0.12); color: var(--color-lavender); }}
.badge-violet {{ background: rgba(124,110,245,0.12); color: var(--color-violet); }}
.tag-empty {{ font-size: 11px; color: var(--color-text-muted); opacity: 0.5; }}

/* ========== Actions ========== */
.item-actions {{
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 2px;
  padding: 0 14px;
  border-left: 1px solid var(--color-hairline);
  flex-shrink: 0;
}}
.btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  font-size: 11px;
  font-weight: 500;
}}
.btn-ghost {{
  height: 32px;
  padding: 0 10px;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  white-space: nowrap;
}}
.btn-ghost:hover {{
  background: var(--color-surface2);
  color: var(--color-text);
}}
.btn-ghost.btn-detail:hover {{ color: var(--color-indigo); background: var(--color-lavender-wash); }}
.btn-ghost.btn-edit:hover {{ color: var(--color-violet); }}
.btn-ghost.btn-folder:hover {{ color: var(--color-orange); }}
.btn-ghost.btn-export:hover {{ color: var(--color-indigo); }}

/* ========== Export Dropdown ========== */
.export-wrap {{
  position: relative;
  display: inline-flex;
}}
.export-menu {{
  display: none;
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-default);
  min-width: 140px;
  z-index: 9999;
  box-shadow: var(--shadow-lg);
  padding: 4px;
}}
.export-menu.show {{ display: block; }}
.export-menu a {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
  text-decoration: none;
  cursor: pointer;
  white-space: nowrap;
  border-radius: var(--radius-sm);
  transition: all 0.12s;
}}
.export-menu a:hover {{
  background: var(--color-lavender-wash);
  color: var(--color-indigo);
}}

/* ========== Pagination ========== */
.pagination {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 24px 0 40px;
}}
.page-info {{
  font-size: 12px;
  color: var(--color-text-muted);
}}
.page-btns {{
  display: flex;
  align-items: center;
  gap: 4px;
}}
.page-btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}}
.page-btn:hover {{
  border-color: var(--color-indigo);
  color: var(--color-indigo);
  background: var(--color-lavender-wash);
}}
.page-btn.active {{
  border-color: var(--color-indigo);
  background: var(--color-indigo);
  color: #fff;
}}
.page-btn:disabled {{
  opacity: 0.3;
  cursor: not-allowed;
}}
.page-ellipsis {{
  padding: 0 4px;
  color: var(--color-text-muted);
  font-size: 13px;
}}

/* ========== List Mode ========== */
.list-mode .recording-item {{
  flex-direction: row;
  align-items: center;
  padding: 0;
}}
.list-mode .item-thumb {{
  width: 60px; min-height: 44px;
}}
.list-mode .item-seq {{
  font-size: 9px; top: 3px; left: 3px;
}}
.list-mode .item-body {{
  flex-direction: row;
  align-items: center;
  padding: 10px 16px;
  gap: 16px;
}}
.list-mode .item-row-top {{
  flex: 1;
}}
.list-mode .item-time {{
  font-size: 12px;
  min-width: 140px;
}}
.list-mode .item-meta {{
  gap: 6px;
}}
.list-mode .item-tags {{
  flex-shrink: 0;
}}
.list-mode .item-actions {{
  padding: 0 10px;
}}
.list-mode .btn-ghost {{
  height: 28px;
  padding: 0 8px;
  font-size: 10px;
}}
.list-mode .btn-ghost svg {{
  width: 12px; height: 12px;
}}

/* ========== Responsive ========== */
@media (max-width: 768px) {{
  .nav {{ padding: 0 16px; gap: 10px; }}
  .nav-search {{ max-width: 180px; }}
  .container {{ padding: 16px; }}
  .filter-bar {{ padding: 8px 16px; flex-wrap: wrap; }}
  .item-thumb {{ width: 100px; }}
  .item-actions {{ flex-direction: column; padding: 8px; gap: 4px; }}
  .btn-ghost {{ height: 28px; padding: 0 6px; font-size: 10px; }}
  .btn-ghost span {{ display: none; }}
  .pagination {{ flex-direction: column; gap: 8px; }}
}}

/* ========== Header button ========== */
.btn-header {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  font-size: 12px; font-weight: 500;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}}
.btn-header:hover {{
  border-color: var(--color-indigo);
  color: var(--color-indigo);
  background: var(--color-lavender-wash);
}}

/* ========== Animations ========== */
@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
.recording-item {{
  animation: fadeIn 0.25s ease-out;
}}
</style>
</head>
<body>

<div class="nav">
  <div class="nav-brand">
    <div class="nav-brand-dot"></div>
    录制历史
  </div>
  <span class="nav-count">{total} 次录制</span>
  <div class="nav-search">
    <span class="nav-search-icon">&#x2315;</span>
    <input type="text" id="search" placeholder="搜索时间、编号..." oninput="filterCards()">
  </div>
  <div class="nav-actions">
    <div class="view-toggle">
      <button class="view-btn {'active' if view_mode == 'card' else ''}" onclick="setViewMode('card')" title="卡片模式">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        卡片
      </button>
      <button class="view-btn {'active' if view_mode == 'list' else ''}" onclick="setViewMode('list')" title="列表模式">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
        列表
      </button>
    </div>
    <button class="theme-btn" onclick="toggleTheme()" title="切换主题">
      <svg class="theme-icon-dark" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg class="theme-icon-light" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
    </button>
    <button class="btn-header" onclick="window.location.href='/open-folder?root=1'">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      目录
    </button>
  </div>
</div>

<div class="filter-bar">
  <div class="filter-tabs">
    <span class="filter-tab active" data-filter="all" onclick="setFilter(this)">全部</span>
    <span class="filter-tab" data-filter="today" onclick="setFilter(this)">今天</span>
    <span class="filter-tab" data-filter="week" onclick="setFilter(this)">本周</span>
    <span class="filter-tab" data-filter="report" onclick="setFilter(this)">有报告</span>
  </div>
  <span class="filter-count">{total} 条记录</span>
</div>

<div class="container" id="card-list">
  {cards_html if recordings else '<div class="empty">暂无录制记录</div>'}
</div>

{pagination_html}

<script>
// ========== Theme ==========
function toggleTheme() {{
  var html = document.documentElement;
  var current = html.getAttribute("data-theme");
  html.setAttribute("data-theme", current === "light" ? "dark" : "light");
  localStorage.setItem("history-theme", html.getAttribute("data-theme"));
}}
(function() {{
  var saved = localStorage.getItem("history-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
}})();

// ========== View Mode ==========
function setViewMode(mode) {{
  var container = document.getElementById("card-list");
  if (mode === "list") {{
    container.classList.add("list-mode");
  }} else {{
    container.classList.remove("list-mode");
  }}
  document.querySelectorAll(".view-btn").forEach(function(b) {{ b.classList.remove("active"); }});
  document.querySelectorAll(".view-btn[onclick*='" + mode + "']").forEach(function(b) {{ b.classList.add("active"); }});
  localStorage.setItem("history-view", mode);
}}
(function() {{
  var saved = localStorage.getItem("history-view");
  if (saved) setViewMode(saved);
}})();

// ========== Search ==========
function filterCards() {{
  var q = document.getElementById("search").value.toLowerCase();
  var items = document.querySelectorAll(".recording-item");
  items.forEach(function(c) {{
    var text = c.textContent.toLowerCase();
    c.style.display = text.indexOf(q) >= 0 ? "" : "none";
  }});
}}

// ========== Actions ==========
function editRecording(id) {{
  window.open("/edit-recording/" + encodeURIComponent(id), "_blank");
}}
function openFolder(id) {{
  window.location.href = "/open-folder?id=" + encodeURIComponent(id);
}}
function toggleExportMenu(btn) {{
  var menu = btn.parentElement.querySelector('.export-menu');
  if (menu) menu.classList.toggle('show');
}}
function exportFormat(id, fmt) {{
  window.open("/export-recording/" + encodeURIComponent(id) + "?format=" + fmt, "_blank");
}}
document.addEventListener('click', function(e) {{
  document.querySelectorAll('.export-menu.show').forEach(function(m) {{ m.classList.remove('show'); }});
}});

// ========== Filter ==========
var currentFilter = "all";
function setFilter(el) {{
  document.querySelectorAll(".filter-tab").forEach(function(c) {{ c.classList.remove("active"); }});
  el.classList.add("active");
  currentFilter = el.dataset.filter;
  applyFilter();
}}
function applyFilter() {{
  var items = document.querySelectorAll(".recording-item");
  var now = new Date();
  items.forEach(function(c) {{
    if (currentFilter === "all") {{ c.style.display = ""; return; }}
    if (currentFilter === "today") {{
      var timeEl = c.querySelector(".item-time");
      if (!timeEl) return;
      var t = timeEl.textContent.trim();
      c.style.display = t.indexOf(now.getFullYear()+"-"+String(now.getMonth()+1).padStart(2,"0")+"-"+String(now.getDate()).padStart(2,"0")) >= 0 ? "" : "none";
      return;
    }}
    if (currentFilter === "week") {{
      var timeEl = c.querySelector(".item-time");
      if (!timeEl) return;
      var t = timeEl.textContent.trim().replace(/-/g, "/");
      var cardDate = new Date(t);
      var weekAgo = new Date(now.getTime() - 7*24*3600*1000);
      c.style.display = cardDate >= weekAgo ? "" : "none";
      return;
    }}
    if (currentFilter === "report") {{
      c.style.display = c.querySelector(".badge") ? "" : "none";
      return;
    }}
  }});
}}

// ========== Pagination ==========
function goPage(p) {{
  var params = new URLSearchParams(window.location.search);
  params.set("page", p);
  window.location.search = params.toString();
}}
</script>
</body>
</html>"""




def _html_detail_page(rec: dict) -> str:
    """Generate the recording detail page HTML — Apifox design with light/dark theme."""
    screenshots = _scan_screenshots(os.path.join(rec["dir"], "inputs"))

    dur = rec["duration_sec"]
    mins = int(dur) // 60
    secs = int(dur) % 60
    dur_text = f"{mins:02d}:{secs:02d}" if dur > 0 else "--:--"

    # Screenshot grid
    ss_html = ""
    for ss in screenshots:
        src = _to_web_path(ss["file"])
        msg = (ss["message"] or "")[:80]
        ts = (ss["timestamp"] or "")[:12]
        ss_html += f"""
        <div class="ss-card" onclick="openLightbox('/file/{src}')">
          <img src="/file/{src}" alt="{ss['name']}" loading="lazy">
          <div class="ss-info">
            <span class="ss-step">#{ss['step']:04d}</span>
            <span class="ss-ts">{ts}</span>
            <span class="ss-msg">{msg}</span>
          </div>
        </div>"""

    # File list
    files_html = ""
    fmt_config = [
        ("html", "HTML 报告", "indigo"),
        ("md", "Markdown", "green"),
        ("docx", "Word 文档", "lavender"),
        ("json", "JSON 数据", "violet"),
    ]
    for fmt, label, color in fmt_config:
        fpath = rec["reports"].get(fmt, "")
        if fpath:
            web = _to_web_path(fpath)
            files_html += f"""
            <div class="file-item" onclick="openFile('/file/{web}')">
              <span class="file-dot dot-{color}"></span>
              <span class="file-name">report.{fmt}</span>
            </div>"""

    # Video
    vid_html = ""
    if rec["video_file"]:
        vid_src = _to_web_path(rec["video_file"])
        vid_sz = _fmt_size(rec["video_size"])
        vid_html = f"""
        <div class="video-section">
          <div class="video-header">
            <span class="file-dot dot-orange"></span>
            <span class="file-name">{os.path.basename(rec['video_file'])}</span>
            <span class="vid-size">{vid_sz}</span>
          </div>
        </div>"""

    # Action buttons
    actions_html = ""
    html_p = rec["reports"].get("html", "")
    if html_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(html_p)}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>\u6253\u5f00 HTML \u62a5\u544a</button>\n"""
    md_p = rec["reports"].get("md", "")
    if md_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(md_p)}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>\u6253\u5f00 Markdown</button>\n"""
    docx_p = rec["reports"].get("docx", "")
    if docx_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(docx_p)}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>\u6253\u5f00 Word</button>\n"""
    json_p = rec["reports"].get("json", "")
    if json_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(json_p)}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>\u6253\u5f00 JSON</button>\n"""
    if rec["video_file"]:
        vid_abs = rec["video_file"].replace(os.sep, "/")
        actions_html += f'''<button class="action-item" onclick="openLocal('{vid_abs}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>\u64ad\u653e\u89c6\u9891</button>\n'''
    actions_html += f"""<button class="action-item" onclick="openFolder('{rec['id']}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>\u6253\u5f00\u6587\u4ef6\u5939</button>\n"""
    actions_html += f"""<button class="action-item" onclick="editRecording('{rec['id']}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>\u5728 UIRecorderCore \u4e2d\u7f16\u8f91</button>\n"""
    actions_html += f"""<button class="action-item" onclick="exportRecording('{rec['id']}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>\u5bfc\u51fa\u6240\u6709\u683c\u5f0f</button>\n"""
    for fmt, label in [("video","Video"),("md","Markdown"),("json","JSON"),("html","HTML"),("docx","Word"),("zip","ZIP"),("guirunner","GuiRunner")]:
        actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','{fmt}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>\u5bfc\u51fa {label}</button>\n"""
    actions_html += f"""<button class="action-item danger" onclick="confirmDelete('{rec['id']}')">\n          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>\u5220\u9664\u672c\u6b21\u5f55\u5236</button>\n"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>#{rec['seq']:03d} — AgentRunner Recorder</title>
<style>
/* ========== Design Tokens (Dark) ========== */
:root {{
  --color-canvas: #0f1117;
  --color-surface: #181b23;
  --color-surface2: #1f2330;
  --color-surface3: #282d3e;
  --color-border: #2a2e3b;
  --color-hairline: #1e2230;
  --color-text: #e8edf5;
  --color-text-secondary: #8b95a8;
  --color-text-muted: #5c6478;
  --color-indigo: #6366F1;
  --color-violet: #7C6EF5;
  --color-lavender: #A58CFF;
  --color-lavender-wash: rgba(99,102,241,0.10);
  --color-lavender-border: rgba(99,102,241,0.25);
  --color-green: #3fb950;
  --color-red: #f85149;
  --color-orange: #f0883e;
  --gradient-brand: linear-gradient(135deg, #6366F1, #A58CFF);
  --font-primary: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: "SF Mono", "Fira Code", "Consolas", monospace;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-default: 8px;
  --radius-lg: 12px;
  --shadow-xs: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.25);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.3);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.4);
}}

/* ========== Design Tokens (Light) ========== */
[data-theme="light"] {{
  --color-canvas: #f5f7fa;
  --color-surface: #ffffff;
  --color-surface2: #f0f2f5;
  --color-surface3: #e8ecf1;
  --color-border: #d0d5dd;
  --color-hairline: #e2e6ed;
  --color-text: #1a1d23;
  --color-text-secondary: #5c6478;
  --color-text-muted: #9ca3af;
  --color-indigo: #4f46e5;
  --color-violet: #7c3aed;
  --color-lavender: #8b5cf6;
  --color-lavender-wash: rgba(79,70,229,0.08);
  --color-lavender-border: rgba(79,70,229,0.20);
  --color-green: #16a34a;
  --color-red: #dc2626;
  --color-orange: #ea580c;
  --gradient-brand: linear-gradient(135deg, #4f46e5, #8b5cf6);
  --shadow-xs: 0 1px 2px rgba(0,0,0,0.06);
  --shadow-sm: 0 2px 8px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.12);
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ height: 100%; }}
body {{
  font-family: var(--font-primary);
  background: var(--color-canvas);
  color: var(--color-text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  transition: background 0.3s, color 0.3s;
}}
a {{ color: var(--color-indigo); text-decoration: none; }}
a:hover {{ color: var(--color-violet); }}
button {{ font-family: inherit; cursor: pointer; outline: none; }}
::selection {{ background: var(--color-lavender-wash); color: var(--color-indigo); }}

/* ========== App Layout ========== */
.app {{
  display: flex;
  height: 100vh;
}}

/* ========== Sidebar ========== */
.sidebar {{
  width: 240px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-right: 1px solid var(--color-hairline);
  display: flex;
  flex-direction: column;
  z-index: 100;
}}
.sidebar-header {{
  padding: 16px 18px;
  border-bottom: 1px solid var(--color-hairline);
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.back-btn {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 500;
  color: var(--color-text-muted);
  background: none; border: none;
  padding: 6px 10px;
  border-radius: var(--radius-md);
  transition: all 0.15s;
}}
.back-btn:hover {{
  color: var(--color-indigo);
  background: var(--color-lavender-wash);
}}
.theme-btn {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s;
}}
.theme-btn:hover {{
  border-color: var(--color-indigo);
  color: var(--color-indigo);
  background: var(--color-lavender-wash);
}}
.sidebar-meta {{
  padding: 18px;
  border-bottom: 1px solid var(--color-hairline);
}}
.rec-id {{
  font-size: 18px; font-weight: 700;
  color: var(--color-indigo);
  font-family: var(--font-mono);
}}
.rec-time {{
  font-size: 12px; color: var(--color-text-muted);
  margin-top: 2px;
}}
.meta-stats {{
  margin-top: 14px;
  display: flex; flex-direction: column; gap: 8px;
}}
.meta-stat {{
  display: flex; justify-content: space-between;
  font-size: 12px;
}}
.meta-stat .label {{ color: var(--color-text-muted); }}
.meta-stat .value {{
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--color-text);
}}
.sidebar-actions {{
  padding: 12px 14px;
  border-top: 1px solid var(--color-hairline);
  flex: 1;
  overflow-y: auto;
}}
.action-list {{
  display: flex; flex-direction: column; gap: 2px;
}}
.action-item {{
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px;
  font-size: 12px; font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.12s;
  color: var(--color-text-secondary);
  border: none;
  background: none;
  width: 100%;
  text-align: left;
}}
.action-item:hover {{
  background: var(--color-surface2);
  color: var(--color-text);
}}
.action-item.danger {{ color: var(--color-red); }}
.action-item.danger:hover {{ background: rgba(248,81,73,0.1); }}

/* ========== Center ========== */
.center {{
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}
.center-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--color-hairline);
  background: var(--color-surface);
}}
.center-title {{
  font-size: 14px; font-weight: 600;
}}
.view-toggle {{
  display: flex; gap: 4px;
  background: var(--color-surface2);
  padding: 3px;
  border-radius: var(--radius-default);
}}
.view-btn {{
  padding: 4px 12px;
  font-size: 11px; font-weight: 500;
  border: none; border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}}
.view-btn.active {{
  background: var(--color-lavender-wash);
  color: var(--color-indigo);
  box-shadow: var(--shadow-xs);
}}
.ss-grid-wrapper {{
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}}
.ss-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}}
.ss-grid.timeline {{
  grid-template-columns: 1fr;
}}
.ss-card {{
  background: var(--color-surface);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-default);
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}}
.ss-card:hover {{
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}}
.ss-card img {{
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  display: block;
}}
.timeline .ss-card img {{
  aspect-ratio: auto;
  max-height: 60vh;
}}
.ss-info {{
  padding: 8px 10px;
  display: flex; flex-direction: column; gap: 3px;
}}
.ss-step {{
  font-size: 11px; font-weight: 700;
  font-family: var(--font-mono);
  color: var(--color-indigo);
}}
.ss-ts {{
  font-size: 10px; color: var(--color-text-muted);
}}
.ss-msg {{
  font-size: 11px; color: var(--color-text-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.empty-ss {{
  text-align: center; padding: 60px 20px;
  color: var(--color-text-muted); font-size: 14px;
}}

/* ========== Right Panel ========== */
.right-panel {{
  width: 260px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-left: 1px solid var(--color-hairline);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}}
.panel-section {{
  padding: 16px 18px;
  border-bottom: 1px solid var(--color-hairline);
}}
.panel-title {{
  font-size: 11px; font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 10px;
}}
.file-item {{
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.12s;
  font-size: 12px;
  color: var(--color-text-secondary);
}}
.file-item:hover {{
  background: var(--color-surface2);
  color: var(--color-text);
}}
.file-dot {{
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.dot-indigo {{ background: var(--color-indigo); }}
.dot-green {{ background: var(--color-green); }}
.dot-lavender {{ background: var(--color-lavender); }}
.dot-violet {{ background: var(--color-violet); }}
.dot-orange {{ background: var(--color-orange); }}
.file-name {{ flex: 1; }}
.vid-size {{ font-size: 11px; color: var(--color-text-muted); }}
.video-section {{ padding: 16px 18px; }}
.video-header {{
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--color-text-secondary);
}}

/* ========== Lightbox ========== */
.lightbox {{
  display: none;
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.85);
  z-index: 9999;
  align-items: center; justify-content: center;
  cursor: zoom-out;
}}
.lightbox.active {{ display: flex; }}
.lightbox img {{
  max-width: 95vw; max-height: 95vh;
  object-fit: contain;
  border-radius: var(--radius-default);
}}

/* ========== Responsive ========== */
@media (max-width: 900px) {{
  .right-panel {{ display: none; }}
  .ss-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 600px) {{
  .sidebar {{ width: 200px; }}
  .ss-grid {{ grid-template-columns: 1fr; }}
  .center-header {{ padding: 12px 16px; }}
  .ss-grid-wrapper {{ padding: 12px 16px; }}
}}

/* ========== Toast ========== */
#toast-container {{
  position: fixed; top: 16px; right: 16px; z-index: 10000;
  display: flex; flex-direction: column; gap: 8px;
  pointer-events: none;
}}
.toast {{
  padding: 10px 18px; border-radius: 8px; font-size: 13px;
  font-family: var(--font-primary); max-width: 400px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  opacity: 0; transform: translateX(40px);
  transition: opacity 0.25s, transform 0.25s;
  pointer-events: auto;
}}
.toast.show {{ opacity: 1; transform: translateX(0); }}
.toast-info {{ background: #1e293b; color: #e2e8f0; border: 1px solid #334155; }}
.toast-success {{ background: #052e16; color: #86efac; border: 1px solid #166534; }}
.toast-error {{ background: #450a0a; color: #fca5a5; border: 1px solid #991b1b; }}
</style>
</head>
<body>
<div id="toast-container"></div>
<div class="app">
  <div class="sidebar">
    <div class="sidebar-header">
      <button class="back-btn" onclick="location.href='/'">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        \u8fd4\u56de
      </button>
      <button class="theme-btn" onclick="toggleTheme()" title="\u5207\u6362\u4e3b\u9898">
        <svg class="theme-icon-dark" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        <svg class="theme-icon-light" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      </button>
    </div>
    <div class="sidebar-meta">
      <div class="rec-id">#{rec['seq']:03d}</div>
      <div class="rec-time">{rec['created']}</div>
      <div class="meta-stats">
        <div class="meta-stat"><span class="label">\u65f6\u957f</span><span class="value">{dur_text}</span></div>
        <div class="meta-stat"><span class="label">\u4e8b\u4ef6</span><span class="value">{rec['events']} \u6761</span></div>
        <div class="meta-stat"><span class="label">\u622a\u56fe</span><span class="value">{rec['screenshots']} \u5f20</span></div>
      </div>
    </div>
    <div class="sidebar-actions">
      <div class="action-list">
        {actions_html}
      </div>
    </div>
  </div>

  <div class="center">
    <div class="center-header">
      <span class="center-title">\u622a\u56fe ({len(screenshots)})</span>
      <div class="view-toggle">
        <button class="view-btn active" onclick="setView('grid', this)">\u7f51\u683c</button>
        <button class="view-btn" onclick="setView('timeline', this)">\u65f6\u95f4\u7ebf</button>
      </div>
    </div>
    <div class="ss-grid-wrapper">
      <div class="ss-grid" id="ss-grid">
        {ss_html if screenshots else '<div class="empty-ss">本次录制无截图</div>'}
      </div>
    </div>
  </div>

  <div class="right-panel">
    <div class="panel-section">
      <div class="panel-title">\u6587\u4ef6\u5217\u8868</div>
      {files_html if files_html else '<div style="font-size:12px;color:var(--color-text-muted);">无报告文件</div>'}
    </div>
    {f'<div class="video-section">{vid_html}</div>' if vid_html else ''}
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="">
</div>

<script>
// ========== Theme ==========
function toggleTheme() {{
  var html = document.documentElement;
  var current = html.getAttribute("data-theme");
  html.setAttribute("data-theme", current === "light" ? "dark" : "light");
  localStorage.setItem("history-theme", html.getAttribute("data-theme"));
}}
(function() {{
  var saved = localStorage.getItem("history-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
}})();

// ========== View ==========
function setView(mode, btn) {{
  var grid = document.getElementById("ss-grid");
  document.querySelectorAll(".view-btn").forEach(function(b) {{ b.classList.remove("active"); }});
  btn.classList.add("active");
  grid.classList.toggle("timeline", mode === "timeline");
}}

// ========== Lightbox ==========
function openLightbox(src) {{
  document.getElementById("lightbox-img").src = src;
  document.getElementById("lightbox").classList.add("active");
}}
function closeLightbox() {{
  document.getElementById("lightbox").classList.remove("active");
}}
document.addEventListener("keydown", function(e) {{ if (e.key === "Escape") closeLightbox(); }});

// ========== Actions ==========
function openFile(url) {{ window.open(url, "_blank"); }}
function openLocal(path) {{ window.location.href = "/open-local?path=" + encodeURIComponent(path); }}
function openFolder(path) {{ window.location.href = "/open-folder?id=" + encodeURIComponent(path); }}
function editRecording(id) {{ window.open("/edit-recording/" + encodeURIComponent(id), "_blank"); }}
function exportRecording(id) {{ window.open("/export-recording/" + encodeURIComponent(id), "_blank"); }}
function exportFormat(id, fmt) {{
  if (fmt === "guirunner") {{
    showToast("\u6b63\u5728\u5bfc\u51fa GuiRunner...", "info");
    fetch("/export-recording/" + encodeURIComponent(id) + "?format=guirunner")
      .then(function(r) {{ return r.json().then(function(data) {{ return {{ok: data.ok, data: data, status: r.status}}; }}); }})
      .then(function(result) {{
        if (result.ok && result.data.ok) {{
          showToast("\u2713 \u5bfc\u51fa\u6210\u529f\uff01" + result.data.project + " \u5df2\u63a8\u9001\u5230 GuiRunner", "success");
        }} else {{
          var msg = result.data.message || "\u63a8\u9001\u5931\u8d25";
          showToast("\u2717 " + msg, "error", 5000);
        }}
      }})
      .catch(function(err) {{
        showToast("\u2717 \u8bf7\u6c42\u5931\u8d25: " + err.message, "error", 5000);
      }});
    return;
  }}
  window.open("/export-recording/" + encodeURIComponent(id) + "?format=" + fmt, "_blank");
}}

// ========== Toast ==========
function showToast(msg, type, duration) {{
  type = type || "info";
  duration = duration || 3000;
  var container = document.getElementById("toast-container");
  var el = document.createElement("div");
  el.className = "toast toast-" + type;
  el.textContent = msg;
  container.appendChild(el);
  requestAnimationFrame(function() {{ el.classList.add("show"); }});
  setTimeout(function() {{
    el.classList.remove("show");
    setTimeout(function() {{ container.removeChild(el); }}, 300);
  }}, duration);
}}
function confirmDelete(id) {{
  var msg = "\u786e\u5b9a\u8981\u5220\u9664\u5f55\u5236 " + id + " \u5417\uff1f" + String.fromCharCode(10) + "\u6b64\u64cd\u4f5c\u4e0d\u53ef\u6062\u590d\u3002";\n  if (confirm(msg)) {{
    window.location.href = "/delete?id=" + encodeURIComponent(id);
  }}
}}
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════
# HTTP Handler
# ═══════════════════════════════════════════════════════════════

class HistoryHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the history server."""

    # Suppress noisy traceback for client disconnects
    def handle_error(self, request, client_address):
        exc_type = sys.exc_info()[0]
        if exc_type and issubclass(exc_type, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)

    # Cache scanned recordings (refreshed on each list request)
    _recordings_cache: list = []
    _recordings_map: dict = {}

    def log_message(self, format, *args):
        pass  # Silence default stderr logging

    def _send(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        """Handle HEAD requests - same as GET but without response body."""
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        while path.startswith("//"):
            path = path[1:]

        if path.startswith("/file/") or path.startswith("/video/"):
            prefix = "/file/" if path.startswith("/file/") else "/video/"
            file_path = path[len(prefix):]
            abs_path = _resolve_path(file_path)
            if not abs_path:
                self.send_response(403)
                self.end_headers()
                return
            if not os.path.isfile(abs_path):
                self.send_response(404)
                self.end_headers()
                return
            file_size = os.path.getsize(abs_path)
            content_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            if path.startswith("/video/"):
                self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        while path.startswith("//"):
            path = path[1:]

        # List page
        if path == "/" or path == "":
            self._handle_list()
            return

        # Detail page
        if path.startswith("/recording/"):
            rec_id = path[len("/recording/"):]
            self._handle_detail(rec_id)
            return

        # Video streaming
        if path.startswith("/video/"):
            file_path = path[len("/video/"):]
            self._handle_video(file_path)
            return

        # File serving
        if path.startswith("/file/"):
            file_path = path[len("/file/"):]
            self._handle_file(file_path)
            return

        # Open local file
        if path.startswith("/open-local"):
            params = urlparse(self.path).query
            import urllib.parse as _ulp
            qs = _ulp.parse_qs(params)
            filepath = qs.get("path", [""])[0]
            if filepath and os.path.isfile(filepath):
                try:
                    open_file(filepath)
                except OSError:
                    pass
            self._send(200, "text/html", b'<script>window.history.back();</script>')
            return

        # Open folder
        if path.startswith("/open-folder"):
            params = urlparse(self.path).query
            import urllib.parse
            qs = urllib.parse.parse_qs(params)
            if qs.get("root", [""])[0]:
                try:
                    open_folder(os.getcwd())
                except OSError:
                    pass
            elif qs.get("id", [""])[0]:
                folder_id = qs.get("id", [""])[0]
                folder_id = os.path.basename(folder_id)
                target = os.path.join(RECORDINGS_ROOT, folder_id)
                if os.path.isdir(target):
                    try:
                        open_folder(target)
                    except OSError:
                        pass
            self._send(302, "text/html", b'<script>window.history.back();</script>')
            return

        # Delete recording
        if path.startswith("/delete"):
            params = urlparse(self.path).query
            import urllib.parse
            qs = urllib.parse.parse_qs(params)
            rec_id = qs.get("id", [""])[0]
            if rec_id:
                import shutil
                target = os.path.join(RECORDINGS_ROOT, rec_id)
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        # File System API
        if path.startswith("/api/fs/"):
            self._handle_fs_api()
            return

        # Edit recording
        if path.startswith("/edit-recording/"):
            rec_id = path[len("/edit-recording/"):]
            self._handle_edit_recording(rec_id)
            return

        # Export recording
        if path.startswith("/export-recording/"):
            rec_id = path[len("/export-recording/"):]
            self._handle_export_recording(rec_id)
            return

        # API
        if path == "/api/recordings":
            self._handle_api()
            return

        self._send(404, "text/plain", b"Not Found")

    def _handle_list(self):
        """Render history list page with pagination and view mode."""
        recordings = _scan_recordings()
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        page = int(params.get("page", ["1"])[0])
        view_mode = params.get("view", ["card"])[0]
        per_page = 20
        total = len(recordings)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        page_recordings = recordings[start:end]
        html = _html_list_page(page_recordings, page=page, total_pages=total_pages, total=total, view_mode=view_mode)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _handle_detail(self, rec_id):
        rec_id = os.path.basename(rec_id)
        recordings = _scan_recordings()
        found = None
        for r in recordings:
            if r["id"] == rec_id:
                found = r
                break
        if not found:
            self._send(404, "text/html", b"<h3>Recording not found</h3>")
            return
        html = _html_detail_page(found)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _handle_file(self, file_path):
        abs_path = _resolve_path(file_path)
        if not abs_path:
            self._send(403, "text/plain", b"Forbidden")
            return
        if not os.path.isfile(abs_path):
            self._send(404, "text/plain", b"Not Found")
            return
        file_size = os.path.getsize(abs_path)
        content_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(abs_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _handle_video(self, file_path):
        abs_path = _resolve_path(file_path)
        if not abs_path or not os.path.isfile(abs_path):
            self._send(404, "text/plain", b"Not Found")
            return
        file_size = os.path.getsize(abs_path)
        content_type = "video/mp4"
        range_header = self.headers.get("Range", "")
        if range_header:
            start, end = 0, file_size - 1
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if range_match:
                start = int(range_match.group(1))
                if range_match.group(2):
                    end = int(range_match.group(2))
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with open(abs_path, "rb") as f:
                f.seek(start)
                shutil.copyfileobj(f, self.wfile, length)
        else:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with open(abs_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

    def _handle_edit_recording(self, rec_id):
        rec_id = os.path.basename(rec_id)
        rec_dir = os.path.join(RECORDINGS_ROOT, rec_id)
        if not os.path.isdir(rec_dir):
            self._send(404, "text/html", b"<h3>Recording not found</h3>")
            return
        try:
            from recorder.urc_bridge import (
                RecordingConverter,
                UIRecorderCoreServer,
                URC_BASE,
                _call_urc_api,
            )

            # 1. 转换录制 → 返回项目名字符串
            project = RecordingConverter.convert(rec_dir)
            if not project:
                self._send(500, "text/html", b"<h3>Conversion failed: no recording data</h3>")
                return

            # 2. 确保 URC 服务已启动
            urc = UIRecorderCoreServer()
            if not urc.is_ready:
                if not urc.start(wait_ready=True, timeout=15):
                    self._send(500, "text/html", b"<h3>UIRecorderCore service failed to start</h3>")
                    return

            # 3. 调用 API 加载项目
            _call_urc_api("/api/v1/loadproject", {"project": project, "mode": "view"})

            # 4. 重定向到 URC 编辑器（带 project 参数）
            import urllib.parse
            self.send_response(302)
            self.send_header("Location", f"{URC_BASE}/?project={urllib.parse.quote(project)}")
            self.end_headers()
        except Exception as e:
            err_msg = "<h3>Conversion failed</h3><pre>{}</pre>".format(str(e))
            self._send(500, "text/html", err_msg.encode("utf-8"))

    def _handle_export_recording(self, rec_id):
        rec_id = os.path.basename(rec_id)
        rec_dir = os.path.join(RECORDINGS_ROOT, rec_id)
        if not os.path.isdir(rec_dir):
            self._send(404, "text/plain", b"Recording not found")
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        fmt = params.get("format", [""])[0]

        inputs_dir = os.path.join(rec_dir, "inputs")
        if not os.path.isdir(inputs_dir):
            self._send(500, "text/html", b"<h3>Export failed</h3><p>No inputs directory</p>")
            return

        log_file = None
        for f in os.listdir(inputs_dir):
            if f.startswith("input_log"):
                log_file = os.path.join(inputs_dir, f)
                break

        if not log_file or not os.path.isfile(log_file):
            self._send(500, "text/html", b"<h3>Export failed</h3><p>No input log found</p>")
            return

        ss_dir = os.path.join(inputs_dir, "screenshots")
        video_path = ""
        for f in os.listdir(inputs_dir):
            if f.lower().endswith(".mp4"):
                video_path = os.path.join(inputs_dir, f)
                break

        # ── GuiRunner export（复用公共导出函数，与 urecorder 同一管线）──
        if fmt == "guirunner":
            import json as _json
            import webbrowser as _webbrowser
            from recorder.click_icon_extractor import export_recording_to_guirunner

            result = export_recording_to_guirunner(rec_dir, _guirunner_url)

            if result.get("ok"):
                # 在详情页场景下自动打开编辑器
                editor_url = result.get("editor_url", "")
                if editor_url:
                    _webbrowser.open_new_tab(editor_url)
                resp = _json.dumps({"ok": True, "project": result.get("project", rec_id), "editor_url": editor_url})
                self._send(200, "application/json; charset=utf-8", resp.encode("utf-8"))
            else:
                resp = _json.dumps({
                    "ok": False,
                    "message": result.get("message", "GuiRunner 导出失败"),
                })
                self._send(200, "application/json; charset=utf-8", resp.encode("utf-8"))
            return

        # Video export
        if fmt == "video":
            if video_path and os.path.isfile(video_path):
                self.send_response(302)
                self.send_header("Location", "/file/" + _to_web_path(video_path))
                self.end_headers()
                return
            else:
                self._send(500, "text/html", b"<h3>Video not found</h3>")
                return

        # ZIP export
        if fmt == "zip":
            import zipfile
            import io
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for root_dir, dirs, files in os.walk(rec_dir):
                    for f in files:
                        fp = os.path.join(root_dir, f)
                        zf.write(fp, os.path.relpath(fp, os.path.dirname(rec_dir)))
            buf.seek(0)
            zip_data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(zip_data)))
            self.send_header("Content-Disposition", 'attachment; filename="' + rec_id + '.zip"')
            self.end_headers()
            self.wfile.write(zip_data)
            return

        # Report format exports
        ext_map = {"md": "md", "html": "html", "json": "json", "docx": "docx"}
        ext = ext_map.get(fmt, "")
        if not ext:
            self._show_export_page(rec_id, rec_dir, inputs_dir, log_file, ss_dir, video_path)
            return

        report_path = os.path.join(inputs_dir, "report_" + rec_id + "." + ext)
        if not os.path.isfile(report_path):
            try:
                from recorder.report_generator import parse_log, generate_markdown, generate_html, generate_word, generate_json
                events = parse_log(log_file)
                if fmt == "md":
                    generate_markdown(events, ss_dir, report_path, rec_id, video_path)
                elif fmt == "html":
                    generate_html(events, ss_dir, report_path, rec_id, video_path)
                elif fmt == "json":
                    generate_json(events, ss_dir, report_path, rec_id, video_path)
                elif fmt == "docx":
                    generate_word(events, ss_dir, report_path, rec_id, video_path)
            except Exception as e:
                import traceback
                err_msg = "<h3>Generate failed</h3><pre>{}</pre>".format(traceback.format_exc())
                self._send(500, "text/html", err_msg.encode("utf-8"))
                return

        if os.path.isfile(report_path):
            self.send_response(302)
            self.send_header("Location", "/file/" + _to_web_path(report_path))
            self.end_headers()
            return
        else:
            self._send(500, "text/html", b"<h3>Report not found</h3>")
            return

    def _show_export_page(self, rec_id, rec_dir, inputs_dir, log_file, ss_dir, video_path):
        try:
            from recorder.report_generator import generate_reports
            result = generate_reports(log_file, ss_dir, rec_dir, project_name=rec_id, video_path=video_path)
        except Exception:
            result = {}

        reports = []
        fmt_map = [("html", "HTML"), ("markdown", "Markdown"), ("word", "Word"), ("json", "JSON")]
        for fmt_key, label in fmt_map:
            fpath = result.get(fmt_key, "")
            if fpath and os.path.isfile(fpath):
                reports.append((label, _to_web_path(fpath)))

        links_html = "".join(
            '<li><a href="/file/{0}" target="_blank">{1}</a></li>\n'.format(web, label)
            for label, web in reports
        )

        if video_path and os.path.isfile(video_path):
            links_html += '<li><a href="/file/{}" target="_blank">Video</a></li>\n'.format(_to_web_path(video_path))

        page = (
            '<!DOCTYPE html>\n'
            '<html lang="zh-CN">\n'
            '<head><meta charset="UTF-8">\n'
            '<title>Export Report - ' + rec_id + '</title>\n'
            '<style>\n'
            'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;\n'
            '       background: #0d1117; color: #e6edf3; padding: 40px; }\n'
            'h1 { font-size: 20px; margin-bottom: 20px; }\n'
            'ul { list-style: none; padding: 0; }\n'
            'li { margin: 8px 0; }\n'
            'a { color: #58a6ff; text-decoration: none; font-size: 15px; }\n'
            'a:hover { text-decoration: underline; }\n'
            '.msg { color: #8b949e; margin-top: 16px; }\n'
            '</style></head>\n'
            '<body>\n'
            '<h1>Export Report - ' + rec_id + '</h1>\n'
            '<ul>\n' + links_html + '</ul>\n'
            '<div class="msg">Total ' + str(len(reports)) + ' reports</div>\n'
            '</body></html>'
        )
        self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))

    def _handle_api(self):
        recordings = _scan_recordings()
        data = json.dumps(recordings, ensure_ascii=False, default=str)
        self._send(200, "application/json; charset=utf-8", data.encode("utf-8"))

    def _handle_fs_api(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        rel_path = path[len("/api/fs/"):]
        abs_path = _resolve_path(rel_path)
        if not abs_path:
            self._send(403, "application/json", b'{"error":"Forbidden"}')
            return
        if os.path.isfile(abs_path):
            self._handle_file(rel_path)
            return
        if os.path.isdir(abs_path):
            entries = []
            try:
                for name in sorted(os.listdir(abs_path)):
                    fp = os.path.join(abs_path, name)
                    entries.append({
                        "name": name,
                        "is_dir": os.path.isdir(fp),
                        "size": os.path.getsize(fp) if os.path.isfile(fp) else 0,
                    })
            except PermissionError:
                pass
            data = json.dumps(entries, ensure_ascii=False)
            self._send(200, "application/json; charset=utf-8", data.encode("utf-8"))
            return
        self._send(404, "application/json", b'{"error":"Not Found"}')


# ═══════════════════════════════════════════════════════════════
# Server
# ═══════════════════════════════════════════════════════════════

class HistoryServer:
    """HTTP server for browsing recording history."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, open_browser: bool = True):
        if self._server:
            return
        self._server = socketserver.TCPServer((self.host, self.port), HistoryHandler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"[HistoryServer] Listening on {self.url}")
        if open_browser:
            webbrowser.open(self.url)

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None

    def is_running(self) -> bool:
        return self._server is not None


# Global server instance
_server: HistoryServer | None = None


def start_server(open_browser: bool = True) -> "HistoryServer":
    """Convenience function to start the history server."""
    server = HistoryServer()
    server.start(open_browser)
    return server


def get_server() -> "HistoryServer | None":
    """Return the currently running server instance."""
    global _server
    return _server
