#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZIP导出器
将监控数据、截图等打包成ZIP文件
"""

import os
import json
import zipfile
from pathlib import Path
from datetime import datetime
from loguru import logger

from .base_exporter import BaseExporter


class ZipExporter(BaseExporter):
    """ZIP导出器"""
    
    def export(self) -> str:
        """
        导出ZIP文件，包含完整的data_dir目录和README文档
        
        Returns:
            str: 输出ZIP文件路径，失败返回空字符串
        """
        try:
            # 生成输出文件路径
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"export_zip_{timestamp}.zip"
            exports_dir = self.data_dir.parent / "data" / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            output_file = exports_dir / output_filename
            
            logger.info(f"开始导出ZIP文件: {output_file}")
            logger.info(f"数据源目录: {self.data_dir}")
            
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 导出完整的data_dir目录结构
                self._add_directory_to_zip(zipf, self.data_dir, "")
                
                # 添加导出信息文件
                export_info = self.get_export_info()
                export_info_json = json.dumps(export_info, ensure_ascii=False, indent=2)
                zipf.writestr("export_info.json", export_info_json)
                logger.debug("添加导出信息文件")
                
                # 添加README文件
                readme_content = self._generate_readme()
                zipf.writestr("README.md", readme_content)
                logger.debug("添加README文件")
            
            logger.info(f"ZIP文件导出成功: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"ZIP导出失败: {e}")
            return ""
    
    def _add_directory_to_zip(self, zipf: zipfile.ZipFile, source_dir: Path, base_arcname: str = ""):
        """
        递归地将目录及其所有内容添加到ZIP文件
        
        Args:
            zipf: ZIP文件对象
            source_dir: 源目录路径
            base_arcname: 在ZIP中的基础路径
        """
        try:
            source_path = Path(source_dir)
            if not source_path.exists():
                logger.warning(f"源目录不存在: {source_path}")
                return
            
            # 遍历目录中的所有文件和子目录
            for item in source_path.rglob("*"):
                # 计算相对于源目录的路径
                relative_path = item.relative_to(source_path)
                
                if item.is_file():
                    # 计算在ZIP中的完整路径
                    if base_arcname:
                        arcname = f"{base_arcname}/{relative_path}"
                    else:
                        arcname = str(relative_path)
                    
                    # 添加文件到ZIP
                    zipf.write(item, arcname)
                    logger.debug(f"添加文件到ZIP: {arcname}")
                    
                elif item.is_dir():
                    # 创建目录在ZIP中
                    if base_arcname:
                        dir_arcname = f"{base_arcname}/{relative_path}"
                    else:
                        dir_arcname = str(relative_path)
                    
                    # 添加目录标记（空目录）
                    zipf.writestr(f"{dir_arcname}/", "")
                    logger.debug(f"添加目录到ZIP: {dir_arcname}/")
                    
        except Exception as e:
            logger.error(f"添加目录到ZIP失败: {e}")
            raise
    
    def _generate_readme(self) -> str:
        """生成README文件内容"""
        monitoring_data = self.load_monitoring_data()
        summary_data = self.load_summary_data()
        screenshots = self.get_screenshots()
        
        readme_content = f"""# 监控系统导出包

## 导出信息
- 导出时间: {self.export_time.strftime('%Y-%m-%d %H:%M:%S')}
- 数据目录: {self.data_dir}
- 监控数据文件: {len(list(self.data_dir.glob('monitoring_data_*.json')))} 个
- 汇总数据文件: {len(list(self.data_dir.glob('summary_*.json')))} 个
- 截图文件: {len(screenshots)} 个

## 文件结构
```
导出包/
├── data/                   # 监控数据文件
│   ├── monitoring_data_*.json
│   └── summary_*.json
├── screenshots/           # 截图文件
│   └── *.png
├── export_info.json       # 导出信息
└── README.md             # 说明文件
```

## 监控概览
"""
        
        if summary_data:
            readme_content += f"""
### 操作统计
- 总操作次数: {summary_data.get('total_operations', 'N/A')}
- 键盘操作: {summary_data.get('keyboard_operations', 'N/A')}
- 鼠标操作: {summary_data.get('mouse_operations', 'N/A')}
- 录制时长: {summary_data.get('recording_duration', 'N/A')}
"""
        
        if monitoring_data:
            readme_content += f"""
### 最新操作
{self._format_latest_operations(monitoring_data)}
"""
        
        readme_content += f"""
## 使用说明
1. 监控数据文件包含详细的操作记录
2. 截图文件记录了关键操作的视觉证据
3. 可以使用任何JSON解析工具查看数据内容
4. 建议使用专业的数据分析工具进行进一步分析

---
导出工具: UIExporter ZIP Exporter v1.0
"""
        return readme_content
    
    def _format_latest_operations(self, monitoring_data: dict, max_operations: int = 10) -> str:
        """格式化最新操作记录"""
        try:
            operations = monitoring_data.get('operations', [])
            if not operations:
                return "暂无操作记录"
            
            # 获取最新的操作
            latest_operations = operations[-max_operations:]
            
            formatted = []
            for i, op in enumerate(latest_operations, 1):
                op_type = op.get('type', 'Unknown')
                timestamp = op.get('timestamp', 'N/A')
                details = op.get('details', {})
                
                detail_str = ", ".join([f"{k}: {v}" for k, v in details.items()])
                formatted.append(f"{i}. [{timestamp}] {op_type} - {detail_str}")
            
            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"格式化操作记录失败: {e}")
            return "操作记录格式化失败"