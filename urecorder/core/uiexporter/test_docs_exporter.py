#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试用例文档导出器
基于监控数据生成测试用例文档
"""

import os
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

from .base_exporter import BaseExporter


class TestDocsExporter(BaseExporter):
    """测试用例文档导出器"""
    
    def export(self) -> str:
        """
        导出测试用例文档
        
        Returns:
            str: 输出文件路径，导出失败返回空字符串
        """
        try:
            # 生成输出文件路径
            timestamp = self.export_time.strftime('%Y%m%d_%H%M%S')
            output_dir = self.data_dir.parent / 'data' / 'exports'
            output_file = output_dir / f'export_test-docs_{timestamp}.md'
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"开始导出测试用例文档: {output_file}")
            
            # 生成测试用例文档内容
            test_docs_content = self._generate_test_docs()
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(test_docs_content)
            
            logger.info(f"测试用例文档导出成功: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"测试用例文档导出失败: {e}")
            return ""
    
    def _generate_test_docs(self) -> str:
        """生成测试用例文档"""
        monitoring_data = self.load_monitoring_data()
        summary_data = self.load_summary_data()
        
        docs = []
        
        # 文档标题和基本信息
        docs.append("# 系统监控测试用例文档")
        docs.append("")
        docs.append(f"**生成时间**: {self.export_time.strftime('%Y-%m-%d %H:%M:%S')}")
        docs.append(f"**数据来源**: {self.data_dir}")
        docs.append("")
        
        # 文档目录
        docs.append("## 目录")
        docs.append("")
        docs.append("1. [测试概述](#测试概述)")
        docs.append("2. [测试环境](#测试环境)")
        docs.append("3. [功能测试用例](#功能测试用例)")
        docs.append("4. [性能测试用例](#性能测试用例)")
        docs.append("5. [异常测试用例](#异常测试用例)")
        docs.append("6. [测试数据](#测试数据)")
        docs.append("")
        
        # 测试概述
        docs.append("## 测试概述")
        docs.append("")
        docs.append("本文档基于系统监控数据自动生成，包含了系统功能的测试用例。")
        docs.append("")
        
        if summary_data:
            docs.append("### 测试范围")
            docs.append("")
            docs.append(f"- 总操作次数: {summary_data.get('total_operations', 'N/A')}")
            docs.append(f"- 键盘操作: {summary_data.get('keyboard_operations', 'N/A')}")
            docs.append(f"- 鼠标操作: {summary_data.get('mouse_operations', 'N/A')}")
            docs.append(f"- 录制时长: {summary_data.get('recording_duration', 'N/A')}")
            docs.append("")
        
        # 测试环境
        docs.append("## 测试环境")
        docs.append("")
        docs.append("| 环境项 | 说明 |")
        docs.append("|--------|------|")
        docs.append("| 操作系统 | Windows/macOS/Linux |")
        docs.append("| 监控工具 | 系统行为监控器 |")
        docs.append("| 浏览器 | Chrome/Firefox/Safari |")
        docs.append("| 屏幕分辨率 | 1920x1080 (推荐) |")
        docs.append("")
        
        # 功能测试用例
        docs.append("## 功能测试用例")
        docs.append("")
        
        if monitoring_data and 'operations' in monitoring_data:
            operations = monitoring_data['operations']
            test_cases = self._generate_functional_test_cases(operations)
            
            for i, test_case in enumerate(test_cases, 1):
                docs.append(f"### 测试用例 {i:03d}")
                docs.append("")
                docs.append(f"**用例名称**: {test_case['name']}")
                docs.append(f"**测试目标**: {test_case['objective']}")
                docs.append(f"**前置条件**: {test_case['precondition']}")
                docs.append("")
                docs.append("**测试步骤**:")
                for j, step in enumerate(test_case['steps'], 1):
                    docs.append(f"{j}. {step}")
                docs.append("")
                docs.append(f"**预期结果**: {test_case['expected_result']}")
                docs.append("")
                docs.append("---")
                docs.append("")
        else:
            docs.append("暂无功能测试用例数据")
            docs.append("")
        
        # 性能测试用例
        docs.append("## 性能测试用例")
        docs.append("")
        
        performance_cases = [
            {
                "name": "系统响应时间测试",
                "objective": "验证系统操作的响应时间是否符合要求",
                "precondition": "系统正常运行，无其他占用资源的程序",
                "steps": [
                    "启动系统监控",
                    "执行一系列键盘和鼠标操作",
                    "记录每个操作的响应时间",
                    "统计分析响应时间数据"
                ],
                "expected_result": "95%以上的操作响应时间小于1秒"
            },
            {
                "name": "内存使用测试",
                "objective": "验证长时间运行时的内存使用情况",
                "precondition": "系统可用内存大于2GB",
                "steps": [
                    "启动系统监控",
                    "连续运行监控功能2小时以上",
                    "监控内存使用情况",
                    "检查是否存在内存泄漏"
                ],
                "expected_result": "内存使用稳定，无明显泄漏"
            },
            {
                "name": "CPU使用率测试",
                "objective": "验证系统监控对CPU资源的影响",
                "precondition": "系统CPU使用率低于50%",
                "steps": [
                    "记录监控前的CPU使用率",
                    "启动系统监控",
                    "执行各种操作",
                    "记录监控期间的CPU使用率"
                ],
                "expected_result": "CPU使用率增加不超过10%"
            }
        ]
        
        for i, test_case in enumerate(performance_cases, 1):
            docs.append(f"### 测试用例 {i:03d}")
            docs.append("")
            docs.append(f"**用例名称**: {test_case['name']}")
            docs.append(f"**测试目标**: {test_case['objective']}")
            docs.append(f"**前置条件**: {test_case['precondition']}")
            docs.append("")
            docs.append("**测试步骤**:")
            for j, step in enumerate(test_case['steps'], 1):
                docs.append(f"{j}. {step}")
            docs.append("")
            docs.append(f"**预期结果**: {test_case['expected_result']}")
            docs.append("")
            docs.append("---")
            docs.append("")
        
        # 异常测试用例
        docs.append("## 异常测试用例")
        docs.append("")
        
        exception_cases = [
            {
                "name": "磁盘空间不足测试",
                "objective": "验证磁盘空间不足时的系统行为",
                "precondition": "系统磁盘可用空间小于100MB",
                "steps": [
                    "模拟磁盘空间不足情况",
                    "尝试启动监控功能",
                    "观察系统反应"
                ],
                "expected_result": "系统给出明确提示，不应崩溃"
            },
            {
                "name": "权限不足测试",
                "objective": "验证权限不足时的系统行为",
                "precondition": "用户没有监控权限",
                "steps": [
                    "使用低权限用户登录",
                    "尝试启动监控功能",
                    "观察系统反应"
                ],
                "expected_result": "系统提示权限不足，不应执行监控"
            },
            {
                "name": "网络中断测试",
                "objective": "验证网络中断时的系统行为",
                "precondition": "系统依赖网络功能",
                "steps": [
                    "启动系统监控",
                    "断开网络连接",
                    "观察系统行为"
                ],
                "expected_result": "系统应能正常处理网络中断"
            }
        ]
        
        for i, test_case in enumerate(exception_cases, 1):
            docs.append(f"### 测试用例 {i:03d}")
            docs.append("")
            docs.append(f"**用例名称**: {test_case['name']}")
            docs.append(f"**测试目标**: {test_case['objective']}")
            docs.append(f"**前置条件**: {test_case['precondition']}")
            docs.append("")
            docs.append("**测试步骤**:")
            for j, step in enumerate(test_case['steps'], 1):
                docs.append(f"{j}. {step}")
            docs.append("")
            docs.append(f"**预期结果**: {test_case['expected_result']}")
            docs.append("")
            docs.append("---")
            docs.append("")
        
        # 测试数据
        docs.append("## 测试数据")
        docs.append("")
        
        if monitoring_data and 'operations' in monitoring_data:
            operations = monitoring_data['operations']
            
            docs.append("### 监控操作数据")
            docs.append("")
            docs.append(f"**数据量**: {len(operations)} 条操作记录")
            docs.append("")
            
            # 操作类型统计
            type_stats = {}
            for op in operations:
                op_type = op.get('type', 'Unknown')
                type_stats[op_type] = type_stats.get(op_type, 0) + 1
            
            docs.append("**操作类型分布**:")
            docs.append("")
            docs.append("| 操作类型 | 数量 |")
            docs.append("|----------|------|")
            for op_type, count in type_stats.items():
                docs.append(f"| {op_type} | {count} |")
            docs.append("")
            
            # 示例数据
            docs.append("### 示例数据")
            docs.append("")
            docs.append("```json")
            if operations:
                sample_op = operations[0]
                docs.append(json.dumps(sample_op, ensure_ascii=False, indent=2))
            docs.append("```")
            docs.append("")
        else:
            docs.append("暂无测试数据")
            docs.append("")
        
        # 页脚
        docs.append("---")
        docs.append("")
        docs.append("*测试用例文档由 UIExporter TestDocs Exporter v1.0 生成*")
        
        return '\n'.join(docs)
    
    def _generate_functional_test_cases(self, operations: list) -> list:
        """基于操作数据生成功能测试用例"""
        test_cases = []
        
        # 按操作类型分组
        operation_groups = {}
        for op in operations:
            op_type = op.get('type', 'Unknown')
            if op_type not in operation_groups:
                operation_groups[op_type] = []
            operation_groups[op_type].append(op)
        
        # 为每种操作类型生成测试用例
        for op_type, ops in operation_groups.items():
            if op_type == "键盘输入":
                test_case = {
                    "name": f"{op_type}功能测试",
                    "objective": f"验证{op_type}功能的正确性",
                    "precondition": "系统正常启动，焦点在输入框中",
                    "steps": [
                        "启动系统监控",
                        "在输入框中输入测试文本",
                        "验证输入内容是否正确记录",
                        "检查操作日志"
                    ],
                    "expected_result": "输入的文本被正确记录和显示"
                }
            elif op_type == "鼠标点击":
                test_case = {
                    "name": f"{op_type}功能测试",
                    "objective": f"验证{op_type}功能的正确性",
                    "precondition": "系统正常启动，目标元素可见",
                    "steps": [
                        "启动系统监控",
                        "点击目标元素",
                        "验证点击操作是否生效",
                        "检查操作日志"
                    ],
                    "expected_result": "点击操作被正确记录，目标元素状态改变"
                }
            elif op_type == "鼠标移动":
                test_case = {
                    "name": f"{op_type}功能测试",
                    "objective": f"验证{op_type}功能的正确性",
                    "precondition": "系统正常启动，鼠标指针可见",
                    "steps": [
                        "启动系统监控",
                        "移动鼠标到目标位置",
                        "验证鼠标轨迹是否正确记录",
                        "检查操作日志"
                    ],
                    "expected_result": "鼠标移动轨迹被正确记录"
                }
            else:
                # 通用测试用例
                test_case = {
                    "name": f"{op_type}功能测试",
                    "objective": f"验证{op_type}功能的正确性",
                    "precondition": "系统正常启动",
                    "steps": [
                        "启动系统监控",
                        f"执行{op_type}操作",
                        "验证操作是否正确执行",
                        "检查操作日志"
                    ],
                    "expected_result": f"{op_type}操作被正确记录和执行"
                }
            
            test_cases.append(test_case)
        
        return test_cases