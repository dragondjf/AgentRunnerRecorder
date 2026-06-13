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
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

# ── UIRecorderCore 桥接（惰性导入，避免启动时加载 Flask 依赖） ──
_urc_converter = None
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
    r"C:\Users\YFJZ\Videos\ScreenRecordings",
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

CSS_COMMON = """
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --surface2: #1c2129;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --accent: #58a6ff;
  --green: #3fb950;
  --red: #ff7b72;
  --orange: #f0883e;
  --purple: #bc8cff;
  --radius: 8px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
button { font-family: inherit; cursor: pointer; }
"""


def _html_list_page(recordings: list) -> str:
    """Generate the history list page HTML."""
    cards_html = ""
    for r in recordings:
        # Thumbnail
        if r["thumbnail"]:
            thumb_src = _to_web_path(r["thumbnail"])
            thumb_html = f'<img src="/file/{thumb_src}" alt="screenshot" class="thumb">'
        else:
            thumb_html = '<div class="thumb-placeholder">N/A</div>'

        # Duration display
        dur = r["duration_sec"]
        if dur > 0:
            mins = int(dur) // 60
            secs = int(dur) % 60
            dur_text = f"{mins:02d}:{secs:02d}"
        else:
            dur_text = "--:--"

        # Report badges
        badges = ""
        for fmt, label in [("html", "HTML"), ("md", "MD"), ("docx", "Word"), ("json", "JSON")]:
            if fmt in r["reports"]:
                badges += f'<span class="badge badge-{fmt}">{label}</span>'

        # Video size
        vid_sz = _fmt_size(r["video_size"]) if r["video_size"] > 0 else "-"
        cards_html += f"""
        <div class="card" data-id="{r['id']}">
          <div class="card-main">
            <div class="card-thumb">{thumb_html}</div>
            <div class="card-body">
              <div class="card-header">
                <span class="card-seq">#{r['seq']:03d}</span>
                <span class="card-time">{r['created']}</span>
              </div>
              <div class="card-stats">
                <span class="stat">{dur_text}</span>
                <span class="stat">{r['screenshots']} 截图</span>
                <span class="stat">{r['events']} 事件</span>
                <span class="stat">{vid_sz}</span>
              </div>
              <div class="card-badges">{badges if badges else '<span class="no-data">无报告</span>'}</div>
            </div>
          </div>
          <div class="card-actions-col">
            <button class="act-btn act-detail" onclick="event.stopPropagation(); location.href='/recording/{r['id']}'">详情</button>
            <button class="act-btn act-edit" onclick="event.stopPropagation(); editRecording('{r['id']}')">编辑</button>
            <button class="act-btn act-folder" onclick="event.stopPropagation(); openFolder('{r['id']}')">打开文件夹</button>
            <div class="export-wrap">
              <button class="act-btn act-export" onclick="event.stopPropagation(); toggleExportMenu(this)">导出</button>
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


    total = len(recordings)
    total_valid = len([r for r in recordings if r["valid"]])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>录制历史 — AgentRunner Recorder</title>
<style>
{CSS_COMMON}
.header {{
  position: sticky; top: 0; z-index: 100;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  display: flex; align-items: center; gap: 16px;
  flex-wrap: wrap;
}}
.header h1 {{
  font-size: 18px; font-weight: 700;
  white-space: nowrap;
}}
.header .count {{
  font-size: 12px; color: var(--text2);
  background: var(--surface2);
  padding: 2px 8px; border-radius: 12px;
}}
.search-box {{
  flex: 1; min-width: 200px; max-width: 400px;
  position: relative;
}}
.search-box input {{
  width: 100%;
  padding: 6px 12px 6px 32px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}}
.search-box input:focus {{ border-color: var(--accent); }}
.search-box::before {{
  content: "\\1F50D";
  position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  font-size: 14px; color: var(--text2);
}}
.filter-chips {{
  display: flex; gap: 6px; flex-wrap: wrap;
}}
.chip {{
  padding: 4px 12px;
  font-size: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 16px;
  color: var(--text2);
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}}
.chip:hover, .chip.active {{
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}}
.container {{
  max-width: 960px;
  margin: 0 auto;
  padding: 20px;
}}
.empty {{
  text-align: center;
  padding: 60px 20px;
  color: var(--text2);
  font-size: 15px;
}}
.card {{
  display: flex;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  cursor: pointer;
  transition: border-color 0.2s, transform 0.1s;
}}
.card:hover {{
  border-color: var(--accent);
  transform: translateY(-1px);
}}
.card-thumb {{
  width: 160px; min-height: 90px;
  flex-shrink: 0;
  overflow: hidden;
  background: var(--surface2);
  display: flex; align-items: center; justify-content: center;
}}
.card-thumb img {{
  width: 100%; height: 100%; object-fit: cover;
}}
.thumb-placeholder {{
  color: var(--text2);
  font-size: 12px;
}}
.card-body {{
  padding: 12px 16px;
  flex: 1;
  min-width: 0;
}}
.card-header {{
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 6px;
}}
.card-seq {{
  font-size: 14px; font-weight: 700;
  font-family: "Consolas", monospace;
  color: var(--accent);
}}
.card-time {{
  font-size: 13px; color: var(--text2);
}}
.card-stats {{
  display: flex; gap: 12px; flex-wrap: wrap;
  margin-bottom: 8px;
}}
.stat {{
  font-size: 12px; color: var(--text2);
  padding: 1px 6px;
  background: var(--bg);
  border-radius: 4px;
}}
.card-badges {{
  display: flex; gap: 4px; flex-wrap: wrap;
}}
.badge {{
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}}
.badge-html {{ background: #1a3a5c; color: var(--accent); }}
.badge-md {{ background: #1a3a3a; color: #3fb950; }}
.badge-docx {{ background: #1a2a5c; color: #79c0ff; }}
.badge-json {{ background: #2a1a4c; color: var(--purple); }}
.header-actions {{
  margin-left: auto;
}}
.btn-open-dir {{
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--text1);
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}}
.btn-open-dir:hover {{
  background: rgba(255,255,255,0.12);
  border-color: var(--accent);
}}
.no-data {{
  font-size: 11px; color: var(--text2); opacity: 0.5;
}}


.card-main {{
  display: flex;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}}

.card-actions-col {{
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px;
  border-left: 1px solid var(--border);
  flex-shrink: 0;
}}
.act-btn {{
  padding: 6px 12px;
  font-size: 11px;
  font-weight: 600;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: opacity 0.2s;
  text-align: center;
  line-height: 1.4;
  white-space: nowrap;
}}
.act-btn:hover {{
  opacity: 0.85;
}}
.act-edit {{
  background: #6b3fa0;
  color: #fff;
}}
.act-folder {{
  background: #a05a2c;
  color: #fff;
}}
.act-detail {{
  background: #2d7d46;
  color: #fff;
}}
.act-export {{
  background: #1a6bb5;
  color: #fff;
}}
.export-wrap {{
  position: relative;
  display: inline-block;
}}
.export-menu {{
  display: none;
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: #1e2430;
  border: 1px solid #3a4050;
  border-radius: 8px;
  min-width: 140px;
  z-index: 9999;
  box-shadow: 0 8px 32px rgba(0,0,0,0.6);
  padding: 6px 0;
}}
.export-menu.show {{
  display: block;
}}
.export-menu a {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 12px;
  color: var(--text);
  text-decoration: none;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s;
  border-left: 3px solid transparent;
}}
.export-menu a:hover {{
  background: #2a3340;
  color: #fff;
  border-left-color: var(--accent);
}}

</style>
</head>
<body>
<div class="header">
  <h1>录制历史</h1>
  <span class="count">{total} 次录制</span>
  <div class="search-box">
    <input type="text" id="search" placeholder="搜索时间、编号..." oninput="filterCards()">
  </div>
  <div class="header-actions">
    <button class="btn-open-dir" onclick="window.location.href='/open-folder?root=1'" title="Open Program Directory">打开程序目录</button>
  </div>
  <div class="filter-chips">
    <span class="chip active" data-filter="all" onclick="setFilter(this)">全部</span>
    <span class="chip" data-filter="today" onclick="setFilter(this)">今天</span>
    <span class="chip" data-filter="week" onclick="setFilter(this)">本周</span>
    <span class="chip" data-filter="report" onclick="setFilter(this)">有报告</span>
  </div>
</div>
<div class="container" id="card-list">
  {cards_html if recordings else '<div class="empty">暂无录制记录</div>'}
</div>
<script>
function filterCards() {{
  var q = document.getElementById("search").value.toLowerCase();
  var cards = document.querySelectorAll(".card");
  cards.forEach(function(c) {{
    var text = c.textContent.toLowerCase();
    c.style.display = text.indexOf(q) >= 0 ? "" : "none";
  }});
}}

function editRecording(id) {{
  window.open("/edit-recording/" + encodeURIComponent(id), "_blank");
}}
function openFolder(id) {{
  window.location.href = "/open-folder?id=" + encodeURIComponent(id);
}}
function toggleExportMenu(btn) {{
  var menu = btn.nextElementSibling;
  menu.classList.toggle('show');
}}
function exportFormat(id, fmt) {{
  window.open("/export-recording/" + encodeURIComponent(id) + "?format=" + fmt, "_blank");
}}
document.addEventListener('click', function(e) {{
  document.querySelectorAll('.export-menu.show').forEach(function(m) {{ m.classList.remove('show'); }});
}});

var currentFilter = "all";
function setFilter(el) {{
  document.querySelectorAll(".chip").forEach(function(c) {{ c.classList.remove("active"); }});
  el.classList.add("active");
  currentFilter = el.dataset.filter;
  applyFilter();
}}

function applyFilter() {{
  var cards = document.querySelectorAll(".card");
  var now = new Date();
  cards.forEach(function(c) {{
    if (currentFilter === "all") {{ c.style.display = ""; return; }}
    if (currentFilter === "today") {{
      var timeEl = c.querySelector(".card-time");
      if (!timeEl) return;
      var t = timeEl.textContent.trim();
      c.style.display = t.indexOf(now.getFullYear()+"-"+String(now.getMonth()+1).padStart(2,"0")+"-"+String(now.getDate()).padStart(2,"0")) >= 0 ? "" : "none";
      return;
    }}
    if (currentFilter === "week") {{
      var timeEl = c.querySelector(".card-time");
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
</script>
</body>
</html>"""


def _html_detail_page(rec: dict) -> str:
    """Generate the recording detail page HTML."""
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

    # File list (real paths from reports dict)
    files_html = ""
    fmt_config = [
        ("html", "HTML 报告"),
        ("md", "Markdown"),
        ("docx", "Word 文档"),
        ("json", "JSON 数据"),
    ]
    for fmt, label in fmt_config:
        fpath = rec["reports"].get(fmt, "")
        if fpath:
            web = _to_web_path(fpath)
            files_html += f"""
            <div class="file-item" onclick="openFile('/file/{web}')">
              <span class="file-dot dot-{fmt}"></span>
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
            <span class="file-dot dot-mp4"></span>
            <span class="file-name">{os.path.basename(rec['video_file'])}</span>
            <span class="vid-size">{vid_sz}</span>
          </div>
        </div>"""

    # Build action buttons (real paths)
    actions_html = ""
    html_p = rec["reports"].get("html", "")
    if html_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(html_p)}')">打开 HTML 报告</button>\n"""
    md_p = rec["reports"].get("md", "")
    if md_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(md_p)}')">打开 Markdown</button>\n"""
    docx_p = rec["reports"].get("docx", "")
    if docx_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(docx_p)}')">打开 Word</button>\n"""
    json_p = rec["reports"].get("json", "")
    if json_p:
        actions_html += f"""<button class="action-item" onclick="openFile('/file/{_to_web_path(json_p)}')">打开 JSON</button>\n"""
    if rec["video_file"]:
        vid_web = _to_web_path(rec["video_file"])
        if rec["video_file"]:
            vid_abs = rec["video_file"].replace(os.sep, "/")
        actions_html += f'''<button class="action-item" onclick="openLocal('{vid_abs}')">播放视频</button>\n'''
    actions_html += f"""<button class="action-item" onclick="openFolder('{rec['id']}')">打开文件夹</button>\n"""
    actions_html += f"""<button class="action-item" onclick="editRecording('{rec['id']}')">在 UIRecorderCore 中编辑</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportRecording('{rec['id']}')">导出所有格式</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','video')">导出 Video</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','md')">导出 Markdown</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','json')">导出 JSON</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','html')">导出 HTML</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','docx')">导出 Word</button>
"""
    actions_html += f"""<button class="action-item" onclick="exportFormat('{rec['id']}','zip')">导出 ZIP</button>
"""
    actions_html += f"""<button class="action-item danger" onclick="confirmDelete('{rec['id']}')">删除本次录制</button>"""

    # CSS (same as before - kept inline for single-file deployment)
    css_sidebar = """
  .sidebar { position: fixed; top: 0; left: 0; bottom: 0; width: 240px; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 100; }
  .sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); }
  .back-btn { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: var(--text2); background: none; border: none; padding: 4px 0; cursor: pointer; }
  .back-btn:hover { color: var(--accent); }
  .sidebar-meta { padding: 16px; }
  .sidebar-meta .rec-id { font-size: 16px; font-weight: 700; color: var(--accent); font-family: "Consolas", monospace; }
  .sidebar-meta .rec-time { font-size: 12px; color: var(--text2); margin-top: 2px; }
  .meta-stats { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
  .meta-stat { display: flex; justify-content: space-between; font-size: 12px; }
  .meta-stat .label { color: var(--text2); }
  .meta-stat .value { font-weight: 600; font-family: "Consolas", monospace; }
  .sidebar-actions { padding: 0 16px 16px; border-top: 1px solid var(--border); margin-top: auto; }
  .action-list { display: flex; flex-direction: column; gap: 2px; }
  .action-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; font-size: 13px; border-radius: 6px; cursor: pointer; transition: background 0.15s; color: var(--text); border: none; background: none; width: 100%; text-align: left; }
  .action-item:hover { background: var(--surface2); }
  .action-item.danger { color: var(--red); }
  .action-item.danger:hover { background: rgba(255,123,114,0.1); }"""
    css_center = """
  .center { flex: 1; margin-left: 240px; margin-right: 280px; padding: 20px; }
  .center-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .view-toggle { display: flex; gap: 4px; }
  .view-btn { padding: 4px 12px; font-size: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; color: var(--text2); }
  .view-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .ss-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .ss-grid.timeline { grid-template-columns: 1fr; }
  .ss-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; cursor: pointer; transition: border-color 0.2s; }
  .ss-card:hover { border-color: var(--accent); }
  .ss-card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
  .timeline .ss-card img { aspect-ratio: auto; max-height: 60vh; }
  .ss-info { padding: 6px 8px; display: flex; flex-direction: column; gap: 2px; }
  .ss-step { font-size: 11px; font-weight: 700; font-family: "Consolas", monospace; color: var(--accent); }
  .ss-ts { font-size: 10px; color: var(--text2); }
  .ss-msg { font-size: 11px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .empty-ss { text-align: center; padding: 60px 20px; color: var(--text2); font-size: 14px; }"""
    css_right = """
  .right-panel { position: fixed; top: 0; right: 0; bottom: 0; width: 280px; background: var(--surface); border-left: 1px solid var(--border); display: flex; flex-direction: column; z-index: 100; overflow-y: auto; }
  .panel-section { padding: 16px; border-bottom: 1px solid var(--border); }
  .panel-title { font-size: 12px; font-weight: 600; color: var(--text2); text-transform: uppercase; margin-bottom: 10px; }
  .file-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 4px; cursor: pointer; transition: background 0.15s; font-size: 13px; }
  .file-item:hover { background: var(--surface2); }
  .file-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .dot-html { background: var(--accent); }
  .dot-md { background: var(--green); }
  .dot-docx { background: #79c0ff; }
  .dot-json { background: var(--purple); }
  .dot-mp4 { background: var(--orange); }
  .file-name { flex: 1; }
  .open-hint { font-size: 10px; color: var(--text2); background: var(--bg); padding: 1px 4px; border-radius: 3px; }
  .vid-size { font-size: 11px; color: var(--text2); }
  .video-section { padding: 16px; }
  .video-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; }
  .video-player { width: 100%; border-radius: var(--radius); background: #000; }
  .lightbox { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.85); z-index: 9999; align-items: center; justify-content: center; cursor: zoom-out; }
  .lightbox.active { display: flex; }
  .lightbox img { max-width: 95vw; max-height: 95vh; object-fit: contain; border-radius: 4px; }
    """

    page_css = CSS_COMMON + css_sidebar + css_center + css_right

    html_body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>#{rec['seq']:03d} -- AgentRunner Recorder</title>
<style>
{page_css}
</style>
</head>
<body>
<div class="app">
  <div class="sidebar">
    <div class="sidebar-header">
      <button class="back-btn" onclick="location.href='/'">&#8592; 返回列表</button>
    </div>
    <div class="sidebar-meta">
      <div class="rec-id">#{rec['seq']:03d}</div>
      <div class="rec-time">{rec['created']}</div>
      <div class="meta-stats">
        <div class="meta-stat"><span class="label">时长</span><span class="value">{dur_text}</span></div>
        <div class="meta-stat"><span class="label">事件</span><span class="value">{rec['events']} 条</span></div>
        <div class="meta-stat"><span class="label">截图</span><span class="value">{rec['screenshots']} 张</span></div>
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
      <span style="font-size:14px;font-weight:600;">截图 ({len(screenshots)})</span>
      <div class="view-toggle">
        <button class="view-btn active" onclick="setView('grid', this)">网格视图</button>
        <button class="view-btn" onclick="setView('timeline', this)">时间线视图</button>
      </div>
    </div>
    <div class="ss-grid" id="ss-grid">
      {ss_html if screenshots else '<div class="empty-ss">本次录制无截图</div>'}
    </div>
  </div>

  <div class="right-panel">
    <div class="panel-section">
      <div class="panel-title">文件列表</div>
      {files_html if files_html else '<div style="font-size:12px;color:var(--text2);">无报告文件</div>'}
    </div>
    {f'<div class="video-section">{vid_html}</div>' if vid_html else ''}
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="">
</div>
  </div>
<script>
function setView(mode, btn) {{
  var grid = document.getElementById("ss-grid");
  document.querySelectorAll(".view-btn").forEach(function(b) {{ b.classList.remove("active"); }});
  btn.classList.add("active");
  grid.classList.toggle("timeline", mode === "timeline");
}}
function openLightbox(src) {{
  document.getElementById("lightbox-img").src = src;
  document.getElementById("lightbox").classList.add("active");
}}
function closeLightbox() {{
  document.getElementById("lightbox").classList.remove("active");
}}
document.addEventListener("keydown", function(e) {{ if (e.key === "Escape") closeLightbox(); }});
function openFile(url) {{ window.open(url, "_blank"); }}
function openLocal(path) {{ window.location.href = "/open-local?path=" + encodeURIComponent(path); }}
function openFolder(path) {{ window.location.href = "/open-folder?id=" + encodeURIComponent(path); }}
function editRecording(id) {{ window.open("/edit-recording/" + encodeURIComponent(id), "_blank"); }}
function exportRecording(id) {{ window.open("/export-recording/" + encodeURIComponent(id), "_blank"); }}
function exportFormat(id, fmt) {{ window.open("/export-recording/" + encodeURIComponent(id) + "?format=" + fmt, "_blank"); }}
function confirmDelete(id) {{
  if (confirm("确定要删除录制 " + id + " 吗？\\n此操作不可恢复。")) {{
    window.location.href = "/delete?id=" + encodeURIComponent(id);
  }}
}}
</script>
</body>
</html>"""
    return html_body


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
        # Normalize double leading slashes (e.g. //video/ -> /video/)
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
        # For HEAD on all other routes, just do a standard HEAD
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        # Normalize double leading slashes (e.g. //video/ -> /video/)
        while path.startswith("//"):
            path = path[1:]

        # ── List page ──
        if path == "/" or path == "":
            self._handle_list()
            return

        # ── Detail page ──
        if path.startswith("/recording/"):
            rec_id = path[len("/recording/"):]
            self._handle_detail(rec_id)
            return

        # ── Video streaming (dedicated route) ──
        if path.startswith("/video/"):
            file_path = path[len("/video/"):]
            self._handle_video(file_path)
            return

        # ── File serving ──
        if path.startswith("/file/"):
            file_path = path[len("/file/"):]
            self._handle_file(file_path)
            return

        # ── Open file locally (Word, video, etc.) ──
        if path.startswith("/open-local"):
            params = urlparse(self.path).query
            import urllib.parse as _ulp
            qs = _ulp.parse_qs(params)
            filepath = qs.get("path", [""])[0]
            if filepath and os.path.isfile(filepath):
                try:
                    os.startfile(filepath)
                except OSError:
                    pass
            self._send(200, "text/html", b'<script>window.history.back();</script>')
            return

        # ── Open folder (OS explorer) ──
        if path.startswith("/open-folder"):
            params = urlparse(self.path).query
            import urllib.parse
            qs = urllib.parse.parse_qs(params)
            # root=1: open program working directory
            if qs.get("root", [""])[0]:
                try:
                    os.startfile(os.getcwd())
                except OSError:
                    pass
            elif qs.get("id", [""])[0]:
                folder_id = qs.get("id", [""])[0]
                folder_id = os.path.basename(folder_id)  # prevent path traversal
                target = os.path.join(RECORDINGS_ROOT, folder_id)
                if os.path.isdir(target):
                    try:
                        os.startfile(target)
                    except OSError:
                        pass
            self._send(302, "text/html", b'<script>window.history.back();</script>')
            return

        # ── Delete recording ──
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
            self._send(302, "text/html", b"")
            self.send_header("Location", "/")
            self.end_headers()
            return

        # ── File System API ──
        if path.startswith("/api/fs/"):
            self._handle_fs_api()
            return

        # ── Edit recording (convert + redirect to UIRecorderCore) ──
        if path.startswith("/edit-recording/"):
            rec_id = path[len("/edit-recording/"):]
            self._handle_edit_recording(rec_id)
            return

        # ── API ──
        if path == "/api/recordings":
            self._handle_api()
            return

        # ── 404 ──
        self._send(404, "text/plain", b"Not Found")

    def _handle_list(self):
        """Render history list page."""
        recordings = _scan_recordings()
        html = _html_list_page(recordings)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _handle_detail(self, rec_id: str):
        """Render recording detail page."""
        # Security: prevent path traversal
        rec_id = os.path.basename(rec_id)
        rec_dir = os.path.join(RECORDINGS_ROOT, rec_id)
        if not os.path.isdir(rec_dir):
            self._send(404, "text/plain", b"Recording not found")
            return

        rec = _parse_recording(Path(rec_dir))
        # Assign seq from full list
        all_recs = _scan_recordings()
        for i, r in enumerate(reversed(all_recs), 1):
            if r["id"] == rec_id:
                rec["seq"] = i
                break

        html = _html_detail_page(rec)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _handle_file(self, file_path: str):
        """Serve a static file from disk with Range request support."""
        abs_path = _resolve_path(file_path)
        if not abs_path:
            self._send(403, "text/plain", b"Forbidden")
            return
        if not os.path.isfile(abs_path):
            self._send(404, "text/plain", b"File not found")
            return

        file_size = os.path.getsize(abs_path)
        content_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"

        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            # Parse range: bytes=start-end
            range_spec = range_header[6:]
            parts = range_spec.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
            if start >= file_size or end >= file_size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            chunk_size = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(chunk_size))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()
            with open(abs_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                try:
                    while remaining > 0:
                        block = f.read(min(8192, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
        else:
            # Full file response
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()
            with open(abs_path, "rb") as f:
                try:
                    while True:
                        block = f.read(8192)
                        if not block:
                            break
                        self.wfile.write(block)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass

    @staticmethod
    def _handle_video(self, file_path: str):
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
        content_type = mimetypes.guess_type(abs_path)[0] or "video/mp4"

        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            range_spec = range_header[6:]
            parts = range_spec.split("-")
            try:
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            if start >= file_size or end >= file_size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            chunk_size = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(chunk_size))
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                with open(abs_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        block = f.read(min(65536, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                with open(abs_path, "rb") as f:
                    while True:
                        block = f.read(65536)
                        if not block:
                            break
                        self.wfile.write(block)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

    def _handle_edit_recording(self, rec_id):
        # Security: prevent path traversal
        rec_id = os.path.basename(rec_id)
        rec_dir = os.path.join(RECORDINGS_ROOT, rec_id)
        if not os.path.isdir(rec_dir):
            self._send(404, "text/plain", b"Recording not found")
            return

        try:
            RecordingConverter, URC_BASE = _get_converter()
            project = RecordingConverter.convert(rec_dir)
            if not project:
                self._send(500, "text/html", b"<h3>Conversion failed</h3><p>No recording data found</p>")
                return

            redirect_url = "{}/api/v1/loadproject?project={}&mode=view".format(URC_BASE, project)
            html = (
                '<!DOCTYPE html><html><head><meta charset="utf-8">'
                '<title>Redirecting to UIRecorderCore...</title>'
                '<script>'
                'fetch("' + redirect_url + '")'
                '.then(function(){window.location.href="' + URC_BASE + '";})'
                '.catch(function(){window.location.href="' + URC_BASE + '";});'
                '</script></head><body>'
                '<p>Converting and redirecting to UIRecorderCore...</p>'
                '</body></html>'
            )
            self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
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
        """Return recordings as JSON."""
        recordings = _scan_recordings()
        # Remove large fields for API response
        for r in recordings:
            r.pop("thumbnail", None)
            r.pop("video_file", None)
        body = json.dumps(recordings, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(200, "application/json; charset=utf-8", body)

    # ═══════════════════════════════════════════════
    # File System API (adapted from file_browser blueprint)
    # ═══════════════════════════════════════════════

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/fs/"):
            self._handle_fs_api()
            return
        self._send(404, "text/plain", b"Not Found")

    def _json_response(self, code: int, data: dict):
        """Send a JSON response."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        """Read request body."""
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length > 0 else b""

    def _handle_fs_api(self):
        """Route /api/fs/* requests."""
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        action = path[len("/api/fs/"):]  # e.g. "list", "read", "open", etc.

        handlers = {
            "list": self._fs_list,
            "read": self._fs_read,
            "download": self._fs_download,
            "open": self._fs_open,
            "open-location": self._fs_open_location,
            "search": self._fs_search,
            "info": self._fs_info,
            "thumbnail": self._fs_thumbnail,
            "delete": self._fs_delete,
            "create-folder": self._fs_create_folder,
            "rename": self._fs_rename,
            "copy": self._fs_copy,
        }
        handler = handlers.get(action)
        if handler:
            try:
                handler()
            except Exception as e:
                self._json_response(500, {"success": False, "error": str(e)})
        else:
            self._json_response(404, {"success": False, "error": f"Unknown action: {action}"})

    def _fs_resolve_path(self, relative_path: str) -> tuple:
        """Resolve a relative/absolute path and return (abs_path, is_safe).
        For safety, only allow paths under user-accessible areas."""
        if not relative_path:
            return None, False
        abs_path = os.path.normpath(os.path.abspath(relative_path))
        # Block system-critical paths
        blocked = ["C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)"]
        for b in blocked:
            if abs_path.lower().startswith(b.lower()):
                return abs_path, False
        return abs_path, True

    def _file_info_dict(self, filepath: str) -> dict:
        """Build file info dict."""
        try:
            stat = os.stat(filepath)
            return {
                "name": os.path.basename(filepath),
                "path": filepath.replace(os.sep, "/"),
                "type": "folder" if os.path.isdir(filepath) else "file",
                "size": self._format_size(stat.st_size),
                "size_bytes": stat.st_size if os.path.isfile(filepath) else None,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            }
        except OSError:
            return {"name": os.path.basename(filepath), "path": filepath, "type": "file", "error": True}

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    # ── /api/fs/list ──
    def _fs_list(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        if not rel:
            # Return system drives on Windows
            drives = []
            import string
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if os.path.exists(d):
                    drives.append({"name": f"{letter}:", "path": f"{letter}/", "type": "folder", "size": None})
            self._json_response(200, {"success": True, "data": {"items": drives, "current_path": ""}})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.isdir(abs_path):
            self._json_response(404, {"success": False, "error": "Directory not found"})
            return
        items = []
        try:
            for entry in sorted(os.scandir(abs_path), key=lambda e: (not e.is_dir(), e.name.lower())):
                try:
                    items.append(self._file_info_dict(entry.path))
                except (PermissionError, OSError):
                    continue
        except PermissionError:
            self._json_response(403, {"success": False, "error": "Permission denied"})
            return
        # Parent
        parent = os.path.dirname(abs_path)
        parent_path = parent.replace(os.sep, "/") if parent != abs_path else ""
        self._json_response(200, {
            "success": True,
            "data": {
                "current_path": abs_path.replace(os.sep, "/"),
                "parent_path": parent_path,
                "items": items,
            }
        })

    # ── /api/fs/read ──
    def _fs_read(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.isfile(abs_path):
            self._json_response(404, {"success": False, "error": "File not found"})
            return
        if os.path.getsize(abs_path) > 10 * 1024 * 1024:
            self._json_response(400, {"success": False, "error": "File too large (max 10MB)"})
            return
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                text = f.read()
            self._json_response(200, {"success": True, "data": {"name": os.path.basename(abs_path), "path": rel, "content": text}})
        except UnicodeDecodeError:
            self._json_response(400, {"success": False, "error": "Cannot read binary file"})

    # ── /api/fs/download ──
    def _fs_download(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.isfile(abs_path):
            self._json_response(404, {"success": False, "error": "File not found"})
            return
        filename = os.path.basename(abs_path)
        ct = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
        file_size = os.path.getsize(abs_path)
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            with open(abs_path, "rb") as f:
                while True:
                    block = f.read(65536)
                    if not block:
                        break
                    self.wfile.write(block)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    # ── /api/fs/open ──
    def _fs_open(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.exists(abs_path):
            self._json_response(404, {"success": False, "error": "Path not found"})
            return
        try:
            os.startfile(abs_path)
            self._json_response(200, {"success": True, "message": "Opened"})
        except OSError:
            self._json_response(500, {"success": False, "error": "No application associated"})

    # ── /api/fs/open-location ──
    def _fs_open_location(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.exists(abs_path):
            self._json_response(404, {"success": False, "error": "Path not found"})
            return
        try:
            if os.path.isfile(abs_path):
                subprocess.run(["explorer", "/select,", abs_path])
            else:
                os.startfile(abs_path)
            self._json_response(200, {"success": True, "message": "Opened in explorer"})
        except OSError as e:
            self._json_response(500, {"success": False, "error": str(e)})

    # ── /api/fs/search ──
    def _fs_search(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        keyword = params.get("keyword", [""])[0]
        if not keyword:
            self._json_response(400, {"success": False, "error": "Missing keyword"})
            return
        abs_path = os.path.normpath(rel) if rel else os.path.expanduser("~")
        if not os.path.isdir(abs_path):
            self._json_response(404, {"success": False, "error": "Directory not found"})
            return
        results = []
        kw = keyword.lower()
        try:
            for entry in os.scandir(abs_path):
                if kw in entry.name.lower():
                    try:
                        results.append(self._file_info_dict(entry.path))
                    except (PermissionError, OSError):
                        continue
                if len(results) >= 100:
                    break
        except PermissionError:
            pass
        self._json_response(200, {"success": True, "data": {"keyword": keyword, "path": rel, "results": results}})

    # ── /api/fs/info ──
    def _fs_info(self):
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.exists(abs_path):
            self._json_response(404, {"success": False, "error": "Path not found"})
            return
        info = self._file_info_dict(abs_path)
        info["is_dir"] = os.path.isdir(abs_path)
        info["is_file"] = os.path.isfile(abs_path)
        info["absolute_path"] = abs_path.replace(os.sep, "/")
        self._json_response(200, {"success": True, "data": info})

    # ── /api/fs/thumbnail ──
    def _fs_thumbnail(self):
        from PIL import Image
        params = parse_qs(urlparse(self.path).query)
        rel = params.get("path", [""])[0]
        size = int(params.get("size", ["128"])[0])
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.isfile(abs_path):
            self._json_response(404, {"success": False, "error": "File not found"})
            return
        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            self._json_response(400, {"success": False, "error": "Not an image"})
            return
        try:
            img = Image.open(abs_path)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            data = buf.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    # ── /api/fs/delete ──
    def _fs_delete(self):
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response(400, {"success": False, "error": "Invalid JSON"})
            return
        rel = data.get("path", "")
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if not os.path.exists(abs_path):
            self._json_response(404, {"success": False, "error": "Path not found"})
            return
        try:
            if os.path.isdir(abs_path):
                shutil.rmtree(abs_path)
            else:
                os.remove(abs_path)
            self._json_response(200, {"success": True, "message": "Deleted"})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    # ── /api/fs/create-folder ──
    def _fs_create_folder(self):
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response(400, {"success": False, "error": "Invalid JSON"})
            return
        rel = data.get("path", "")
        if not rel:
            self._json_response(400, {"success": False, "error": "Missing path"})
            return
        abs_path = os.path.normpath(rel)
        if os.path.exists(abs_path):
            self._json_response(409, {"success": False, "error": "Already exists"})
            return
        try:
            os.makedirs(abs_path, exist_ok=False)
            self._json_response(200, {"success": True, "message": "Created", "path": abs_path.replace(os.sep, "/")})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    # ── /api/fs/rename ──
    def _fs_rename(self):
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response(400, {"success": False, "error": "Invalid JSON"})
            return
        rel = data.get("path", "")
        new_name = data.get("new_name", "")
        if not rel or not new_name:
            self._json_response(400, {"success": False, "error": "Missing path or new_name"})
            return
        illegal = '<>:"/\\|?*'
        for ch in illegal:
            if ch in new_name:
                self._json_response(400, {"success": False, "error": f"Illegal character: {ch}"})
                return
        abs_path = os.path.normpath(rel)
        if not os.path.exists(abs_path):
            self._json_response(404, {"success": False, "error": "Path not found"})
            return
        new_path = os.path.join(os.path.dirname(abs_path), new_name)
        if os.path.exists(new_path):
            self._json_response(400, {"success": False, "error": "Target name already exists"})
            return
        try:
            os.rename(abs_path, new_path)
            self._json_response(200, {"success": True, "message": "Renamed", "new_path": new_path.replace(os.sep, "/")})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    # ── /api/fs/copy ──
    def _fs_copy(self):
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response(400, {"success": False, "error": "Invalid JSON"})
            return
        rel = data.get("path", "")
        dest = data.get("dest_path", "")
        if not rel or not dest:
            self._json_response(400, {"success": False, "error": "Missing path or dest_path"})
            return
        abs_path = os.path.normpath(rel)
        abs_dest = os.path.normpath(dest)
        if not os.path.exists(abs_path):
            self._json_response(404, {"success": False, "error": "Source not found"})
            return
        if os.path.exists(abs_dest):
            self._json_response(400, {"success": False, "error": "Destination already exists"})
            return
        try:
            if os.path.isdir(abs_path):
                shutil.copytree(abs_path, abs_dest)
            else:
                shutil.copy2(abs_path, abs_dest)
            self._json_response(200, {"success": True, "message": "Copied", "dest_path": abs_dest.replace(os.sep, "/")})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})


# ── Path resolution helper (shared by _handle_file, _handle_video, do_HEAD) ──
def _resolve_path(file_path: str) -> str | None:
    """Resolve a file path for serving, supporting both relative and absolute paths.

    Strategy:
      1. Try as relative path joined with RECORDINGS_ROOT.
      2. If that doesn't exist and path looks absolute, try it directly
         (backward compat for old URLs that used absolute Windows paths).
      3. Security: reject any path outside RECORDINGS_ROOT.
    """
    norm_root = os.path.normpath(RECORDINGS_ROOT)

    # Try relative
    abs_path = os.path.normpath(os.path.join(RECORDINGS_ROOT, file_path))
    if abs_path.startswith(norm_root) and os.path.exists(abs_path):
        return abs_path

    # Fallback: try as absolute path (for old URLs)
    if os.path.isabs(file_path):
        abs_path = os.path.normpath(file_path)
        if abs_path.startswith(norm_root) and os.path.exists(abs_path):
            return abs_path

    return None


class SilentHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that silently ignores connection errors."""
    allow_reuse_address = True
    def handle_error(self, request, client_address):
        pass  # Browser frequently aborts connections


class HistoryServer:
    """Manages the HTTP server lifecycle."""

    def __init__(self):
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    @property
    def port(self) -> int:
        return self._port

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self, open_browser: bool = True):
        """Start the history server on the first available port."""
        global _server
        _server = self

        for port in PORT_RANGE:
            try:
                self._httpd = SilentHTTPServer(("127.0.0.1", port), HistoryHandler)
                self._port = port
                break
            except OSError:
                continue
        else:
            print("[HistoryServer] No available port in range 8080-8090")
            return

        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="history-server",
        )
        self._thread.start()
        url = f"http://127.0.0.1:{self._port}"
        print(f"[HistoryServer] Running at {url}")

        if open_browser:
            webbrowser.open(url)

    def stop(self):
        """Stop the server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
            print("[HistoryServer] Stopped")

    def _serve(self):
        """Server loop (runs in daemon thread)."""
        if self._httpd:
            self._httpd.serve_forever()


def start_server(open_browser: bool = True) -> "HistoryServer":
    """Convenience function to start the history server."""
    server = HistoryServer()
    server.start(open_browser)
    return server


def get_server() -> "HistoryServer | None":
    """Return the currently running server instance."""
    global _server
    return _server
