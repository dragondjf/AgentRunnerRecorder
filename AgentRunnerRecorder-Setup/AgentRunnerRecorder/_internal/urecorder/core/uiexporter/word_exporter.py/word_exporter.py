#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于pypandoc的Word导出器 - 一层重构版本
继承MarkdownExporter，通过zip文件中间层实现Word格式转换
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
    logger.warning("pypandoc未安装，Word导出功能将不可用")
    PYPANDOC_AVAILABLE = False

from .markdown_exporter import MarkdownExporter


class WordExporter(MarkdownExporter):
    """基于pypandoc的Word导出器，通过zip文件中间层实现转换"""
    
    def export(self) -> str:
        """
        导出Word文件（通过Markdown zip文件转换）
        
        Returns:
            str: 输出文件路径，导出失败返回空字符串
        """
        import time as _time
        _t_total = _time.time()
        
        if not PYPANDOC_AVAILABLE:
            logger.error("[WordExporter] pypandoc库未安装，无法导出Word文件")
            return ""
        
        zip_file_path = ""
        output_dir = ""
        original_cwd = ""
        
        try:
            logger.info(f"[WordExporter] ===== 开始导出Word文件 =====")
            
            # 步骤1: 调用MarkdownExporter生成临时zip文件
            _t1 = _time.time()
            logger.info(f"[WordExporter] 步骤1: 生成Markdown zip文件 ...")
            zip_file_path = super().export()
            _step1 = _time.time() - _t1
            
            if not zip_file_path:
                logger.error(f"[WordExporter] 步骤1失败: Markdown zip文件生成失败, 耗时={_step1:.2f}s")
                return ""
            
            zip_size = Path(zip_file_path).stat().st_size / (1024*1024) if Path(zip_file_path).exists() else 0
            logger.info(f"[WordExporter] 步骤1完成: {zip_file_path}, 耗时={_step1:.2f}s, 大小={zip_size:.2f}MB")
            
            # 步骤2: 创建output_dir并解压zip文件
            _t2 = _time.time()
            logger.info(f"[WordExporter] 步骤2: 创建output_dir并解压zip文件 ...")
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = Path(self.data_dir).parent / 'data'/ 'exports' / f'word_export_{timestamp}'
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(os.path.abspath(output_dir))
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)
            _step2 = _time.time() - _t2
            logger.info(f"[WordExporter] 步骤2完成: 解压到 {output_dir}, 耗时={_step2:.2f}s")
            
            # 步骤3: 记录当前目录并切换到output_dir
            _t3 = _time.time()
            logger.info(f"[WordExporter] 步骤3: 切换到解压目录 ...")
            original_cwd = os.getcwd()
            os.chdir(output_dir)
            logger.info(f"[WordExporter] 步骤3完成: cwd={os.getcwd()}, 耗时={_time.time()-_t3:.2f}s")
            
            # 步骤4: 在解压目录中查找markdown文件
            _t4 = _time.time()
            logger.info(f"[WordExporter] 步骤4: 查找markdown文件 ...")
            markdown_file = self._find_markdown_file(os.getcwd())
            if not markdown_file:
                logger.error(f"[WordExporter] 步骤4失败: 在解压目录中未找到markdown文件, 耗时={_time.time()-_t4:.2f}s")
                return ""
            
            # 获取相对于output_dir的相对路径
            markdown_file_rel = os.path.relpath(markdown_file, output_dir)
            md_size = Path(markdown_file).stat().st_size / 1024 if Path(markdown_file).exists() else 0
            logger.info(f"[WordExporter] 步骤4完成: md={markdown_file_rel}, 大小={md_size:.1f}KB, 耗时={_time.time()-_t4:.2f}s")
            
            # 步骤5: 生成输出文件路径（相对于当前目录，即output_dir）
            output_file = f'export_word_{timestamp}.{self._get_file_extension()}'
            
            # 步骤6: 调用md_to_target进行转换
            logger.info(f"[WordExporter] 步骤6: 调用md_to_target转换Word文件 ...")
            
            # 调用md_to_target方法进行转换
            _t6 = _time.time()
            if self.md_to_target(markdown_file, output_file):
                _step6 = _time.time() - _t6
                _total_elapsed = _time.time() - _t_total
                
                # 返回完整的文件路径
                full_output_path = output_dir / output_file
                out_size = full_output_path.stat().st_size / (1024*1024) if full_output_path.exists() else 0
                
                logger.info(f"[WordExporter] ===== Word导出成功! =====")
                logger.info(f"[WordExporter] 输出文件: {full_output_path}, 大小={out_size:.2f}MB")
                logger.info(f"[WordExporter] 各步骤耗时: step1(zip)={_step1:.2f}s, step2(解压)={_step2:.2f}s, "
                           f"step6(pypandoc)={_step6:.2f}s, 总计={_total_elapsed:.2f}s")
                
                return str(full_output_path)
            else:
                logger.error(f"[WordExporter] 步骤6失败: Word导出失败")
                return ""
        finally:
            # 清理临时文件
            self._cleanup_temp_files(zip_file_path, str(output_dir) if output_dir else "")
            # 步骤7: 切换回原始目录
            if original_cwd:
                os.chdir(original_cwd)
                logger.debug(f"[WordExporter] 切换回原始目录: {os.getcwd()}")
    
    def _find_markdown_file(self, extract_dir: str) -> str:
        """
        在解压目录中查找markdown文件
        
        Args:
            extract_dir: 解压目录路径
            
        Returns:
            str: markdown文件路径，未找到返回空字符串
        """
        try:
            extract_path = Path(extract_dir)
            
            # 查找可能的markdown文件
            md_files = list(extract_path.rglob("*.md"))
            
            if not md_files:
                logger.warning("在解压目录中未找到.md文件")
                return ""
            
            # 优先选择records_*.md文件
            records_md_files = [f for f in md_files if f.name.startswith("records_")]
            if records_md_files:
                return str(records_md_files[0])
            
            # 否则选择第一个找到的md文件
            return str(md_files[0])
            
        except Exception as e:
            logger.error(f"查找markdown文件失败: {e}")
            return ""
    
    def _read_markdown_content(self, markdown_file: str) -> str:
        """
        读取markdown文件内容
        
        Args:
            markdown_file: markdown文件路径
            
        Returns:
            str: markdown文件内容
        """
        try:
            with open(markdown_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取markdown文件失败: {e}")
            return ""
    
    def _cleanup_temp_files(self, zip_file_path: str, output_dir: str):
        """
        清理临时文件
        
        Args:
            zip_file_path: zip文件路径
            output_dir: 输出目录路径
        """
        try:
            # 删除临时zip文件
            if zip_file_path and os.path.exists(zip_file_path):
                os.remove(zip_file_path)
                logger.debug(f"删除临时zip文件: {zip_file_path}")
            
            # 注意：output_dir是正式的输出目录，不应该删除
            logger.debug(f"保留输出目录: {output_dir}")
                
        except Exception as e:
            logger.warning(f"清理临时文件时出错: {e}")
    
    def md_to_target(self, markdown_file: str, output_file: str) -> bool:
        """
        将markdown文件转换为Word格式
        
        Args:
            markdown_file: markdown文件路径
            output_file: 输出文件路径
            
        Returns:
            bool: 转换成功返回True，失败返回False
        """
        import time as _time
        
        try:
            template_docx = Path(__file__).parent / 'templates' / 'template.docx'

            # 读取markdown内容并记录大小
            md_content = self._read_markdown_content(markdown_file)
            logger.info(f"[WordExporter] pypandoc转换开始: md={markdown_file}, docx={output_file}, "
                       f"md_size={len(md_content)} chars, template={template_docx} (exists={template_docx.exists()})")

            _t0 = _time.time()
            extra_args = []
            if template_docx.exists():
                extra_args.append(f'--reference-doc={template_docx}')
            else:
                logger.warning(f"[WordExporter] 模板文件不存在，使用pypandoc默认样式: {template_docx}")

            pypandoc.convert_text(
                md_content,
                'docx',
                format='markdown',
                outputfile=output_file,
                extra_args=extra_args,
            )
            _elapsed = _time.time() - _t0
            
            # 检查输出文件是否生成及大小
            out_path = Path(output_file)
            if out_path.exists():
                out_size = out_path.stat().st_size / 1024
                logger.info(f"[WordExporter] pypandoc转换成功! 耗时={_elapsed:.2f}s, 输出大小={out_size:.1f}KB")
            else:
                logger.error(f"[WordExporter] pypandoc返回无异常但输出文件不存在: {output_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"[WordExporter] Word转换失败: {e}", exc_info=True)
            return False
    
    def _get_format_name(self) -> str:
        """
        获取格式名称
        
        Returns:
            str: 格式名称
        """
        return "Word"
    
    def _get_file_extension(self) -> str:
        """
        获取文件扩展名
        
        Returns:
            str: 文件扩展名
        """
        return "docx"