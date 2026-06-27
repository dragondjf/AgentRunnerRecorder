"""
修复 records.json 中图片路径的脚本
将绝对路径转换为 API 路径
"""

import os
import json
import re
import sys
from pathlib import Path
from loguru import logger


def fix_records_json_file(file_path):
    """
    修复单个 records.json 文件中的图片路径
    
    Args:
        file_path (str): records.json 文件路径
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"文件不存在: {file_path}")
            return False
        
        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        modified = False
        
        # 处理 slides 数组
        if 'slides' in data:
            # 提取项目名称(从文件路径获取)
            project_name = Path(file_path).parent.name
            
            for slide in data['slides']:
                if 'markdown' in slide:
                    markdown = slide['markdown']
                    
                    # 匹配绝对路径模式: ./F:\path\to\file.png 或 ./C:\path\to\file.png
                    # 使用正则表达式匹配并替换
                    pattern = r'!\[操作截图\]\(\./[A-Za-z]:[^)]+\)'
                    
                    def replace_path(match):
                        nonlocal modified
                        modified = True
                        # 提取文件名
                        full_match = match.group(0)
                        # 从路径中提取文件名 (最后一个斜杠后的部分)
                        filename_match = re.search(r'([^/\\]+\.png)', full_match)
                        if filename_match:
                            filename = filename_match.group(1)
                            return f'![操作截图](/api/v1/file?path={project_name}/my_screenshots/{filename})'
                        return full_match
                    
                    new_markdown = re.sub(pattern, replace_path, markdown)
                    slide['markdown'] = new_markdown
        
        # 如果有修改,保存文件
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 已修复: {file_path}")
            return True
        else:
            logger.info(f"ℹ️ 无需修复: {file_path}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 修复失败 {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return False


def fix_all_records_in_directory(data_dir):
    """
    修复目录下所有项目的 records.json 文件
    
    Args:
        data_dir (str): 数据目录路径
    """
    data_path = Path(data_dir)
    
    if not data_path.exists():
        logger.error(f"数据目录不存在: {data_dir}")
        return
    
    logger.info(f"🔍 开始扫描目录: {data_dir}")
    
    # 查找所有 records.json 文件
    total_files = 0
    fixed_files = 0
    
    for project_dir in data_path.iterdir():
        if project_dir.is_dir():
            records_file = project_dir / "records.json"
            if records_file.exists():
                total_files += 1
                if fix_records_json_file(str(records_file)):
                    fixed_files += 1
    
    logger.info(f"=" * 50)
    logger.info(f"📊 修复完成:")
    logger.info(f"   - 总文件数: {total_files}")
    logger.info(f"   - 已修复: {fixed_files}")
    logger.info(f"   - 无需修复: {total_files - fixed_files}")
    logger.info(f"=" * 50)


if __name__ == "__main__":
    # 设置日志
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )
    
    # 获取当前目录的 filestorage 目录
    script_dir = Path(__file__).parent
    filestorage_dir = script_dir / "filestorage"
    
    if not filestorage_dir.exists():
        logger.error(f"找不到 filestorage 目录: {filestorage_dir}")
    else:
        fix_all_records_in_directory(str(filestorage_dir))
