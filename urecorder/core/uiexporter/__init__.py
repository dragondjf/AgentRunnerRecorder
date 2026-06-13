#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UIExporter模块
统一的用户界面导出工具
"""

from loguru import logger

from .base_exporter import BaseExporter, validate_export_type, get_exporter_class
from .zip_exporter import ZipExporter
from .word_exporter import WordExporter
from .pdf_exporter import PdfExporter
from .html_exporter import HtmlExporter
from .markdown_exporter import MarkdownExporter
from .test_docs_exporter import TestDocsExporter
from .help_docs_exporter import HelpDocsExporter
from .gui_runner_exporter import GuiRunnerExporter

__version__ = "1.0.0"
__author__ = "UIExporter Team"

# 导出器映射
EXPORTERS = {
    'zip': ZipExporter,
    'word': WordExporter,
    'pdf': PdfExporter,
    'html': HtmlExporter,
    'markdown': MarkdownExporter,
    'test-docs': TestDocsExporter,
    'help-docs': HelpDocsExporter,
    'gui-runner': GuiRunnerExporter
}

# 支持的导出格式
SUPPORTED_FORMATS = list(EXPORTERS.keys())

def get_exporter(export_type: str, data_dir: str):
    """
    获取导出器实例
    
    Args:
        export_type: 导出类型
        data_dir: 数据目录
        
    Returns:
        BaseExporter: 导出器实例
        
    Raises:
        ValueError: 不支持的导出类型
    """
    if export_type not in EXPORTERS:
        raise ValueError(f"不支持的导出类型: {export_type}. 支持的类型: {SUPPORTED_FORMATS}")
    
    exporter_class = EXPORTERS[export_type]
    return exporter_class(data_dir)

def export_data(export_type: str, data_dir: str) -> tuple[bool, str]:
    """
    导出数据
    
    Args:
        export_type: 导出类型
        data_dir: 数据目录
        
    Returns:
        tuple[bool, str]: (导出是否成功, 输出文件路径)
    """
    import time as _time
    _t0 = _time.time()
    
    try:
        logger.info(f"[uiexporter] 开始导出: type={export_type}, data_dir={data_dir}")
        
        exporter = get_exporter(export_type, str(data_dir))
        logger.info(f"[uiexporter] 导出器实例化完成: {type(exporter).__name__}")
        
        _t1 = _time.time()
        output_path = exporter.export()
        _elapsed_export = _time.time() - _t1
        _total_elapsed = _time.time() - _t0
        
        logger.info(f"[uiexporter] 导出完成: output_path={output_path}, exporter耗时={_elapsed_export:.2f}s, 总耗时={_total_elapsed:.2f}s")
        return True, str(output_path)
    except Exception as e:
        logger.error(f"[uiexporter] 导出失败: {e}", exc_info=True)
        return False, ""

def list_supported_formats() -> list:
    """
    获取支持的导出格式列表
    
    Returns:
        list: 支持的导出格式列表
    """
    return SUPPORTED_FORMATS.copy()

def get_format_info(format_type: str) -> dict:
    """
    获取导出格式信息
    
    Args:
        format_type: 导出格式类型
        
    Returns:
        dict: 格式信息
    """
    format_info = {
        'zip': {
            'name': 'ZIP压缩包',
            'description': '包含所有监控数据和截图的压缩包',
            'file_extension': '.zip',
            'use_case': '数据备份、完整归档'
        },
        'word': {
            'name': 'Word文档',
            'description': '格式化的监控报告文档',
            'file_extension': '.docx',
            'use_case': '正式报告、文档编辑'
        },
        'pdf': {
            'name': 'PDF文档',
            'description': '跨平台兼容的监控报告',
            'file_extension': '.pdf',
            'use_case': '打印输出、正式文档'
        },
        'markdown': {
            'name': 'Markdown文档',
            'description': '轻量级标记语言的监控报告',
            'file_extension': '.md',
            'use_case': '技术文档、开发者使用'
        },
        'html': {
            'name': 'HTML文档',
            'description': '独立的HTML格式监控报告，支持嵌入资源',
            'file_extension': '.html',
            'use_case': '网页展示、在线分享'
        },
        'test-docs': {
            'name': '测试用例文档',
            'description': '基于监控数据生成的测试用例',
            'file_extension': '.md',
            'use_case': 'QA测试、用例管理'
        },
        'help-docs': {
            'name': '帮助手册',
            'description': '详细的用户使用指南',
            'file_extension': '.md',
            'use_case': '用户培训、帮助文档'
        },
        'gui-runner': {
            'name': 'GUIRunner脚本',
            'description': '可执行的GUI自动化测试脚本',
            'file_extension': '.py',
            'use_case': '自动化测试、脚本执行'
        }
    }
    
    return format_info.get(format_type, {})