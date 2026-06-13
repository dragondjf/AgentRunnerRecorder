"""
UIRecorderCore Bridge — 将 AgentRunnerRecorder 录制输出无缝桥接到 UIRecorderCore。

包含三个核心组件：
  - UIRecorderCoreServer  后台线程启动 UIRecorderCore Flask 服务
  - RecordingConverter    录制数据转换（ARR JSONL → URC records.json）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────────────────────
# UIRecorderCore 代码库位于 AgentRunnerRecorder/urecorder/
URC_DIR = Path(__file__).resolve().parent.parent / "urecorder"
URC_FILESTORAGE = URC_DIR / "filestorage"
URC_PORT = 12000
URC_HOST = "127.0.0.1"
URC_BASE = f"http://{URC_HOST}:{URC_PORT}"


# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def ensure_urc_importable() -> bool:
    """将 urecorder/ 的父目录加入 sys.path，确保相对导入正常工作。"""
    parent = str(URC_DIR.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return URC_DIR.is_dir()


def _check_urc_alive() -> bool:
    """检查 UIRecorderCore Flask 服务是否已就绪。"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{URC_BASE}/api/v1/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _call_urc_api(path: str, params: dict = None, timeout: int = 5) -> bool:
    """调用 UIRecorderCore API，返回是否成功。"""
    try:
        import urllib.request
        import urllib.parse
        url = f"{URC_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════
# UIRecorderCore 服务管理
# ══════════════════════════════════════════════════════════════════

class UIRecorderCoreServer:
    """在后台 daemon 线程中启动 UIRecorderCore Flask 服务。"""

    def __init__(self, host: str = URC_HOST, port: int = URC_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._thread: threading.Thread | None = None
        self._ready = False
        self._lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        return self._ready

    def start(self, wait_ready: bool = True, timeout: float = 15.0) -> bool:
        """启动 UIRecorderCore 服务。

        参数:
            wait_ready: 是否等待服务就绪
            timeout: 最长等待秒数
        返回:
            True 表示服务已就绪
        """
        with self._lock:
            if self._ready:
                return True

            # 先检查是否已有外部实例在运行
            if _check_urc_alive():
                self._ready = True
                return True

            # 确保 urecorder/ 可导入
            if not ensure_urc_importable():
                raise RuntimeError(
                    f"UIRecorderCore 代码库不存在: {URC_DIR}\\n"
                    f"请确保已完整拷贝到 AgentRunnerRecorder/urecorder/"
                )

            # 启动后台线程
            self._thread = threading.Thread(
                target=self._run_flask,
                daemon=True,
                name="urc-flask",
            )
            self._thread.start()

        if wait_ready:
            return self._wait_ready(timeout)
        return False

    def _run_flask(self):
        """后台线程入口：切换 CWD → 启动 Flask。"""
        old_cwd = os.getcwd()
        os.chdir(str(URC_DIR))
        try:
            # 将父目录加入 sys.path，使 urecorder 可作为包导入
            parent = str(URC_DIR.parent)
            if parent not in sys.path:
                sys.path.insert(0, parent)
            # 同时将 urecorder/ 自身加入 sys.path，使 import flask_app 可找到
            urc_str = str(URC_DIR)
            if urc_str not in sys.path:
                sys.path.insert(0, urc_str)

            # 先以包方式导入所有需要相对导入的子模块
            # 此时 Python 将 view 识别为 urecorder.view 子包，
            # ..core 正确解析为 urecorder.core
            import urecorder.view.api_blueprint  # 含 from ..core.uiexporter import ...
            try:
                import urecorder.view.qwen_vl_bp  # 依赖 autogen，可能未安装
            except ImportError:
                print("[URC] 警告: qwen_vl_bp 导入失败（autogen 依赖未安装），AI 分析功能不可用")

            # 建立 sys.modules 别名，使 flask_app.py 中的绝对导入
            # from view.api_blueprint import api_blueprint
            # from view import qwen_vl_bp
            # 能直接从 sys.modules 中找到已加载的模块
            sys.modules["view"] = sys.modules["urecorder.view"]
            sys.modules["view.api_blueprint"] = sys.modules["urecorder.view.api_blueprint"]
            if "urecorder.view.qwen_vl_bp" in sys.modules:
                sys.modules["view.qwen_vl_bp"] = sys.modules["urecorder.view.qwen_vl_bp"]

            # 导入 postcase 依赖（config、utils）并设置别名
            import urecorder.config
            import urecorder.config.settings
            import urecorder.utils
            import urecorder.utils.llm
            sys.modules["config"] = sys.modules["urecorder.config"]
            sys.modules["config.settings"] = sys.modules["urecorder.config.settings"]
            sys.modules["utils"] = sys.modules["urecorder.utils"]
            sys.modules["utils.llm"] = sys.modules["urecorder.utils.llm"]

            # 导入并注册 postcase 蓝图
            import urecorder.postcase
            import urecorder.postcase.routes
            import urecorder.postcase.routes.test_cases
            import urecorder.postcase.routes.api_routes
            sys.modules["postcase"] = sys.modules["urecorder.postcase"]
            sys.modules["postcase.routes"] = sys.modules["urecorder.postcase.routes"]
            sys.modules["postcase.routes.test_cases"] = sys.modules["urecorder.postcase.routes.test_cases"]
            sys.modules["postcase.routes.api_routes"] = sys.modules["urecorder.postcase.routes.api_routes"]

            # 现在导入 flask_app，其绝对导入 from view.xxx 将命中 sys.modules 别名
            import flask_app
            app = flask_app.app

            # 注册 postcase 蓝图
            app.register_blueprint(
                sys.modules["postcase"].postcase_bp,
                url_prefix="/api/v1/postcase",
            )
            app.register_blueprint(
                sys.modules["postcase"].postcase_api_bp,
            )
            print("[URC] postcase 蓝图已注册")
            app.run(
                host=self.host,
                port=self.port,
                debug=False,
                use_reloader=False,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            os.chdir(old_cwd)

    def _wait_ready(self, timeout: float = 15.0) -> bool:
        """轮询等待服务就绪。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _check_urc_alive():
                self._ready = True
                return True
            time.sleep(0.5)
        return False

    def stop(self):
        """停止服务（daemon 线程在主程序退出时自动终止）。"""
        self._ready = False
        self._thread = None


# ══════════════════════════════════════════════════════════════════
# 录制数据转换
# ══════════════════════════════════════════════════════════════════

# 事件消息 → 中文标题映射
_EVENT_TITLE_MAP = {
    "LClick": "左键单击",
    "RClick": "右键单击",
    "MClick": "中键单击",
    "LDblClick": "左键双击",
    "RDblClick": "右键双击",
    "LRelease": "左键释放",
    "RRelease": "右键释放",
    "DragStart": "拖拽开始",
    "DragMove": "拖拽移动",
    "DragEnd": "拖拽结束",
    "ScrollUp": "向上滚动",
    "ScrollDown": "向下滚动",
}

# 事件消息 → 操作类型分类
_EVENT_TYPE_MAP = {
    "LClick": "mouse",
    "RClick": "mouse",
    "MClick": "mouse",
    "LDblClick": "mouse",
    "RDblClick": "mouse",
    "LRelease": "mouse",
    "RRelease": "mouse",
    "DragStart": "drag",
    "DragMove": "drag",
    "DragEnd": "drag",
    "ScrollUp": "scroll",
    "ScrollDown": "scroll",
}


def _classify_event(message: str) -> str:
    """根据消息内容分类事件类型。"""
    if not message or message.startswith("{"):
        return "system"
    for keyword, etype in _EVENT_TYPE_MAP.items():
        if keyword in message:
            return etype
    if "Hotkey:" in message:
        return "hotkey"
    if "Key Press:" in message or "Key Release:" in message:
        return "keyboard"
    return "input"


def _describe_event(message: str) -> str:
    """将事件消息转为中文描述。"""
    for keyword, title in _EVENT_TITLE_MAP.items():
        if keyword in message:
            return title
    if "Hotkey:" in message:
        keys = message.split("Hotkey:")[1].strip()
        return f"组合键 [{keys}]"
    if "Key Press:" in message:
        key = message.split("Key Press:")[1].strip()
        return f"按键 [{key}]"
    if "Key Release:" in message:
        key = message.split("Key Release:")[1].strip()
        return f"释放键 [{key}]"
    return "未知操作"


def _extract_coords(message: str) -> str:
    """从消息中提取坐标，如 '(651, 527)'。"""
    m = re.search(r"at\s*\((\d+),\s*(\d+)\)", message)
    if m:
        return f"({m.group(1)}, {m.group(2)})"
    return ""


class RecordingConverter:
    """将 AgentRunnerRecorder 的录制输出转换为 UIRecorderCore 项目。"""

    @staticmethod
    def convert(
        output_dir: str,
        project_name: str = None,
        target_project: str = None,
    ) -> str | None:
        """转换录制到 UIRecorderCore 项目。

        参数:
            output_dir: AgentRunnerRecorder 的输出目录（recording_xxx/）
            project_name: 项目名（如 recording_20240101_120000），
                          为 None 时从 output_dir 自动推断
            target_project: 目标项目名，为 None 时使用 project_name

        返回:
            项目名（成功时），None（失败时）
        """
        inputs_dir = os.path.join(output_dir, "inputs")
        if not os.path.isdir(inputs_dir):
            return None

        # 自动推断 project_name
        if project_name is None:
            project_name = os.path.basename(output_dir.rstrip("/\\\\"))

        log_file = os.path.join(inputs_dir, f"input_log_{project_name}.txt")
        ss_dir = os.path.join(inputs_dir, "screenshots")

        if not os.path.exists(log_file):
            return None

        # 1. 解析 JSONL
        events = RecordingConverter._parse_log(log_file)
        if not events:
            return None

        # 2. 转换为 slides
        slides = RecordingConverter._events_to_slides(events, ss_dir, project_name)

        # 3. 目标项目名
        proj = target_project or project_name

        # 4. 目标路径
        urc_proj_dir = URC_FILESTORAGE / proj
        urc_ss_dir = urc_proj_dir / "my_screenshots"
        urc_proj_dir.mkdir(parents=True, exist_ok=True)
        urc_ss_dir.mkdir(parents=True, exist_ok=True)

        # 5. 复制截图，更新 URL
        for slide in slides:
            src_ss = slide.pop("_screenshot_path", None)
            if src_ss and os.path.isfile(src_ss):
                ss_name = os.path.basename(src_ss)
                dst = urc_ss_dir / ss_name
                try:
                    shutil.copy2(src_ss, str(dst))
                except Exception:
                    continue
                url = (f"http://127.0.0.1:{URC_PORT}/api/v1/file"
                       f"?path={proj}/my_screenshots/{ss_name}")
                slide["url"] = url
                slide["thumbnail"] = url
                slide["markdown"] = f"![操作截图]({url})"

        # 6. 写入 records.json
        records = {
            "slides": slides,
            "lastUpdated": datetime.now().isoformat(),
            "version": "1.0",
        }
        records_path = urc_proj_dir / "records.json"
        with open(str(records_path), "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        return proj

    @staticmethod
    def _parse_log(log_path: str) -> list[dict]:
        """解析 JSONL 日志 → 事件列表。"""
        events = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    ev = json.loads(line)
                    events.append(ev)
                except json.JSONDecodeError:
                    pass
        return events

    @staticmethod
    def _events_to_slides(
        events: list[dict],
        ss_dir: str,
        project_name: str,
    ) -> list[dict]:
        """事件列表 → UIRecorderCore slides[]。"""
        slides = []
        idx = 0

        for ev in events:
            msg = ev.get("message", "")

            # 跳过系统配置事件
            if _classify_event(msg) == "system":
                continue

            idx += 1
            desc = _describe_event(msg)
            coords = _extract_coords(msg)
            ts = ev.get("timestamp", "")
            win = ev.get("window", "")
            ss_rel = ev.get("screenshot", "")  # "screenshots/0001.png"

            # 截图绝对路径
            ss_abs = ""
            if ss_rel:
                ss_abs = os.path.join(ss_dir, os.path.basename(ss_rel))

            slide = {
                "id": idx,
                "title": f"第{idx}步：{desc}",
                "context": (
                    f"操作类型: {_classify_event(msg)}; "
                    f"时间戳: {ts}; "
                    f"位置: {coords}; "
                    f"窗口: {win}"
                ),
                "markdown": "",
                "url": "",
                "operation_details": {
                    "操作": desc,
                    "原始消息": msg,
                    "位置": coords,
                    "时间戳": ts,
                    "窗口": win,
                },
                "thumbnail": "",
                "ai_result": "",
                "testCase": "需要生成包含正向测试、异常测试、边界测试的完整测试用例，重点关注安全性和用户体验。",
                "remark": "",
                "link": "",
                "_screenshot_path": ss_abs,  # 临时字段，转换后删除
            }
            slides.append(slide)

        return slides
