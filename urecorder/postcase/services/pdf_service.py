"""PDF 处理服务 - 从 PDF 文件提取文本和需求分析"""
import os
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class PDFService:
    """PDF 处理服务"""

    def __init__(self):
        self.supported_extensions = ['.pdf']

    def extract_text_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        从 PDF 文件中提取文本内容

        参数:
            pdf_path: PDF 文件路径

        返回:
            包含提取文本和元数据的字典
        """
        # 优先使用 pdfplumber
        if pdfplumber:
            try:
                return self._extract_with_pdfplumber(pdf_path)
            except Exception as e:
                print(f"pdfplumber 提取失败: {e}")

        # 备用方法 PyPDF2
        if PyPDF2:
            try:
                return self._extract_with_pypdf2(pdf_path)
            except Exception as e:
                print(f"PyPDF2 提取失败: {e}")

        raise Exception("无法提取 PDF 文本，请安装 pdfplumber 或 PyPDF2")

    def _extract_with_pdfplumber(self, pdf_path: str) -> Dict[str, Any]:
        """使用 pdfplumber 提取文本"""
        text_content = ""
        metadata = {}

        with pdfplumber.open(pdf_path) as pdf:
            # 提取元数据
            if pdf.metadata:
                metadata = {
                    'title': pdf.metadata.get('Title', ''),
                    'author': pdf.metadata.get('Author', ''),
                    'subject': pdf.metadata.get('Subject', ''),
                    'creator': pdf.metadata.get('Creator', ''),
                    'creation_date': pdf.metadata.get('CreationDate', ''),
                    'modification_date': pdf.metadata.get('ModDate', ''),
                    'pages': len(pdf.pages)
                }

            # 提取每页文本
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_content += f"\n--- 第 {page_num} 页 ---\n"
                    text_content += page_text
                    text_content += "\n"

        return {
            'text': text_content,
            'metadata': metadata,
            'extraction_method': 'pdfplumber',
            'extracted_at': datetime.now().isoformat()
        }

    def _extract_with_pypdf2(self, pdf_path: str) -> Dict[str, Any]:
        """使用 PyPDF2 提取文本"""
        text_content = ""
        metadata = {}

        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)

            # 提取元数据
            if pdf_reader.metadata:
                metadata = {
                    'title': pdf_reader.metadata.get('/Title', ''),
                    'author': pdf_reader.metadata.get('/Author', ''),
                    'subject': pdf_reader.metadata.get('/Subject', ''),
                    'creator': pdf_reader.metadata.get('/Creator', ''),
                    'pages': len(pdf_reader.pages)
                }

            # 提取每页文本
            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_content += f"\n--- 第 {page_num} 页 ---\n"
                    text_content += page_text
                    text_content += "\n"

        return {
            'text': text_content,
            'metadata': metadata,
            'extraction_method': 'pypdf2',
            'extracted_at': datetime.now().isoformat()
        }

    def analyze_requirements_structure(self, text: str) -> Dict[str, Any]:
        """
        分析需求文档的结构，提取关键信息

        参数:
            text: 提取的文本内容

        返回:
            结构化的需求信息
        """
        analysis = {
            'sections': [],
            'requirements': [],
            'functional_requirements': [],
            'non_functional_requirements': [],
            'use_cases': [],
            'business_rules': [],
            'data_requirements': []
        }

        # 分割文本为行
        lines = text.split('\n')
        current_section = None
        current_content = []

        # 常见的需求文档关键词模式
        section_patterns = {
            'functional': r'(功能需求|功能性需求|functional\s+requirement)',
            'non_functional': r'(非功能需求|非功能性需求|non.?functional\s+requirement)',
            'use_case': r'(用例|使用场景|use\s+case)',
            'business_rule': r'(业务规则|business\s+rule)',
            'data': r'(数据需求|数据结构|data\s+requirement)'
        }

        requirement_patterns = [
            r'需求\s*[：:]\s*(.+)',
            r'要求\s*[：:]\s*(.+)',
            r'应该\s*(.+)',
            r'必须\s*(.+)',
            r'系统\s*(.+)',
            r'用户\s*(.+)',
            r'REQ[-_]\d+\s*[：:]\s*(.+)'
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测章节标题
            if self._is_section_header(line):
                if current_section and current_content:
                    analysis['sections'].append({
                        'title': current_section,
                        'content': '\n'.join(current_content)
                    })
                current_section = line
                current_content = []
                continue

            # 检测需求条目
            for pattern in requirement_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    requirement = {
                        'id': f"REQ-{len(analysis['requirements']) + 1}",
                        'text': line,
                        'extracted_content': match.group(1) if match.groups() else line,
                        'section': current_section or '未分类'
                    }
                    analysis['requirements'].append(requirement)

                    # 根据上下文分类需求
                    self._categorize_requirement(requirement, analysis, section_patterns)
                    break

            if current_section:
                current_content.append(line)

        # 添加最后一个章节
        if current_section and current_content:
            analysis['sections'].append({
                'title': current_section,
                'content': '\n'.join(current_content)
            })

        return analysis

    def _is_section_header(self, line: str) -> bool:
        """判断是否为章节标题"""
        patterns = [
            r'^\d+\.?\s+.+',  # 1. 标题
            r'^第\s*[一二三四五六七八九十\d]+\s*[章节部分]\s*.+',  # 第一章
            r'^[一二三四五六七八九十]+[、．.]\s*.+',  # 一、标题
            r'^[A-Z]+\.?\s+.+',  # A. 标题
            r'^\s*#+\s+.+',  # Markdown标题
        ]

        for pattern in patterns:
            if re.match(pattern, line):
                return True

        return False

    def _categorize_requirement(self, requirement: Dict, analysis: Dict, section_patterns: Dict):
        """根据内容将需求分类"""
        text = requirement['text'].lower()
        section = requirement.get('section', '').lower()

        # 根据章节和内容分类
        if re.search(section_patterns['functional'], section + ' ' + text, re.IGNORECASE):
            analysis['functional_requirements'].append(requirement)
        elif re.search(section_patterns['non_functional'], section + ' ' + text, re.IGNORECASE):
            analysis['non_functional_requirements'].append(requirement)
        elif re.search(section_patterns['use_case'], section + ' ' + text, re.IGNORECASE):
            analysis['use_cases'].append(requirement)
        elif re.search(section_patterns['business_rule'], section + ' ' + text, re.IGNORECASE):
            analysis['business_rules'].append(requirement)
        elif re.search(section_patterns['data'], section + ' ' + text, re.IGNORECASE):
            analysis['data_requirements'].append(requirement)


# 服务实例
pdf_service = PDFService()
