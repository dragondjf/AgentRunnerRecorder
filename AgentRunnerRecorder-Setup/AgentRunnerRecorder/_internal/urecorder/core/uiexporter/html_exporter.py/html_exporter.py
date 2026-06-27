#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于pypandoc的HTML导出器 - 一层重构版本
继承WordExporter，通过pypandoc实现HTML格式转换
支持--embed-resources --standalone参数生成完整的HTML文件
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
    logger.warning("pypandoc未安装，HTML导出功能将不可用")
    PYPANDOC_AVAILABLE = False

from .word_exporter import WordExporter


class HtmlExporter(WordExporter):
    """基于pypandoc的HTML导出器，继承WordExporter的实现"""
    
    def md_to_target(self, markdown_file: str, output_file: str) -> bool:
        """
        将markdown文件转换为HTML格式
        
        Args:
            markdown_file: markdown文件路径
            output_file: 输出文件路径
            
        Returns:
            bool: 转换成功返回True，失败返回False
        """
        try:
            # 使用pypandoc.convert_text方法转换（避免文件路径问题）
            # 注意：某些版本的pypandoc可能不支持--embed-resources参数
            extra_args = ['--standalone']  # 使用基本的standalone参数
            
            # 尝试添加embed-resources，如果不支持会抛出异常
            try:
                pypandoc.convert_text(
                    self._read_markdown_content(markdown_file),
                    'html',
                    format='markdown',
                    outputfile=output_file,
                    extra_args=extra_args + ['--embed-resources']
                )
            except Exception:
                # 如果--embed-resources不支持，回退到基本参数
                logger.info("当前pypandoc版本不支持--embed-resources，使用基本参数")
                pypandoc.convert_text(
                    self._read_markdown_content(markdown_file),
                    'html',
                    format='markdown',
                    outputfile=output_file,
                    extra_args=extra_args
                )
            
            return True
            
        except Exception as e:
            logger.error(f"HTML转换失败: {e}")
            return False
    
    def _get_format_name(self) -> str:
        """
        获取格式名称
        
        Returns:
            str: 格式名称
        """
        return "HTML"
    
    def _get_file_extension(self) -> str:
        """
        获取文件扩展名
        
        Returns:
            str: 文件扩展名
        """
        return "html"