#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础导出器类
为所有导出功能提供统一的基类
"""

import os
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from loguru import logger


class BaseExporter(ABC):
    """基础导出器类"""
    
    def __init__(self, data_dir: str):
        """
        初始化导出器
        
        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = Path(data_dir)
        self.export_time = datetime.now()
        
    def load_monitoring_data(self) -> dict:
        """加载监控数据"""
        try:
            monitoring_files = list(self.data_dir.glob("monitoring_data_*.json"))
            if not monitoring_files:
                logger.warning(f"在目录 {self.data_dir} 中未找到监控数据文件")
                return {}
            
            # 读取最新的监控数据文件
            latest_file = max(monitoring_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"加载监控数据文件: {latest_file}")
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
        except Exception as e:
            logger.error(f"加载监控数据失败: {e}")
            return {}
    
    def load_summary_data(self) -> dict:
        """加载汇总数据"""
        try:
            summary_files = list(self.data_dir.glob("summary_*.json"))
            if not summary_files:
                logger.warning(f"在目录 {self.data_dir} 中未找到汇总数据文件")
                return {}
            
            # 读取最新的汇总数据文件
            latest_file = max(summary_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"加载汇总数据文件: {latest_file}")
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
        except Exception as e:
            logger.error(f"加载汇总数据失败: {e}")
            return {}
    
    def get_screenshots(self) -> list:
        """获取截图文件列表"""
        try:
            screenshots_dir = self.data_dir / "my_screenshots"
            if not screenshots_dir.exists():
                logger.warning(f"截图目录不存在: {screenshots_dir}")
                return []
            
            screenshot_files = list(screenshots_dir.glob("*.png"))
            logger.info(f"找到 {len(screenshot_files)} 个截图文件")
            
            return [f.name for f in screenshot_files]
        except Exception as e:
            logger.error(f"获取截图文件列表失败: {e}")
            return []
    
    @abstractmethod
    def export(self) -> str:
        """
        执行导出操作
        
        Returns:
            str: 输出文件路径，导出失败返回空字符串
        """
        pass
    
    def get_export_info(self) -> dict:
        """获取导出信息"""
        return {
            "exporter_type": self.__class__.__name__,
            "data_dir": str(self.data_dir),
            "export_time": self.export_time.isoformat(),
            "monitoring_data_files": len(list(self.data_dir.glob("monitoring_data_*.json"))),
            "summary_data_files": len(list(self.data_dir.glob("summary_*.json"))),
            "screenshot_files": len(self.get_screenshots())
        }


def validate_export_type(export_type: str) -> bool:
    """验证导出类型是否支持"""
    supported_types = [
        'zip', 'word', 'pdf', 'markdown', 'html',
        'test-docs', 'help-docs', 'gui-runner'
    ]
    return export_type in supported_types


def get_exporter_class(export_type: str):
    """获取导出器类"""
    exporter_map = {
        'zip': 'ZipExporter',
        'word': 'WordExporter', 
        'pdf': 'PdfExporter',
        'markdown': 'MarkdownExporter',
        'test-docs': 'TestDocsExporter',
        'help-docs': 'HelpDocsExporter',
        'gui-runner': 'GuiRunnerExporter'
    }
    return exporter_map.get(export_type)