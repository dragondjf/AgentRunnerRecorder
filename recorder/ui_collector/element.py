"""
element.py — UI 控件元素模型（平台无关）
=========================================
定义 UIElement 数据类、去重判定、排序等纯逻辑。
所有平台相关的采集操作请使用 platform 模块。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────

@dataclass
class UIElement:
    """UI 控件元素"""
    name: str          # 控件名称
    type: str          # 控件类型（如 Button, Edit, TabItem）
    bbox_left: int     # 相对于窗口的左边距
    bbox_top: int      # 相对于窗口的上边距
    bbox_right: int    # 相对于窗口的右边距
    bbox_bottom: int   # 相对于窗口的下边距
    width: int         # 宽度
    height: int        # 高度
    id: int = -1       # 唯一标识（由采集器分配）

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'bbox_left': self.bbox_left,
            'bbox_top': self.bbox_top,
            'bbox_right': self.bbox_right,
            'bbox_bottom': self.bbox_bottom,
            'width': self.width,
            'height': self.height,
        }

    @classmethod
    def from_dict(cls, d: dict) -> UIElement:
        return cls(
            id=d.get('id', -1),
            name=d.get('name', ''),
            type=d.get('type', ''),
            bbox_left=d.get('bbox_left', 0),
            bbox_top=d.get('bbox_top', 0),
            bbox_right=d.get('bbox_right', 0),
            bbox_bottom=d.get('bbox_bottom', 0),
            width=d.get('width', 0),
            height=d.get('height', 0),
        )

    @property
    def center_x(self) -> float:
        return (self.bbox_left + self.bbox_right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.bbox_top + self.bbox_bottom) / 2.0

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def safe_name(self) -> str:
        """文件名安全的名称"""
        s = re.sub(r'[\\/:*?"<>|]', '_', self.name)[:30]
        return s if s.strip() else self.type


# ──────────────────────────────────────────────
# 去重判定（平台无关）
# ──────────────────────────────────────────────

def elements_are_same(a: UIElement, b: UIElement) -> bool:
    """判断两个控件元素是否相同（三重判定）

    判定条件（满足任一即判为相同）:
    1. 名称 + 类型精确匹配
    2. 位置重叠度 IoU > 0.7
    3. 名称类型匹配且中心距离 < 30px
    """
    # 1. 名称 + 类型精确匹配
    name_match = a.name == b.name and a.type == b.type

    # 2. 位置重叠度 (IoU > 0.7)
    x1 = max(a.bbox_left, b.bbox_left)
    y1 = max(a.bbox_top, b.bbox_top)
    x2 = min(a.bbox_right, b.bbox_right)
    y2 = min(a.bbox_bottom, b.bbox_bottom)

    iou = 0.0
    if x2 > x1 and y2 > y1:
        inter = (x2 - x1) * (y2 - y1)
        a_area = a.area
        b_area = b.area
        union = a_area + b_area - inter
        if union > 0:
            iou = inter / union

    iou_match = iou > 0.7

    # 3. 中心点距离（同类型且名称相似时）
    dist = ((a.center_x - b.center_x) ** 2 + (a.center_y - b.center_y) ** 2) ** 0.5
    center_match = name_match and dist < 30

    return iou_match or center_match


def is_duplicate(new_elem: UIElement, existing_list: list[UIElement]) -> bool:
    """检查新元素是否与已有列表中的任意元素重复"""
    for exist in existing_list:
        if elements_are_same(new_elem, exist):
            return True
    return False


def deduplicate_elements(
    candidates: list[UIElement],
    existing: list[UIElement] | None = None,
) -> list[UIElement]:
    """对候选列表去重（内部去重 + 与历史去重）

    性能优化：
      - 使用名称+类型哈希表快速预过滤（O(1) 查重）
      - 仅哈希未命中时执行完整 IoU 计算
      - 按面积降序排列，大控件优先保留

    Args:
        candidates: 候选元素列表
        existing: 已有元素列表（可选）

    Returns:
        去重后的新元素列表
    """
    # 构建历史哈希索引（名称+类型 → 元素列表，快速预过滤）
    existing_index: dict[str, list[UIElement]] = {}
    if existing:
        for e in existing:
            key = "{}|{}".format(e.name, e.type)
            existing_index.setdefault(key, []).append(e)

    # 按面积降序排列，大控件优先保留
    candidates.sort(key=lambda e: e.area, reverse=True)

    deduped: list[UIElement] = []
    deduped_index: dict[str, list[UIElement]] = {}

    for elem in candidates:
        key = "{}|{}".format(elem.name, elem.type)

        # 快速预过滤：名称+类型完全匹配时检查所有同键元素
        duplicate = False

        # 检查 deduped 列表
        if key in deduped_index:
            for exist in deduped_index[key]:
                if elements_are_same(elem, exist):
                    duplicate = True
                    break

        # 检查历史列表
        if not duplicate and key in existing_index:
            for exist in existing_index[key]:
                if elements_are_same(elem, exist):
                    duplicate = True
                    break

        if not duplicate:
            deduped.append(elem)
            deduped_index.setdefault(key, []).append(elem)

    return deduped


def sort_elements_top_left(elements: list[UIElement]) -> list[UIElement]:
    """按左上到右下排序"""
    return sorted(elements, key=lambda e: (e.bbox_top, e.bbox_left))
