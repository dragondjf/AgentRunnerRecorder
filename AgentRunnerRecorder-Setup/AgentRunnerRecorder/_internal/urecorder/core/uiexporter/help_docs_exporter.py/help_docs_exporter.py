#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帮助手册导出器
生成用户帮助手册
"""

import os
from datetime import datetime
from pathlib import Path
from loguru import logger

from .base_exporter import BaseExporter


class HelpDocsExporter(BaseExporter):
    """帮助手册导出器"""
    
    def export(self) -> str:
        """
        导出帮助手册
        
        Returns:
            str: 输出文件路径，导出失败返回空字符串
        """
        try:
            # 生成输出文件路径
            timestamp = self.export_time.strftime('%Y%m%d_%H%M%S')
            output_dir = self.data_dir.parent / 'data' / 'exports'
            output_file = output_dir / f'export_help-docs_{timestamp}.md'
            
            # 创建输出目录
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"开始导出帮助手册: {output_file}")
            
            # 生成帮助手册内容
            help_content = self._generate_help_docs()
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(help_content)
            
            logger.info(f"帮助手册导出成功: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"帮助手册导出失败: {e}")
            return ""
    
    def _generate_help_docs(self) -> str:
        """生成帮助手册内容"""
        docs = []
        
        # 文档标题和基本信息
        docs.append("# 系统监控器使用帮助手册")
        docs.append("")
        docs.append(f"**版本**: v1.0")
        docs.append(f"**更新时间**: {self.export_time.strftime('%Y-%m-%d')}")
        docs.append("")
        
        # 目录
        docs.append("## 目录")
        docs.append("")
        docs.append("1. [系统简介](#系统简介)")
        docs.append("2. [快速开始](#快速开始)")
        docs.append("3. [功能介绍](#功能介绍)")
        docs.append("4. [操作指南](#操作指南)")
        docs.append("5. [数据导出](#数据导出)")
        docs.append("6. [常见问题](#常见问题)")
        docs.append("7. [技术支持](#技术支持)")
        docs.append("")
        
        # 系统简介
        docs.append("## 系统简介")
        docs.append("")
        docs.append("系统监控器是一个强大的用户行为监控和分析工具，能够：")
        docs.append("")
        docs.append("- 实时记录键盘和鼠标操作")
        docs.append("- 自动截取操作截图")
        docs.append("- 生成详细的操作日志")
        docs.append("- 提供多种格式的数据导出")
        docs.append("- 支持数据分析和报告生成")
        docs.append("")
        docs.append("### 主要特性")
        docs.append("")
        docs.append("- **实时监控**: 无感知的操作记录")
        docs.append("- **可视化界面**: 直观的Web界面")
        docs.append("- **多格式导出**: 支持ZIP、Word、PDF、Markdown等")
        docs.append("- **数据分析**: 自动生成统计报告")
        docs.append("- **跨平台支持**: Windows、macOS、Linux")
        docs.append("")
        
        # 快速开始
        docs.append("## 快速开始")
        docs.append("")
        docs.append("### 系统要求")
        docs.append("")
        docs.append("- 操作系统: Windows 10+, macOS 10.14+, Ubuntu 18.04+")
        docs.append("- 内存: 至少4GB RAM")
        docs.append("- 磁盘空间: 至少100MB可用空间")
        docs.append("- 浏览器: Chrome 80+, Firefox 75+, Safari 13+")
        docs.append("")
        docs.append("### 安装步骤")
        docs.append("")
        docs.append("1. 下载系统监控器安装包")
        docs.append("2. 解压到指定目录")
        docs.append("3. 运行启动脚本")
        docs.append("4. 在浏览器中访问 `http://localhost:5000`")
        docs.append("")
        docs.append("### 第一次使用")
        docs.append("")
        docs.append("1. 打开浏览器，访问系统界面")
        docs.append("2. 点击工具栏中的「启动录制」按钮")
        docs.append("3. 开始正常使用计算机")
        docs.append("4. 点击「停止录制」结束监控")
        docs.append("5. 使用导出功能保存数据")
        docs.append("")
        
        # 功能介绍
        docs.append("## 功能介绍")
        docs.append("")
        docs.append("### 核心功能")
        docs.append("")
        docs.append("#### 1. 操作录制")
        docs.append("- **键盘监控**: 记录所有键盘输入")
        docs.append("- **鼠标监控**: 记录点击、移动、滚轮操作")
        docs.append("- **截图功能**: 自动截取关键操作画面")
        docs.append("- **时间戳**: 精确记录每个操作的时间")
        docs.append("")
        docs.append("#### 2. 数据管理")
        docs.append("- **实时显示**: 界面实时显示当前操作")
        docs.append("- **历史记录**: 查看历史监控数据")
        docs.append("- **数据筛选**: 按时间、操作类型筛选")
        docs.append("- **数据搜索**: 快速查找特定操作")
        docs.append("")
        docs.append("#### 3. 主题切换")
        docs.append("- **浅色主题**: 适合白天使用")
        docs.append("- **深色主题**: 适合夜间使用")
        docs.append("- **蓝色主题**: 护眼模式")
        docs.append("")
        
        # 操作指南
        docs.append("## 操作指南")
        docs.append("")
        docs.append("### 基本操作")
        docs.append("")
        docs.append("#### 启动监控")
        docs.append("1. 点击工具栏中的「🎥 启动录制」按钮")
        docs.append("2. 系统开始记录您的操作")
        docs.append("3. 界面显示当前录制状态")
        docs.append("")
        docs.append("#### 停止监控")
        docs.append("1. 再次点击「🎥 启动录制」按钮")
        docs.append("2. 系统停止记录操作")
        docs.append("3. 数据自动保存到本地")
        docs.append("")
        docs.append("#### 查看数据")
        docs.append("1. 在左侧面板中选择「数据管理」")
        docs.append("2. 浏览历史监控记录")
        docs.append("3. 点击记录查看详细信息")
        docs.append("4. 查看对应的截图")
        docs.append("")
        docs.append("### 高级功能")
        docs.append("")
        docs.append("#### 数据筛选")
        docs.append("- **时间范围**: 选择特定时间段")
        docs.append("- **操作类型**: 筛选键盘或鼠标操作")
        docs.append("- **关键词搜索**: 搜索特定内容")
        docs.append("")
        docs.append("#### 实时预览")
        docs.append("- **当前操作**: 显示正在进行的操作")
        docs.append("- **操作统计**: 实时更新的统计数据")
        docs.append("- **系统状态**: 监控服务运行状态")
        docs.append("")
        
        # 数据导出
        docs.append("## 数据导出")
        docs.append("")
        docs.append("系统支持多种格式的数据导出，满足不同需求。")
        docs.append("")
        docs.append("### 支持的格式")
        docs.append("")
        docs.append("#### 1. JSON格式")
        docs.append("- **用途**: 程序开发、数据处理")
        docs.append("- **特点**: 结构化数据，易于解析")
        docs.append("- **适用**: 开发者、数据分析师")
        docs.append("")
        docs.append("#### 2. ZIP压缩包")
        docs.append("- **用途**: 完整数据备份")
        docs.append("- **特点**: 包含所有数据和截图")
        docs.append("- **适用**: 数据归档、传输")
        docs.append("")
        docs.append("#### 3. Word文档")
        docs.append("- **用途**: 正式报告、文档")
        docs.append("- **特点**: 格式美观，易于编辑")
        docs.append("- **适用**: 管理层汇报、文档存档")
        docs.append("")
        docs.append("#### 4. PDF文档")
        docs.append("- **用途**: 打印、分享")
        docs.append("- **特点**: 跨平台兼容，格式固定")
        docs.append("- **适用**: 正式文档、打印输出")
        docs.append("")
        docs.append("#### 5. Markdown文档")
        docs.append("- **用途**: 技术文档、README")
        docs.append("- **特点**: 轻量级标记语言")
        docs.append("- **适用**: 开发者、技术团队")
        docs.append("")
        docs.append("#### 6. 测试用例文档")
        docs.append("- **用途**: QA测试、用例管理")
        docs.append("- **特点**: 结构化的测试用例")
        docs.append("- **适用**: 测试团队、质量保证")
        docs.append("")
        docs.append("#### 7. 帮助手册")
        docs.append("- **用途**: 用户指南、培训材料")
        docs.append("- **特点**: 详细的操作说明")
        docs.append("- **适用**: 新用户、培训场景")
        docs.append("")
        docs.append("#### 8. GUIRunner脚本")
        docs.append("- **用途**: 自动化测试、脚本执行")
        docs.append("- **特点**: 可执行的测试脚本")
        docs.append("- **适用**: 自动化测试、回归测试")
        docs.append("")
        docs.append("### 导出步骤")
        docs.append("")
        docs.append("1. 点击工具栏中的「导出」按钮")
        docs.append("2. 选择所需的导出格式")
        docs.append("3. 确认导出设置")
        docs.append("4. 等待导出完成")
        docs.append("5. 下载生成的文档")
        docs.append("")
        
        # 常见问题
        docs.append("## 常见问题")
        docs.append("")
        docs.append("### 安装和启动")
        docs.append("")
        docs.append("**Q: 系统无法启动怎么办？**")
        docs.append("A: 请检查：")
        docs.append("- 是否安装了Python 3.7+")
        docs.append("- 端口5000是否被占用")
        docs.append("- 防火墙是否阻止了程序")
        docs.append("")
        docs.append("**Q: 浏览器无法访问界面？**")
        docs.append("A: 请尝试：")
        docs.append("- 确认服务是否正常运行")
        docs.append("- 检查浏览器地址是否正确")
        docs.append("- 尝试使用其他浏览器")
        docs.append("")
        docs.append("### 功能使用")
        docs.append("")
        docs.append("**Q: 录制功能不工作？**")
        docs.append("A: 请检查：")
        docs.append("- 是否有管理员权限")
        docs.append("- 杀毒软件是否阻止")
        docs.append("- 系统兼容性")
        docs.append("")
        docs.append("**Q: 截图功能异常？**")
        docs.append("A: 可能的原因：")
        docs.append("- 磁盘空间不足")
        docs.append("- 权限问题")
        docs.append("- 显卡驱动问题")
        docs.append("")
        docs.append("**Q: 数据导出失败？**")
        docs.append("A: 请检查：")
        docs.append("- 目标目录是否有写入权限")
        docs.append("- 磁盘空间是否足够")
        docs.append("- 数据文件是否损坏")
        docs.append("")
        docs.append("### 性能问题")
        docs.append("")
        docs.append("**Q: 系统运行缓慢？**")
        docs.append("A: 优化建议：")
        docs.append("- 关闭不必要的程序")
        docs.append("- 增加系统内存")
        docs.append("- 清理磁盘空间")
        docs.append("")
        docs.append("**Q: 内存占用过高？**")
        docs.append("A: 解决方法：")
        docs.append("- 定期重启服务")
        docs.append("- 清理历史数据")
        docs.append("- 调整监控频率")
        docs.append("")
        
        # 技术支持
        docs.append("## 技术支持")
        docs.append("")
        docs.append("### 联系方式")
        docs.append("")
        docs.append("- **邮箱**: support@example.com")
        docs.append("- **电话**: 400-123-4567")
        docs.append("- **在线文档**: https://docs.example.com")
        docs.append("- **社区论坛**: https://forum.example.com")
        docs.append("")
        docs.append("### 版本信息")
        docs.append("")
        docs.append(f"- **当前版本**: v1.0")
        docs.append(f"- **发布日期**: {self.export_time.strftime('%Y-%m-%d')}")
        docs.append("- **更新频率**: 每月更新")
        docs.append("")
        docs.append("### 更新日志")
        docs.append("")
        docs.append("#### v1.0 (2024-11-03)")
        docs.append("- 初始版本发布")
        docs.append("- 基础监控功能")
        docs.append("- Web界面")
        docs.append("- 多格式导出")
        docs.append("- 主题切换")
        docs.append("")
        
        # 页脚
        docs.append("---")
        docs.append("")
        docs.append("*帮助手册由 UIExporter HelpDocs Exporter v1.0 生成*")
        docs.append("")
        docs.append("© 2024 系统监控器项目组. 保留所有权利.")
        
        return '\n'.join(docs)