#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown导出器
生成Markdown格式的监控报告
"""

import os
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from loguru import logger

from .base_exporter import BaseExporter


class MarkdownExporter(BaseExporter):
    """Markdown导出器"""
    
    def export(self) -> str:
        """
        导出Markdown文件（实际上是ZIP文件）
        
        Returns:
            str: 输出ZIP文件路径，失败返回空字符串
        """
        try:
            logger.info(f"开始导出Markdown ZIP文件")
            
            # 生成Markdown内容
            markdown_content = self._generate_markdown()
            
            # 创建临时markdown文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_md_file = self.data_dir / f"records_{timestamp}.md"
            
            # 写入临时文件
            with open(temp_md_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            logger.info(f"临时Markdown文件生成成功: {temp_md_file}")
            
            # 生成新的records.json文件
            self._generate_new_records_json()
            
            # 压缩data_dir目录
            zip_path = self._create_zip_archive()
            
            # 删除临时markdown文件
            if temp_md_file.exists():
                temp_md_file.unlink()
            
            logger.info(f"Markdown ZIP文件导出成功: {zip_path}")
            return str(zip_path)
            
        except Exception as e:
            logger.error(f"Markdown导出失败: {e}")
            return ""
    
    def _generate_markdown(self) -> str:
        """生成完整的Markdown内容 - 重构版本"""
        try:
            # 查找records.json文件
            records_file = self.data_dir / "records.json"
            if not records_file.exists():
                logger.error(f"records.json文件不存在: {records_file}")
                return self._generate_fallback_markdown()
            
            # 读取records.json数据
            with open(records_file, 'r', encoding='utf-8') as f:
                records_data = json.load(f)
            
            slides = records_data.get('slides', [])
            if not slides:
                logger.warning("records.json中没有slides数据")
                return self._generate_fallback_markdown()
            
            logger.info(f"开始处理 {len(slides)} 个slides")
            
            markdown_lines = []
            
            # 添加文档头部
            markdown_lines.append("# 基于智能体驱动的下一代测试平台 AgentRunner")
            markdown_lines.append("")
            markdown_lines.append(f"+ **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            markdown_lines.append(f"+ **数据源**: {records_file}")
            markdown_lines.append(f"+ **操作总数**: {len(slides)}")
            markdown_lines.append("")
            
            # 处理每个slide
            for i, slide in enumerate(slides, 1):
                title = slide.get('title', f'操作 {i}')
                markdown_content = slide.get('markdown', '')
                
                # 格式化markdown内容
                formatted_content = self._format_markdown_content(markdown_content, slide)
                
                # 按照指定格式生成内容：#{title}\n{markdown}
                markdown_lines.append(f"# {i}. {title}")
                markdown_lines.append("")
                markdown_lines.append(formatted_content)
                markdown_lines.append("")
                
                logger.debug(f"处理slide {i}: {title}")
            
            # 添加文档尾部
            markdown_lines.append("---")
            markdown_lines.append("")
            markdown_lines.append("*报告由 AgentRunner Markdown Exporter 生成*")
            
            return '\n'.join(markdown_lines)
            
        except Exception as e:
            logger.error(f"生成Markdown内容时出错: {e}")
            return self._generate_fallback_markdown()
    
    def _format_markdown_content(self, markdown_content: str, slide: dict) -> str:
        """格式化markdown内容"""
        context = slide.get('context', '')

        if not markdown_content:
            markdown_content = "操作记录"

        # 替换图片路径：支持多种格式
        # 1. API路径格式: /api/v1/file?path=project/my_screenshots/xxx.png
        # 2. HTTP URL格式: http://IP:PORT/path/to/xxx.png
        def replace_image_path(match):
            # match.group(1) 是 alt 文本
            # match.group(2) 是 URL
            alt = match.group(1)
            url = match.group(2)

            # 判断是否是API路径格式
            if url.startswith('/api/v1/file?path='):
                # 提取路径参数中的完整路径
                path_param = url[len('/api/v1/file?path='):]
                # 提取文件名
                filename = os.path.basename(path_param)
            else:
                # 其他格式,直接提取文件名
                filename = os.path.basename(url)
            # 使用固定的my_screenshots目录路径,保留完整的markdown语法
            return f"![{alt}](./my_screenshots/{filename})"

        # 匹配图片语法: ![alt](url)
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        formatted_content = re.sub(image_pattern, replace_image_path, markdown_content)
        
        # 如果有context信息，添加到内容中
        if context:
            # 将context格式化为markdown列表格式
            context_lines = context.split('\n')
            formatted_context = '\n'.join([f"+ {line}" for line in context_lines if line.strip()])
            formatted_content += f"\n\n**操作详情**:\n{formatted_context}"
        
        remark = slide.get('remark', '')
        if remark:
            formatted_content += f"\n\n**页面描述**:\n{remark}"

        # 清理多余的空行
        formatted_content = re.sub(r'\n\s*\n\s*\n', '\n\n', formatted_content)
        
        return formatted_content.strip()
    
    def _generate_new_records_json(self):
        """生成新的records.json文件"""
        try:
            # 查找原始records.json文件
            records_file = self.data_dir / "records.json"
            if not records_file.exists():
                logger.warning(f"原始records.json文件不存在: {records_file}")
                return
            
            # 读取原始数据
            with open(records_file, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
            
            # 创建新的records.json内容
            new_records_data = {
                "slides": original_data.get('slides', []),
                "lastUpdated": datetime.now().isoformat(),
                "version": "2.0",
                "generatedBy": "AgentRunner Markdown Exporter",
                "exportTime": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 保存到data_dir根目录
            new_records_file = self.data_dir / "records.json"
            with open(new_records_file, 'w', encoding='utf-8') as f:
                json.dump(new_records_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"新的records.json已生成: {new_records_file}")
            
        except Exception as e:
            logger.error(f"生成新的records.json时出错: {e}")
    
    def _create_zip_archive(self) -> Path:
        """创建ZIP压缩文件"""
        import time as _time
        
        try:
            # 生成ZIP文件路径
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"agentrunner_export_{timestamp}.zip"
            exports_dir = self.data_dir.parent / "data" / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            zip_path = exports_dir / zip_filename
            
            # 统计待压缩的文件
            all_files = [f for f in self.data_dir.rglob('*') if f.is_file()]
            total_files = len(all_files)
            total_size_bytes = sum(f.stat().st_size for f in all_files)
            total_size_mb = total_size_bytes / (1024 * 1024)
            
            logger.info(f"[MarkdownExporter] 开始ZIP压缩: data_dir={self.data_dir}, "
                       f"文件数={total_files}, 总大小={total_size_mb:.2f}MB")
            
            _t0 = _time.time()
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 添加data_dir中的所有文件
                for idx, file_path in enumerate(all_files):
                    # 计算相对路径
                    arcname = file_path.relative_to(self.data_dir)
                    zipf.write(file_path, arcname)
                    
                    # 每100个文件或最后一个打一次日志
                    if (idx + 1) % max(1, total_files // 10 + 1) == 0 or idx == total_files - 1:
                        elapsed = _time.time() - _t0
                        progress_pct = (idx + 1) / total_files * 100
                        logger.info(f"[MarkdownExporter] ZIP进度: {idx+1}/{total_files} ({progress_pct:.0f}%), 耗时={elapsed:.2f}s")
            
            _elapsed_total = _time.time() - _t0
            zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
            
            logger.info(f"[MarkdownExporter] ZIP压缩完成: {zip_path}, "
                       f"耗时={_elapsed_total:.2f}s, 压缩后大小={zip_size_mb:.2f}MB")
            return zip_path
            
        except Exception as e:
            logger.error(f"[MarkdownExporter] 创建ZIP文件时出错: {e}", exc_info=True)
            raise
    
    def _generate_fallback_markdown(self) -> str:
        """生成备用markdown内容"""
        return f"""# 基于智能体驱动的下一代测试平台 AgentRunner

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据目录**: `{self.data_dir}`

暂无有效数据可导出。

---
*报告由 AgentRunner Markdown Exporter 生成*
"""