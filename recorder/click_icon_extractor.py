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
                          output_path: str, icon_size: int = DEFAULT_ICON_SIZE) -> bool:
    """从完整截图中以点击坐标为中心裁剪图标。"""
    if not _HAS_PIL or not os.path.exists(screenshot_path):
        return False
    try:
        img = Image.open(screenshot_path)
        w, h = img.size
        half = icon_size // 2

        # 计算裁剪区域（保证不超出图片边界）
        left = max(0, click_x - half)
        top = max(0, click_y - half)
        right = min(w, left + icon_size)
        bottom = min(h, top + icon_size)
        left = max(0, right - icon_size)
        top = max(0, bottom - icon_size)

        crop = img.crop((left, top, right, bottom))
        # 如果需要，填充到 64×64
        if crop.size != (icon_size, icon_size):
            canvas = Image.new("RGB", (icon_size, icon_size), (40, 40, 40))
            canvas.paste(crop, (0, 0))
            crop = canvas

        crop.save(output_path, "JPEG", quality=85)
        return True
    except Exception:
        return False


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
            if _crop_from_screenshot(ss_abs, click_x, click_y, icon_path, icon_size):
                item["icon_file"] = icon_filename
                item["source"] = f"{ss_rel} (cropped {icon_size}×{icon_size})"
            else:
                item["icon_file"] = ""
                item["source"] = "(截图缺失，无法裁剪)"

        items.append(item)

    # ── 6. 生成 mapping.json ──
    mapping = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "icon_size": f"{icon_size}x{icon_size}",
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
    return result


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
