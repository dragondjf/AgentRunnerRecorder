"""全局路径管理模块 - 统一管理 filestorage/agentrunner/ 下所有子目录路径

所有模块通过 ``from ..config.globals import globalPaths`` 获取路径，禁止硬编码相对路径。

用法::

    from __future__ import annotations

    # 首次访问时自动创建目录（cached_property 惰性创建+缓存）
    session_file = globalPaths.CHAT_SESSIONS / "session_xxx.jsonl"

    # 手动确保目录存在
    ensure_dir(globalPaths.LOGS)
"""

from __future__ import annotations

import os
import sys
from functools import cached_property
from pathlib import Path
from typing import Union
from loguru import logger

__all__ = ("normpath", "ensure_dir", "GlobalPaths", "globalPaths")


def normpath(path: Union[str, Path]) -> str:
    """归一化路径为绝对路径字符串"""
    return os.path.normpath(os.path.abspath(str(path)))


def ensure_dir(path: Union[str, Path]) -> Path:
    """确保目录存在，不存在则创建（含父目录）"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


class GlobalPaths:
    """统一路径管理器

    参考 webmanager/webglobal/globalpath.py 设计：
    - 使用 ``@cached_property`` 惰性创建目录，首次访问时自动 mkdir
    - 所有路径基于 ``self.storage_root`` 派生，支持动态设置根路径
    - 提供通用工具方法
    """

    def __init__(self, root: Union[str, Path, None] = None):
        """
        Args:
            root: agentrunner 项目根目录，默认自动推断
        """
        self._root = Path(root) if root else self._detect_root()
        # ★ 动态 references 路径（工程级覆盖），None 表示使用默认值
        self._references: Union[Path, None] = None

    # ──────────────────────── 根路径 ────────────────────────

    @staticmethod
    def _detect_root() -> Path:
        """基于当前工作目录动态推断 agentrunner 项目根目录。

        从 CWD 向上逐级查找，找到包含 ``agentrunnercore/`` 子目录的路径作为根目录。
        若未找到则回退到 ``__file__`` 相对路径。
        """
        cwd = Path(os.getcwd()).resolve()
        current = cwd
        for _ in range(20):  # 最多向上查 20 级
            if (current / "filestorage").is_dir():
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent
        # 回退：基于 __file__ 推断
        return Path(__file__).parent.parent.parent

    @property
    def root(self) -> Path:
        """agentrunner 项目根目录"""
        return self._root

    def set_root(self, root: Union[str, Path]) -> None:
        """动态设置根路径（会清除所有 cached_property 缓存）"""
        self._root = Path(root)
        logger.info(self._root)
        # 清除所有 cached_property 缓存，使下次访问重新计算
        # cached_property 会把结果存在实例的 __dict__ 中
        keys_to_remove = [k for k in self.__dict__ if k in (
            "storage_root", "CHAT_HISTORY", "CHAT_SESSIONS", "CONFIG",
            "MEMORY", "MEMORY_SESSIONS", "MEMORY_BACKUP", "PLANS",
            "WORKSPACE", "UPLOADS", "USAGE", "LOGS", "APP_LOGS", "SCREENSHOTS",
            "DOCGEN"
        )]
        for k in keys_to_remove:
            self.__dict__.pop(k)

    @cached_property
    def storage_root(self) -> Path:
        """filestorage/agentrunner/ 存储根目录（首次访问自动创建）"""
        p = self._root / "filestorage" / "agentrunner"
        return ensure_dir(p)

    @property
    def SKILLS(self) -> Path:
        """内置系统技能目录 (agentrunnercore/skills/)"""
        return Path(__file__).parent.parent / "skills"

    @property
    def static_dir(self) -> Path:
        """agentrunnercore/static/ 静态资源目录"""
        return Path(__file__).parent.parent / "static"

    # ──────────────────────── 聊天历史 ────────────────────────

    @cached_property
    def CHAT_HISTORY(self) -> Path:
        return ensure_dir(self.storage_root / "chat_history")

    @cached_property
    def CHAT_SESSIONS(self) -> Path:
        return ensure_dir(self.storage_root / "chat_history" / "sessions")

    # ──────────────────────── 配置文件 ────────────────────────

    @cached_property
    def CONFIG(self) -> Path:
        return ensure_dir(self.storage_root / "config")

    # ──────────────────────── 记忆 ────────────────────────

    @cached_property
    def MEMORY(self) -> Path:
        return ensure_dir(self.storage_root / "memory")

    @cached_property
    def MEMORY_SESSIONS(self) -> Path:
        return ensure_dir(self.storage_root / "memory" / "sessions")

    @cached_property
    def MEMORY_BACKUP(self) -> Path:
        return ensure_dir(self.storage_root / "memory" / "backup")

    # ──────────────────────── 计划 ────────────────────────

    @cached_property
    def PLANS(self) -> Path:
        return ensure_dir(self.storage_root / "plans")

    # ──────────────────────── 工作空间 ────────────────────────

    @cached_property
    def WORKSPACE(self) -> Path:
        return ensure_dir(self.storage_root / "workspace")

    # ──────────────────────── 上传 ────────────────────────

    @cached_property
    def UPLOADS(self) -> Path:
        return ensure_dir(self.storage_root / "uploads")

    # ──────────────────────── Usage 追踪 ────────────────────────

    @cached_property
    def USAGE(self) -> Path:
        return ensure_dir(self.storage_root / "usage")

    # ──────────────────────── 日志 ────────────────────────

    @cached_property
    def LOGS(self) -> Path:
        return ensure_dir(self.storage_root / "logs")

    @cached_property
    def APP_LOGS(self) -> Path:
        """agentrunner/logs 应用运行日志目录（非 filestorage 子目录）"""
        return ensure_dir(self._root / "logs")

    # ──────────────────────── 截图 ────────────────────────

    @cached_property
    def SCREENSHOTS(self) -> Path:
        return ensure_dir(self.storage_root / "screenshots")

    # ──────────────────────── 智能文档 ────────────────────────

    @cached_property
    def DOCGEN(self) -> Path:
        """智能文档存储目录 (filestorage/agentrunner/docgen/)"""
        return ensure_dir(self.storage_root / "docgen")

    @property
    def REFERENCES(self) -> Path:
        """GJB 文档参考模板目录。

        优先返回工程级动态路径（通过 set_references() 设置），
        未设置时回退到默认 docgen/references/ 目录。
        """
        if self._references is not None:
            return self._references
        return Path(__file__).parent.parent / "docgen" / "references"

    def set_references(self, path: Union[str, Path]) -> Path:
        """设置工程级 references 目录路径（全局生效）。

        设置后，所有通过 globalPaths.REFERENCES 获取的路径
        都将指向该工程目录，而非默认模板目录。
        """
        p = ensure_dir(Path(path))
        self._references = p
        logger.info(f"[GlobalPaths] REFERENCES 已设置为: {p}")
        return p

    def reset_references(self) -> None:
        """重置 references 为默认模板目录"""
        self._references = None

    @property
    def DOCGEN_RULES(self) -> Path:
        """GJB 文档规则目录 (docgen/rules/)"""
        return Path(__file__).parent.parent / "docgen" / "rules"

    @property
    def DOCGEN_SCRIPTS(self) -> Path:
        """GJB 文档生成脚本目录 (docgen/scripts/)"""
        return Path(__file__).parent.parent / "docgen" / "scripts"

    # ──────────────────────── 配置文件快捷方式 ────────────────────────

    @property
    def providers_file(self) -> Path:
        return self.CONFIG / "providers.json"

    @property
    def agents_file(self) -> Path:
        return self.CONFIG / "agents.json"

    @property
    def preferences_file(self) -> Path:
        return self.CONFIG / "preferences.json"

    @property
    def provider_sort_order_file(self) -> Path:
        return self.CONFIG / "provider_sort_order.json"

    @property
    def model_sort_orders_file(self) -> Path:
        return self.CONFIG / "model_sort_orders.json"

    # ──────────────────────── 工具方法 ────────────────────────

    def filepath(self, relative_path: Union[str, Path], create: bool = True) -> Path:
        """在 storage_root 下获取/创建子路径

        Args:
            relative_path: 相对于 storage_root 的路径
            create: 是否自动创建目录

        Returns:
            目标路径
        """
        p = self.storage_root / relative_path
        if create:
            ensure_dir(p.parent)
        return p

    def open_dir(self, filepath: Union[str, Path]) -> None:
        """在文件管理器中打开文件或目录"""
        path = Path(filepath)
        _dir = path.parent if path.is_file() else path

        if sys.platform == "win32":
            os.startfile(str(_dir))
        elif sys.platform == "darwin":
            os.system(f"open {_dir}")
        else:
            os.system(f"xdg-open {_dir}")

    def __repr__(self) -> str:
        return f"GlobalPaths(root={self._root!s})"


# ── 模块级单例 ──
globalPaths = GlobalPaths()
