#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于pypandoc的PDF导出器 - 一层继承版本
继承WordExporter，通过zip文件中间层实现PDF格式转换
输出文件直接保存在解压目录中
"""

import os
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from loguru import logger

try:
    import pypandoc
    PYPANDOC_AVAILABLE = True
except ImportError:
    logger.warning("pypandoc未安装，PDF导出功能将不可用")
    PYPANDOC_AVAILABLE = False

from .word_exporter import WordExporter


class PdfExporter(WordExporter):
    """基于pypandoc的PDF导出器，通过zip文件中间层实现转换"""
    
    def __init__(self, data_dir: str):
        super().__init__(data_dir)
        self.styles = None
    
    def md_to_target(self, markdown_file: str, output_file: str) -> bool:
        """
        将markdown文件转换为PDF格式
        
        Args:
            markdown_file: markdown文件路径
            output_file: 输出文件路径
            
        Returns:
            bool: 转换成功返回True，失败返回False
        """
        try:
            # 使用convert_text方法转换（避免文件路径问题）
            pypandoc.convert_text(
                self._read_markdown_content(markdown_file),
                'pdf',
                format='markdown',
                outputfile=output_file,
                extra_args=[
                    '--toc',  # 添加目录
                    '--toc-depth=3',  # 目录深度
                    '--number-sections',  # 章节编号
                    '--pdf-engine=weasyprint',  # 使用weasyprint引擎
                    '-V', 'geometry:margin=1in',  # 页面边距
                    '--css=/dev/null',  # 禁用默认CSS，避免路径问题
                ]
            )
            return True
            
        except Exception as e:
            logger.error(f"PDF转换失败: {e}")
            return False
    
    def _get_format_name(self) -> str:
        """
        获取格式名称
        
        Returns:
            str: 格式名称
        """
        return "PDF"
    
    def _get_file_extension(self) -> str:
        """
        获取文件扩展名
        
        Returns:
            str: 文件扩展名
        """
        return "pdf"