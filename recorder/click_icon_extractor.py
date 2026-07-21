"""click_icon_extractor.py — 从录制报告中自动提取点击坐标对应的图标

根据 report JSON 中的点击坐标 + ui_controls/session.json 的控件 bbox，
自动匹配合成每个点击步骤的图标（64×64），输出到 clicked_icons/ 目录。

工作流程:
  1. 读取 report_{project}.json → 提取所有鼠标点击步骤
  2. 读取 ui_controls/session.json → 建立 bbox 索引
  3. 对每个点击坐标 (x, y):
     - 命中 bbox → 从 ui_controls/crops/{id}_{name}.jpg 复制
     - 未命中   → 从对应截图中以坐标为中心裁剪 64×64 区域
  4. 输出到 inputs/clicked_icons/ + mapping.json
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ── 常量 ──────────────────────────────────────────────────────────
DEFAULT_ICON_SIZE = 64
BBOX_TOLERANCE = 15  # 坐标容差（像素），处理 UIA bbox 与屏幕坐标小幅偏移

# 截图裁剪参数（非 UIA 命中时的 fallback 策略）
CROP_DEFAULT_RADIUS = 32     # 默认裁剪半径（像素），以点击坐标为中心向四周扩展
CROP_MIN_SIZE = 16           # 控件最小边长（像素），低于此值等比放大至此
CROP_MAX_SIZE = 128          # 控件最大边长（像素），超过此值等比缩小至此
# ══════════════════════════════════════════════════════════════════
# 数据加载
# ══════════════════════════════════════════════════════════════════

def load_report_json(report_path: str) -> Dict:
    """加载 report JSON，返回 {steps: [...], project: ..., ...}。"""
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_session_json(session_path: str) -> Dict:
    """加载 ui_controls/session.json，返回完整的 session 数据。"""
    with open(session_path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_all_elements(session_data: Dict) -> List[Dict]:
    """从 session.json 的所有 captures 中收集所有元素（去重 by id）。"""
    seen: Dict[int, Dict] = {}
    for cap in session_data.get("captures", []):
        for elem in cap.get("elements", []):
            eid = elem.get("id")
            if eid not in seen:
                seen[eid] = elem
    return list(seen.values())


def find_input_log(inputs_dir: str) -> Optional[str]:
    """在 inputs 目录中查找 input_log_*.txt。"""
    for f in os.listdir(inputs_dir):
        if f.startswith("input_log_") and f.endswith(".txt"):
            return os.path.join(inputs_dir, f)
    return None


def read_target_app(input_log_path: str) -> Optional[Dict]:
    """从 input_log 的 CONFIG 行（首条事件）读取用户选择的目标应用。

    Returns:
        目标应用 dict（name, window_title, process_name, process_path, pid），
        或 None（旧格式日志无此字段）。
    """
    try:
        with open(input_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # CONFIG 行的 window == "System Info"
                if event.get("window") == "System Info" and "target_app" in event:
                    return event["target_app"]
                break  # 只检查首条非注释行
    except Exception:
        pass
    return None


def collect_programs_from_log(input_log_path: str) -> Tuple[List[Dict], Dict[str, str]]:
    """从 input log 解析所有出现过的程序/窗口，返回 (programs列表, 窗口标题→程序名映射)。

    每条 program dict:
        name:         显示名称（优先 process_name，其次 window title）
        window_title:  窗口标题
        process_name:  进程文件名
        process_path:  完整二进制路径
        pid:           进程 ID

    兼容旧格式日志（无 process_name 字段）：用 window_title 作为 name。
    """
    programs_map: Dict[str, Dict] = {}  # key = 去重标识 (process_path or window_title)
    window_to_program: Dict[str, str] = {}  # window_title → program name

    try:
        with open(input_log_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                title = event.get("window", "")
                if not title or title == "System Info":
                    continue

                proc_name = event.get("process_name", "")
                proc_path = event.get("process_path", "")
                pid = event.get("pid", 0)

                # 构建唯一标识
                if proc_path:
                    dedup_key = proc_path
                elif proc_name:
                    dedup_key = proc_name
                else:
                    dedup_key = title

                if dedup_key not in programs_map:
                    display_name = proc_name if proc_name else title
                    programs_map[dedup_key] = {
                        "name": display_name,
                        "window_title": title,
                        "process_name": proc_name,
                        "process_path": proc_path,
                        "pid": pid,
                    }
                    window_to_program[title] = display_name

    except Exception as e:
        print(f"[click_icon] 警告: 解析 input_log 失败: {e}")

    programs_list = list(programs_map.values())
    # 按 name 排序（Recorder 放最后）
    recorder_idx = None
    for i, p in enumerate(programs_list):
        if "recorder" in p["name"].lower() or "录制" in p["window_title"]:
            recorder_idx = i
            break
    if recorder_idx is not None and len(programs_list) > 1:
        p = programs_list.pop(recorder_idx)
        programs_list.append(p)
        # 同时更新映射顺序
        rec_title = p["window_title"]
        rec_name = p["name"]
        del window_to_program[rec_title]
        window_to_program[rec_title] = rec_name

    return programs_list, window_to_program


# ══════════════════════════════════════════════════════════════════
# 坐标匹配
# ══════════════════════════════════════════════════════════════════

def point_in_bbox(x: int, y: int, bbox: Tuple[int, int, int, int],
                  tolerance: int = BBOX_TOLERANCE) -> bool:
    """判断 (x, y) 是否在 bbox (l, t, r, b) 内（含容差）。"""
    l, t, r, b = bbox
    return (l - tolerance <= x <= r + tolerance and
            t - tolerance <= y <= b + tolerance)


def bbox_center(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
    """返回 bbox 的中心坐标。"""
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def match_click_to_element(click_x: int, click_y: int,
                           elements: List[Dict],
                           tolerance: int = BBOX_TOLERANCE) -> Optional[Dict]:
    """将点击坐标匹配到 UI 控件元素。

    当点击点落在多个嵌套/重叠的 bbox 内时（如 Tab 容器 vs 子 TabItem），
    优先选择 **bbox 面积最小**的精确子元素，避免匹配到大容器。

    Returns:
        匹配的元素 dict，或 None。
    """
    candidates = []

    for elem in elements:
        bbox = (elem["bbox_left"], elem["bbox_top"],
                elem["bbox_right"], elem["bbox_bottom"])
        if point_in_bbox(click_x, click_y, bbox, tolerance=tolerance):
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            cx, cy = bbox_center(bbox)
            dist = (click_x - cx) ** 2 + (click_y - cy) ** 2
            # 排序优先级: 面积越小越精确 > 距离中心越近
            candidates.append((area, dist, elem))

    if not candidates:
        return None

    # 先按面积升序（最精确优先），面积相同时按距离中心近者优先
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2]


# ══════════════════════════════════════════════════════════════════
# 图标生成：命中 → 复制 crop / 未命中 → 从截图裁剪
# ══════════════════════════════════════════════════════════════════

def _sanitize_filename(name: str, max_len: int = 24) -> str:
    """清理文件名中的非法字符并截断。"""
    import re
    # 替换非法字符为下划线
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe = safe.strip().strip('.')
    if not safe:
        safe = "unknown"
    if len(safe) > max_len:
        safe = safe[:max_len]
    return safe


def _build_icon_filename(step_num: int, x: int, y: int, label: str) -> str:
    """生成图标文件名: step_{NN}_({x},{y})_{label}.jpg"""
    clean = _sanitize_filename(label)
    return f"step_{step_num:02d}_({x},{y})_{clean}.jpg"


def _copy_crop_icon(elem: Dict, output_path: str, crops_dir: str) -> bool:
    """从 crops 目录复制已裁剪的控件图片。"""
    eid = elem["id"]
    safe_name = _sanitize_filename(elem["name"])
    src = os.path.join(crops_dir, f"{eid}_{safe_name}.jpg")
    if os.path.exists(src):
        shutil.copy2(src, output_path)
        return True
    # 尝试 .png
    src_png = os.path.join(crops_dir, f"{eid}_{safe_name}.png")
    if os.path.exists(src_png):
        shutil.copy2(src_png, output_path)
        return True
    return False


def _crop_from_screenshot(screenshot_path: str, click_x: int, click_y: int,
                          output_path: str, icon_size: int = DEFAULT_ICON_SIZE) -> tuple:
    """从完整截图中以点击坐标为中心进行对称裁剪。

    策略：
      1. 以点击坐标为中心，使用默认半径（CROP_DEFAULT_RADIUS）裁剪正方形区域
      2. 靠近屏幕边缘时，对称收缩另一侧保证点击始终在裁剪中心
      3. 动态适配尺寸（CROP_MIN_SIZE ~ CROP_MAX_SIZE 范围）

    注意：不采用 getbbox 内容感知，因为低对比度 GUI（微信等）中 getbbox
    会误将整个窗口背景检测为"前景"，导致裁剪区域过大。
    """
    if not _HAS_PIL or not os.path.exists(screenshot_path):
        return (False, 0, 0)
    try:
        img = Image.open(screenshot_path)
        w, h = img.size
        r = CROP_DEFAULT_RADIUS

        # ── 以点击坐标为中心，向四方向扩展半径 r ──
        left   = click_x - r
        top    = click_y - r
        right  = click_x + r
        bottom = click_y + r

        # ── clamp 到图像边界 ──
        left   = max(0, left)
        top    = max(0, top)
        right  = min(w, right)
        bottom = min(h, bottom)

        # ── 对称收缩：clamp 后不对称时，缩小另一侧保证点击在中心 ──
        actual_left   = click_x - left
        actual_right  = right - click_x
        actual_top    = click_y - top
        actual_bottom = bottom - click_y
        radius_h = min(actual_left, actual_right)
        radius_v = min(actual_top, actual_bottom)

        left   = click_x - radius_h
        top    = click_y - radius_v
        right  = click_x + radius_h
        bottom = click_y + radius_v

        crop = img.crop((int(left), int(top), int(right), int(bottom)))

        # ── 动态尺寸适配（保持原始比例，仅约束上下限） ──
        crop_w, crop_h = crop.size
        long_edge = max(crop_w, crop_h)
        if long_edge < CROP_MIN_SIZE:
            scale = CROP_MIN_SIZE / long_edge
            crop = crop.resize((int(crop_w * scale), int(crop_h * scale)), Image.LANCZOS)
        elif long_edge > CROP_MAX_SIZE:
            scale = CROP_MAX_SIZE / long_edge
            crop = crop.resize((int(crop_w * scale), int(crop_h * scale)), Image.LANCZOS)
        crop.save(output_path, "JPEG", quality=85)
        return (True, crop.size[0], crop.size[1])
    except Exception:
        return (False, 0, 0)

def _resolve_screenshot_abs(rel_path: str, inputs_dir: str) -> str:
    """将 report 中的相对 screenshot_file 解析为绝对路径。"""
    # rel_path 通常是 "screenshots/0001.jpg"
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.join(inputs_dir, rel_path)


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def extract_click_icons(
    report_json_path: str,
    session_json_path: str,
    inputs_dir: str,
    icon_size: int = DEFAULT_ICON_SIZE,
    tolerance: int = BBOX_TOLERANCE,
) -> Dict:
    """主入口：从录制数据提取点击图标。

    Args:
        report_json_path: report_{project}.json 的完整路径
        session_json_path: ui_controls/session.json 的完整路径
        inputs_dir: inputs/ 目录
        icon_size: 输出图标尺寸（默认 64×64）
        tolerance: bbox 容差像素

    Returns:
        {
            "ok": bool,
            "output_dir": str,          # clicked_icons 目录路径
            "mapping_path": str,        # mapping.json 路径
            "total_clicks": int,
            "hits": int,                # 命中 bbox 数量
            "misses": int,              # 未命中数量
            "items": [...],             # 每个 step 的详细信息
            "error": str or None,
        }
    """
    result: Dict = {
        "ok": False,
        "output_dir": "",
        "mapping_path": "",
        "total_clicks": 0,
        "hits": 0,
        "misses": 0,
        "items": [],
        "error": None,
    }

    crops_dir = os.path.join(inputs_dir, "ui_controls", "crops")

    # ── 1. 加载数据 ──
    if not os.path.exists(report_json_path):
        result["error"] = f"report JSON 不存在: {report_json_path}"
        return result

    try:
        report = load_report_json(report_json_path)
    except Exception as e:
        result["error"] = f"无法解析 report JSON: {e}"
        return result

    elements = []
    if os.path.exists(session_json_path):
        try:
            session_data = load_session_json(session_json_path)
            elements = collect_all_elements(session_data)
            print(f"[click_icon] 加载 {len(elements)} 个控件 bbox")
        except Exception as e:
            print(f"[click_icon] 无法加载 session.json: {e}（将全部使用截图裁剪）")
    else:
        print(f"[click_icon] session.json 不存在，全部使用截图裁剪")

    # ── 2. 筛选鼠标点击步骤 ──
    click_steps = []
    for step in report.get("steps", []):
        if step.get("category") == "mouse":
            coords = step.get("coordinates")
            if coords and coords.get("x") is not None and coords.get("y") is not None:
                click_steps.append(step)

    if not click_steps:
        result["error"] = "没有找到带坐标的鼠标点击步骤"
        return result

    # ── 3. 从 input_log 收集程序信息（优先使用目标应用）──
    input_log = find_input_log(inputs_dir)
    programs_list: List[Dict] = []
    window_to_program: Dict[str, str] = {}
    target_app: Optional[Dict] = None  # 目标应用引用（用作默认程序信息）
    if input_log:
        # 优先读取用户手动选择的目标应用
        target_app = read_target_app(input_log)
        if target_app:
            programs_list = [target_app]
            if target_app.get("window_title"):
                window_to_program[target_app["window_title"]] = target_app.get("name", "")
            print(f"[click_icon] 目标应用: {target_app.get('name', '?')} (pid={target_app.get('pid', '?')})")
        else:
            # 旧格式：回退到全量扫描所有窗口
            try:
                programs_list, window_to_program = collect_programs_from_log(input_log)
                print(f"[click_icon] 发现 {len(programs_list)} 个程序/窗口（旧格式）")
                for p in programs_list:
                    print(f"    - {p['name']} (pid={p.get('pid', '?')}, path={p.get('process_path', 'N/A')})")
            except Exception as e:
                print(f"[click_icon] 警告: 收集程序信息失败: {e}")
    else:
        print(f"[click_icon] 未找到 input_log（旧格式录制），程序信息不可用")

    # ── 4. 创建输出目录 ──
    output_dir = os.path.join(inputs_dir, "clicked_icons")
    os.makedirs(output_dir, exist_ok=True)
    result["output_dir"] = output_dir

    # ── 5. 逐个生成图标 ──
    hits = 0
    misses = 0
    items = []

    for step in click_steps:
        step_num = step["step"]
        click_x = step["coordinates"]["x"]
        click_y = step["coordinates"]["y"]
        window = step.get("window", "")

        # 查找该窗口对应的程序信息
        prog_name = window_to_program.get(window, "")
        prog_info = None
        if prog_name:
            for p in programs_list:
                if p["name"] == prog_name or p["window_title"] == window:
                    prog_info = p
                    break
        # 目标应用模式下，未匹配到窗口时默认使用目标应用信息
        if not prog_info and target_app:
            prog_info = target_app

        item = {
            "step": step_num,
            "click_x": click_x,
            "click_y": click_y,
            "window": window,
            "program_name": prog_info["process_name"] if prog_info else (prog_name or ""),
            "program_path": prog_info["process_path"] if prog_info else "",
            "pid": prog_info.get("pid", 0) if prog_info else 0,
            "matched": False,
            "element_id": None,
            "element_name": None,
            "element_type": None,
            "element_bbox": None,
            "icon_file": "",
            "source": "",
        }

        # 尝试匹配元素
        icon_generated = False
        matched = match_click_to_element(click_x, click_y, elements, tolerance)

        if matched:
            # 尝试从 crops 复制已裁剪的控件图片
            icon_filename = _build_icon_filename(step_num, click_x, click_y, matched["name"])
            icon_path = os.path.join(output_dir, icon_filename)

            if _copy_crop_icon(matched, icon_path, crops_dir):
                hits += 1
                item["matched"] = True
                item["element_id"] = matched["id"]
                item["element_name"] = matched["name"]
                item["element_type"] = matched.get("type", "")
                item["element_bbox"] = [matched["bbox_left"], matched["bbox_top"],
                                         matched["bbox_right"], matched["bbox_bottom"]]
                item["icon_file"] = icon_filename
                item["source"] = f"ui_controls/crops/{matched['id']}_{matched['name']}.jpg"
                icon_generated = True
            else:
                print(f"[click_icon] step {step_num}: crop 文件缺失，回退截图裁剪")

        # 未命中 bbox 或 crop 缺失 → 从截图裁剪
        if not icon_generated:
            misses += 1
            use_label = window if window else f"pos_{click_x}_{click_y}"
            icon_filename = _build_icon_filename(step_num, click_x, click_y, use_label)
            icon_path = os.path.join(output_dir, icon_filename)

            ss_rel = step.get("screenshot_file", "")
            ss_abs = _resolve_screenshot_abs(ss_rel, inputs_dir)
            ok, cw, ch = _crop_from_screenshot(ss_abs, click_x, click_y, icon_path, icon_size)
            if ok:
                item["icon_file"] = icon_filename
                item["source"] = f"{ss_rel} (cropped {cw}×{ch})"
            else:
                item["icon_file"] = ""
                item["source"] = "(截图缺失，无法裁剪)"

        items.append(item)

    # ── 6. 生成 mapping.json ──
    mapping = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "icon_size": f"{CROP_DEFAULT_RADIUS*2}x{CROP_DEFAULT_RADIUS*2} (actual varies)",
        "total_clicks": len(click_steps),
        "hits": hits,
        "misses": misses,
        "programs": programs_list,       # 录制中涉及的所有程序/窗口
        "items": items,
    }
    mapping_path = os.path.join(output_dir, "mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    result["ok"] = True
    result["total_clicks"] = len(click_steps)
    result["hits"] = hits
    result["misses"] = misses
    result["mapping_path"] = mapping_path
    result["items"] = items

    print(f"[click_icon] 完成: {hits} 命中 / {misses} 未命中 → {output_dir}")

    # ── 7. 生成 HAR 协议文件 ──
    try:
        generate_har(report_json_path, mapping, target_app, output_dir)
    except Exception as e:
        print(f"[click_icon] HAR 生成失败: {e}")

    result["har_path"] = os.path.join(output_dir, "default.har")
    return result


# ══════════════════════════════════════════════════════════════════
# HAR 协议生成
# ══════════════════════════════════════════════════════════════════

def _step_to_har_entry(step: Dict, icon_map: Dict[int, str]) -> Optional[Dict]:
    """将 report 中的一个 step 转换为 HAR entry，返回 None 表示跳过。"""
    category = step.get("category", "")
    message = step.get("message", "")
    description = step.get("description", "")
    step_num = step["step"]
    icon_file = icon_map.get(step_num, "")

    if category == "mouse":
        if "双击" in description:
            method = "gui_double_click"
        elif "右键" in description:
            method = "gui_right_click"
        else:
            method = "gui_click"

        if icon_file:
            return {"method": method, "image": icon_file, "text": "", "timeout": 30}
        coords = step.get("coordinates", {})
        if coords:
            x, y = coords.get("x"), coords.get("y")
            if x is not None and y is not None:
                return {"method": method, "image": "", "text": f"({x}, {y})", "timeout": 10}
        return None

    elif category == "keyboard":
        key = message.replace("Key Press: ", "").strip()
        return {"method": "gui_keyboard", "image": "", "text": key, "timeout": 10}

    elif category == "hotkey":
        hotkey = message.replace("Hotkey: ", "").strip()
        return {"method": "gui_keyboard", "image": "", "text": hotkey, "timeout": 10}

    elif category == "scroll":
        direction = "+5" if "ScrollDown" in message else "-5"
        return {"method": "gui_wheel", "image": "", "text": direction, "timeout": 10}

    return None  # drag / system 跳过


def generate_har(report_json_path: str, mapping: Dict, target_app: Optional[Dict],
                 output_dir: str, project_name: str = "") -> Optional[str]:
    """从 report JSON + mapping 生成 GuiRunner 6.0 兼容的 .har 协议文件。

    HAR 结构:
      gui_start → gui_focus_current_window → [steps...] → gui_stop

    Returns:
        har 文件路径，或 None（无可用步骤时）。
    """
    report = load_report_json(report_json_path)
    steps = report.get("steps", [])
    if not steps:
        print("[click_icon] 无步骤数据，跳过 HAR 生成")
        return None

    # 构建 step_num → icon_filename 映射
    icon_map = {}
    for item in mapping.get("items", []):
        if item.get("icon_file"):
            icon_map[item["step"]] = item["icon_file"]

    entries = []

    # 1. gui_start
    if target_app and target_app.get("process_path"):
        entries.append({
            "method": "gui_start",
            "image": "",
            "text": target_app["process_path"],
            "timeout": 30,
        })

    # 2. gui_focus_current_window
    entries.append({
        "method": "gui_focus_current_window",
        "image": "",
        "text": "",
        "timeout": 30,
    })

    # 3. 遍历 report steps
    for step in steps:
        entry = _step_to_har_entry(step, icon_map)
        if entry:
            entries.append(entry)

    # 4. gui_stop
    if target_app and target_app.get("process_path"):
        entries.append({
            "method": "gui_stop",
            "image": "",
            "text": target_app["process_path"],
            "timeout": 30,
        })

    har = {
        "log": {
            "version": "6.0",
            "creator": {"name": "GuiRunner", "version": "0.1"},
            "taskmode": "recorder",
            "entries": entries,
        }
    }

    har_path = os.path.join(output_dir, "default.har")
    with open(har_path, "w", encoding="utf-8") as f:
        json.dump(har, f, ensure_ascii=False, indent=2)

    print(f"[click_icon] HAR 已生成: {har_path} ({len(entries)} 个 entry)")
    return har_path


def push_har_to_guirunner(har_path: str, project_name: str,
                          base_url: str = "http://127.0.0.1:60000") -> bool:
    """将 HAR 文件推送到 GuiRunner 后端，创建/更新脚本工程。

    调用 POST /api/editor/project/create_or_update (multipart/form-data)，
    参考 guirunnercore/gui_project.py 的 MultipartEncoder 方式。
    """
    try:
        import requests
        from requests_toolbelt import MultipartEncoder
    except ImportError:
        print("[click_icon] 缺少 requests / requests-toolbelt，跳过推送")
        return False

    url = base_url.rstrip("/") + "/api/editor/project/create_or_update"

    fields = {
        "url": "",
        "repo_url": "",
        "project": project_name,
        "protocol": "GUI",
        "description": "",
        "mode": "edit",
        "script_path": "",
        "template_path": har_path,
        "notify": "ws",
    }

    try:
        data = MultipartEncoder(fields=fields)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Content-Type": data.content_type,
            "Content-length": str(data.len),
        }
        res = requests.post(url, headers=headers, data=data.to_string(), timeout=10)
        result = res.json()
        print(f"[click_icon] 推送 GuiRunner: {result}")
        ok = result.get("code") == 1000
        if ok:
            print(f"[click_icon] 推送成功: {project_name}")
        return ok
    except Exception as e:
        print(f"[click_icon] 推送失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
# 公共导出函数（recorder 详情页 + urecorder 共用）
# ══════════════════════════════════════════════════════════════════

def export_recording_to_guirunner(rec_dir: str, guirunner_url: str) -> dict:
    """从录制目录导出到 GuiRunner（完整管线：report → mapping → HAR → push）。

    recorder 详情页和 urecorder 共用此函数，避免两套 HAR 构建逻辑。

    Args:
        rec_dir: 录制目录路径（如 C:/Users/.../recording_20260625_222701）
        guirunner_url: GuiRunner 后端地址

    Returns:
        {"ok": True, "project": str, "editor_url": str}  或
        {"ok": False, "message": str}
    """
    rec_id = os.path.basename(rec_dir)
    inputs_dir = os.path.join(rec_dir, "inputs")

    if not os.path.isdir(inputs_dir):
        return {"ok": False, "message": f"录制数据目录不存在: {inputs_dir}"}

    # 查找 input_log
    log_file = find_input_log(inputs_dir)
    if not log_file:
        return {"ok": False, "message": "未找到 input_log 文件"}

    # 1. 确保 report JSON 存在
    report_path = os.path.join(inputs_dir, "report_" + rec_id + ".json")
    if not os.path.isfile(report_path):
        try:
            from recorder.report_generator import parse_log, generate_json
            events = parse_log(log_file)
            ss_dir = os.path.join(inputs_dir, "screenshots")
            video_path = ""
            for f in os.listdir(inputs_dir):
                if f.lower().endswith(".mp4"):
                    video_path = os.path.join(inputs_dir, f)
                    break
            generate_json(events, ss_dir, report_path, rec_id, video_path)
            print(f"[export_guirunner] report JSON 已生成: {report_path}")
        except Exception as e:
            return {"ok": False, "message": f"Report JSON 生成失败: {e}"}

    # 2. 确保 clicked_icons/mapping.json 存在
    icons_dir = os.path.join(inputs_dir, "clicked_icons")
    mapping_path = os.path.join(icons_dir, "mapping.json")
    if not os.path.isfile(mapping_path):
        try:
            from recorder.report_generator import generate_click_icons
            result = generate_click_icons(inputs_dir, rec_id)
            if not result or not result.get("ok"):
                return {"ok": False, "message": "点击图标生成失败：无点击事件"}
            print(f"[export_guirunner] mapping.json 已生成: {mapping_path}")
        except Exception as e:
            return {"ok": False, "message": f"点击图标生成失败: {e}"}

    # 3. 确保 HAR 存在
    har_path = os.path.join(icons_dir, "default.har")
    if not os.path.isfile(har_path):
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            target_app = read_target_app(log_file) if log_file else None
            result_path = generate_har(report_path, mapping, target_app, icons_dir, rec_id)
            if not result_path:
                return {"ok": False, "message": "HAR 生成失败：无可执行步骤"}
            har_path = result_path
            print(f"[export_guirunner] HAR 已生成: {har_path}")
        except Exception as e:
            return {"ok": False, "message": f"HAR 生成失败: {e}"}

    # 4. 推送到 GuiRunner
    ok = push_har_to_guirunner(har_path, rec_id, base_url=guirunner_url)
    if ok:
        editor_url = guirunner_url.rstrip("/") + "/static/webeditor/index.html#/?project=" + rec_id
        print(f"[export_guirunner] 推送成功: {rec_id}")
        return {"ok": True, "project": rec_id, "editor_url": editor_url}
    else:
        return {
            "ok": False,
            "message": f"请确保 GuiRunner 后端已启动 ({guirunner_url})",
            "har_path": har_path.replace("\\", "/"),
        }


# ══════════════════════════════════════════════════════════════════
# CLI 入口（独立运行 / 录制后手动补生成）
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python click_icon_extractor.py <录制目录>")
        print("  例: python click_icon_extractor.py C:\\Users\\...\\recording_20260625_221040")
        sys.exit(1)

    base_dir = sys.argv[1]
    inputs_dir = os.path.join(base_dir, "inputs")
    report_json = None

    # 自动查找 report JSON
    for f in os.listdir(inputs_dir):
        if f.startswith("report_") and f.endswith(".json"):
            report_json = os.path.join(inputs_dir, f)
            break

    if not report_json:
        print(f"错误: 在 {inputs_dir} 中未找到 report_*.json")
        sys.exit(1)

    session_json = os.path.join(inputs_dir, "ui_controls", "session.json")

    result = extract_click_icons(
        report_json_path=report_json,
        session_json_path=session_json,
        inputs_dir=inputs_dir,
    )

    if result["ok"]:
        print(f"\n[OK] 图标已生成到: {result['output_dir']}")
        print(f"   mapping: {result['mapping_path']}")
        print(f"   命中: {result['hits']}  /  未命中: {result['misses']}")
    else:
        print(f"\n[FAIL] 失败: {result['error']}")
