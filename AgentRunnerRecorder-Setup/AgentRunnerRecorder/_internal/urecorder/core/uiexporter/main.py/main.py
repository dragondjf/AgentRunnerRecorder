#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UIExporter主程序
提供命令行接口和API接口
"""

import os
import sys
import argparse
from pathlib import Path
from loguru import logger

from . import (
    export_data,
    list_supported_formats,
    get_format_info,
    validate_export_type
)


def setup_logging(verbose: bool = False):
    """设置日志配置"""
    level = "DEBUG" if verbose else "INFO"
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )


def cmd_list_formats():
    """列出支持的导出格式"""
    formats = list_supported_formats()
    print("支持的导出格式:")
    print("-" * 50)
    
    for fmt in formats:
        info = get_format_info(fmt)
        name = info.get('name', fmt)
        desc = info.get('description', '')
        ext = info.get('file_extension', '')
        print(f"{fmt:12} | {name:20} | {desc:30} | {ext}")
    
    print("-" * 50)
    print(f"共 {len(formats)} 种格式")


def cmd_export(args):
    """执行导出命令"""
    data_dir = Path(args.data_dir)
    output_path = Path(args.output)
    
    # 验证数据目录
    if not data_dir.exists():
        logger.error(f"数据目录不存在: {data_dir}")
        return False
    
    # 验证导出类型
    if not validate_export_type(args.format):
        logger.error(f"不支持的导出格式: {args.format}")
        logger.info(f"支持的格式: {list_supported_formats()}")
        return False
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"开始导出 {args.format} 格式")
    logger.info(f"数据目录: {data_dir}")
    logger.info(f"输出文件: {output_path}")
    
    # 执行导出
    success = export_data(args.format, str(data_dir), str(output_path))
    
    if success:
        logger.info(f"导出成功: {output_path}")
        return True
    else:
        logger.error(f"导出失败")
        return False


def cmd_info(args):
    """显示格式信息"""
    format_type = args.format
    
    if not validate_export_type(format_type):
        logger.error(f"不支持的导出格式: {format_type}")
        return False
    
    info = get_format_info(format_type)
    
    print(f"导出格式: {format_type}")
    print("-" * 30)
    for key, value in info.items():
        print(f"{key}: {value}")
    
    return True


def create_parser():
    """创建命令行解析器"""
    parser = argparse.ArgumentParser(
        description="UIExporter - 统一的用户界面导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s list                                    # 列出支持的格式
  %(prog)s info zip                                # 查看ZIP格式信息
  %(prog)s export zip /path/to/data /path/to/output.zip
  %(prog)s export pdf /path/to/data /path/to/report.pdf --verbose
        """
    )
    
    parser.add_argument(
        '--version', 
        action='version', 
        version='UIExporter v1.0.0'
    )
    
    parser.add_argument(
        '--verbose', '-v', 
        action='store_true', 
        help='显示详细信息'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # list命令
    list_parser = subparsers.add_parser('list', help='列出支持的导出格式')
    
    # info命令
    info_parser = subparsers.add_parser('info', help='查看导出格式信息')
    info_parser.add_argument('format', help='导出格式类型')
    
    # export命令
    export_parser = subparsers.add_parser('export', help='导出数据')
    export_parser.add_argument('format', help='导出格式类型')
    export_parser.add_argument('data_dir', help='数据目录路径')
    export_parser.add_argument('output', help='输出文件路径')
    
    return parser


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose)
    
    # 处理命令
    if args.command == 'list':
        cmd_list_formats()
    elif args.command == 'info':
        cmd_info(args)
    elif args.command == 'export':
        success = cmd_export(args)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()