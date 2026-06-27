#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试导出器图片路径转换功能
"""

import os
import re
from loguru import logger


def test_image_path_replacement():
    """测试图片路径替换逻辑"""
    test_cases = [
        {
            "name": "API路径格式",
            "input": "![操作截图](/api/v1/file?path=mydata12/my_screenshots/active_window_20260308_140905_525.png)",
            "expected": "![操作截图](./my_screenshots/active_window_20260308_140905_525.png)"
        },
        {
            "name": "HTTP URL格式",
            "input": "![操作截图](http://localhost:8000/my_screenshots/active_window_20260308_140905_525.png)",
            "expected": "![操作截图](./my_screenshots/active_window_20260308_140905_525.png)"
        },
        {
            "name": "相对路径格式",
            "input": "![操作截图](./my_screenshots/active_window_20260308_140905_525.png)",
            "expected": "![操作截图](./my_screenshots/active_window_20260308_140905_525.png)"
        },
        {
            "name": "绝对路径格式(不应该匹配)",
            "input": "![操作截图](F:\\workspace\\my_screenshots\\active_window_20260308_140905_525.png)",
            "expected": "![操作截图](F:\\workspace\\my_screenshots\\active_window_20260308_140905_525.png)"
        },
        {
            "name": "多个图片",
            "input": "![图1](/api/v1/file?path=project1/img1.png)\n\n![图2](http://localhost:8000/img2.png)",
            "expected": "![图1](./my_screenshots/img1.png)\n\n![图2](./my_screenshots/img2.png)"
        }
    ]

    def replace_image_path(match):
        # match.group(0) 是整个匹配的字符串 ![alt](url)
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
    # url可以是:
    # 1. API路径: /api/v1/file?path=xxx/yyy/zzz.png
    # 2. HTTP URL: http://xxx/yyy/zzz.png
    # 3. 相对路径: ./yyy/zzz.png
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

    passed = 0
    failed = 0

    logger.info("=" * 60)
    logger.info("开始测试图片路径转换功能")
    logger.info("=" * 60)

    for i, test_case in enumerate(test_cases, 1):
        result = re.sub(image_pattern, replace_image_path, test_case["input"])
        success = result == test_case["expected"]
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"\n测试 {i}: {test_case['name']} - {status}")
        logger.info(f"输入: {test_case['input']}")
        logger.info(f"期望: {test_case['expected']}")
        logger.info(f"结果: {result}")
        
        if success:
            passed += 1
        else:
            failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"测试完成: {passed}/{len(test_cases)} 通过, {failed} 失败")
    logger.info("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = test_image_path_replacement()
    exit(0 if success else 1)
