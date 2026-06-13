"""AI 服务 - 使用 AgentRunner LLMClient 进行测试用例生成"""
import os
import json
from typing import List, Dict, Any, Generator, Optional, Callable

from ...config.settings import config as global_config, ModelPresets
from ...utils.llm import LLMClient, build_multimodal_message

from .pdf_service import pdf_service
from .openapi_service import openapi_service


class AIService:
    """AI 测试用例生成服务"""

    def __init__(self):
        self._vision_client = None
        self._text_client = None

    @property
    def vision_client(self) -> LLMClient:
        """获取视觉模型客户端"""
        if self._vision_client is None:
            # 使用通义千问 VL 模型
            self._vision_client = LLMClient(global_config.llm)
        return self._vision_client

    @property
    def text_client(self) -> LLMClient:
        """获取文本模型客户端"""
        if self._text_client is None:
            # 使用配置中的模型
            self._text_client = LLMClient(global_config.llm)
        return self._text_client

    def _get_model_client_for_file_type(self, file_path: str):
        """根据文件类型选择合适的模型客户端"""
        file_extension = file_path.lower().split('.')[-1] if '.' in file_path else ''

        # 图像文件使用支持视觉的模型客户端
        if file_extension in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']:
            # 检查配置的模型是否支持视觉
            if ModelPresets.supports_vision(global_config.llm.api_base, global_config.llm.model):
                return self.vision_client
            else:
                # 如果不支持视觉，使用文本模型
                return self.text_client
        else:
            # 非图像文件使用文本模型客户端
            return self.text_client

    def generate_test_cases_stream(
        self,
        file_path: str,
        context: str,
        requirements: str,
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> Generator[str, None, None]:
        """
        基于文件分析、上下文和需求生成测试用例

        参数:
            file_path: 文件路径（图像或其他类型）
            context: 用户提供的上下文
            requirements: 用户提供的需求
            stream_callback: 流式输出回调函数

        返回:
            生成器 yields Markdown 格式的测试用例
        """
        # 根据文件类型选择合适的模型客户端
        model_client = self._get_model_client_for_file_type(file_path)
        file_extension = file_path.lower().split('.')[-1] if '.' in file_path else ''

        # 构建系统消息和用户消息
        system_message, user_message = self._build_prompt(file_path, file_extension, context, requirements)

        # 检查用户消息中是否包含错误信息
        is_error_message = False
        if isinstance(user_message, str):
            if user_message.startswith("PDF处理失败"):
                is_error_message = True
            elif user_message.startswith("OpenAPI文档处理失败"):
                is_error_message = True
            elif user_message.startswith("无法读取文件内容"):
                is_error_message = True

        if is_error_message:
            # 首先输出标题
            yield "# 测试用例生成\n\n"
            yield f"**文件信息**\n"
            yield f"- 文件类型: {file_extension.upper()}\n\n"
            yield "---\n\n"
            yield f"\n\n**错误**: {user_message}\n"
            return

        # 首先输出标题
        yield "# 正在生成测试用例...\n\n"
        yield f"**文件信息**\n"
        yield f"- 文件类型: {file_extension.upper() if file_extension else '未知'}\n"
        yield f"- 使用模型: {global_config.llm.model}\n\n"
        yield "---\n\n"

        # 调用 LLM 生成内容
        # 对于图像文件，需要构建多模态消息
        user_message_dict = user_message  # 默认为纯文本
        if file_extension in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']:
            # 验证文件是否存在
            if not os.path.exists(file_path):
                yield f"\n\n**错误**: 图片文件不存在: {file_path}\n"
                return

            # Dashscope 的多模态消息格式
            from ...utils.llm import encode_image_base64

            try:
                image_base64 = encode_image_base64(file_path)
                # Dashscope 使用 URL 格式，需要指定正确的 MIME 类型
                image_mime = f"image/{file_extension.replace('jpg', 'jpeg').replace('jpe', 'jpeg')}"
                # Dashscope 要求文本在前，图片在后
                user_message_dict = [
                    {
                        "type": "text",
                        "text": user_message
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime};base64,{image_base64}"
                        }
                    }
                ]
            except Exception as e:
                import traceback
                yield f"\n\n**错误**: 图片编码失败 - {str(e)}\n"
                yield f"\n堆栈跟踪:\n```\n{traceback.format_exc()}\n```"
                return

        try:
            # 使用队列来传递流式数据
            from queue import Queue
            from threading import Thread

            result_queue = Queue()

            def callback(content: str):
                """流式输出回调函数 - 将内容放入队列"""
                result_queue.put(content)

            # 在单独的线程中调用 LLM
            def call_llm():
                try:
                    model_client.call(
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message_dict}
                        ],
                        stream_callback=callback
                    )
                finally:
                    # 发送结束标记
                    result_queue.put(None)

            # 启动线程
            thread = Thread(target=call_llm, daemon=True)
            thread.start()

            # 从队列中读取并 yield 数据
            while True:
                chunk = result_queue.get()
                if chunk is None:
                    break
                yield chunk

            # 等待线程结束
            thread.join()

        except Exception as e:
            import traceback
            yield f"\n\n**错误**: LLM调用失败 - {str(e)}\n"
            yield f"\n堆栈跟踪:\n```\n{traceback.format_exc()}\n```"

    def _build_prompt(self, file_path: str, file_extension: str, context: str, requirements: str) -> tuple:
        """构建提示词"""
        file_type_info = ""
        user_content = ""

        # 检查是否为图像文件
        if file_extension in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']:
            # 构建图像分析提示词
            file_type_info = f"文件类型: 图像 ({file_extension.upper()})"

            user_content = f"""请基于上传的图像生成全面的测试用例。

上下文信息: {context}

需求: {requirements}

**重要格式要求**：
请严格按照以下格式生成测试用例，这对于系统解析非常重要：

1. 每个测试用例必须以二级标题开始：## TC-001: 测试标题
2. 每个测试用例必须包含以下字段（使用加粗格式）：
   - **优先级:** 高/中/低
   - **描述:** 测试用例的详细描述
   - **前置条件:** 执行测试前的条件（如果有）

3. 测试步骤必须使用标准Markdown表格格式：

### 测试步骤

| # | 步骤描述 | 预期结果 |
| --- | --- | --- |
| 1 | 具体的操作步骤 | 期望看到的结果 |
| 2 | 下一个操作步骤 | 对应的期望结果 |

请严格遵循此格式，确保每个测试用例都包含完整的信息和正确的表格格式。
请确保测试用例覆盖全面，包含正向和负向测试场景。"""

            system_message = """你是一个专业的测试用例生成器，擅长基于图像生成全面的测试用例。

**关键要求**：
1. 必须严格按照指定的 Markdown 格式生成测试用例
2. 每个测试用例必须以 ## TC-XXX: 标题 格式开始
3. 必须包含 **优先级:**、**描述:**、**前置条件:** 等加粗字段
4. 测试步骤必须使用标准的 Markdown 表格格式，包含表头和分隔行
5. 表格必须有三列：#、步骤描述、预期结果
6. 确保格式完全符合要求，以便系统能够正确解析

请严格遵循格式要求，这对于系统解析测试用例非常重要。"""

        elif file_extension == 'pdf':
            # 处理 PDF 文件
            try:
                pdf_content = pdf_service.extract_text_from_pdf(file_path)
                file_type_info = f"文件类型: PDF"

                user_content = f"""请基于上传的PDF文档生成全面的测试用例。

PDF文档信息:
- 标题: {pdf_content['metadata'].get('title', '未知')}
- 页数: {pdf_content['metadata'].get('pages', '未知')}

文档内容:
{pdf_content['text'][:8000]}{'...(内容过长，已截断)' if len(pdf_content['text']) > 8000 else ''}

上下文信息: {context}

需求: {requirements}

请先以 Markdown 格式生成测试用例，包含以下内容：
1. 测试用例 ID 和标题（使用二级标题格式，如 ## TC-001: 测试标题）
2. 优先级（加粗显示，如 **优先级:** 高）
3. 描述（加粗显示，如 **描述:** 测试描述）
4. 前置条件（如果有，加粗显示，如 **前置条件:** 条件描述）
5. 测试步骤和预期结果（使用标准 Markdown 表格格式）

对于测试步骤表格，请使用以下格式：

### 测试步骤

| # | 步骤描述 | 预期结果 |
| --- | --- | --- |
| 1 | 第一步描述 | 第一步预期结果 |
| 2 | 第二步描述 | 第二步预期结果 |

请确保表格格式正确，包含表头和分隔行。

请确保测试用例覆盖全面，包含正向和负向测试场景。"""

                system_message = "你是一个专业的测试用例生成器，擅长基于文档内容生成全面的测试用例。请先以标准 Markdown 格式生成测试用例，包含正确的表格格式。"

            except Exception as e:
                # 在生成器中处理错误，不要在 _build_prompt 中 yield
                user_content = f"PDF处理失败: {str(e)}"
                system_message = "你是一个专业的测试用例生成器。"

        elif file_extension in ['json', 'yaml', 'yml']:
            # 处理 OpenAPI 文件
            try:
                api_data = openapi_service.parse_openapi_file(file_path)
                api_info = api_data['api_info']
                file_type_info = f"文件类型: OpenAPI ({file_extension.upper()})"

                user_content = f"""请基于上传的OpenAPI/Swagger文档生成API测试用例。

API文档信息:
- 标题: {api_info['info'].get('title', '未知')}
- 版本: {api_info['info'].get('version', '未知')}
- 描述: {api_info['info'].get('description', '无描述')}
- API路径数量: {len(api_info['paths'])}

API端点概览:
{self._format_api_endpoints_for_prompt(api_info)}

上下文信息: {context}

需求: {requirements}

请先以 Markdown 格式生成测试用例，包含以下内容：
1. 测试用例 ID 和标题（使用二级标题格式，如 ## TC-001: 测试标题）
2. 优先级（加粗显示，如 **优先级:** 高）
3. 描述（加粗显示，如 **描述:** 测试描述）
4. 前置条件（如果有，加粗显示，如 **前置条件:** 条件描述）
5. 测试步骤和预期结果（使用标准 Markdown 表格格式）

请确保测试用例覆盖全面，特别关注：
- 所有API端点的测试
- 正向测试（正常请求和响应）
- 负向测试（错误参数、认证失败等）
- 边界值测试
- 不同HTTP状态码的验证
- 请求和响应数据格式验证"""

                system_message = "你是一个专业的API测试用例生成器，擅长基于OpenAPI/Swagger文档生成全面的API测试用例。请先以标准 Markdown 格式生成测试用例，包含正确的表格格式。"

            except Exception as e:
                # 在生成器中处理错误，不要在 _build_prompt 中 yield
                user_content = f"OpenAPI文档处理失败: {str(e)}"
                system_message = "你是一个专业的API测试用例生成器。"

        else:
            # 处理其他文本文件
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        file_content = f.read()
                except:
                    # 在生成器中处理错误，不要在 _build_prompt 中 yield
                    user_content = "无法读取文件内容，不支持的编码格式"
                    system_message = "你是一个专业的测试用例生成器。"
                    return system_message, user_content

            file_type_info = f"文件类型: 文本"

            user_content = f"""请基于上传的文件内容生成全面的测试用例。

文件内容:
{file_content[:5000]}{'...(内容过长，已截断)' if len(file_content) > 5000 else ''}

上下文信息: {context}

需求: {requirements}

请先以 Markdown 格式生成测试用例，包含以下内容：
1. 测试用例 ID 和标题（使用二级标题格式，如 ## TC-001: 测试标题）
2. 优先级（加粗显示，如 **优先级:** 高）
3. 描述（加粗显示，如 **描述:** 测试描述）
4. 前置条件（如果有，加粗显示，如 **前置条件:** 条件描述）
5. 测试步骤和预期结果（使用标准 Markdown 表格格式）

请确保测试用例覆盖全面，包含正向和负向测试场景。"""

            system_message = "你是一个专业的测试用例生成器，擅长基于文档内容生成全面的测试用例。请先以标准 Markdown 格式生成测试用例，包含正确的表格格式。"

        return system_message, user_content

    def _format_api_endpoints_for_prompt(self, api_info: Dict[str, Any]) -> str:
        """格式化 API 端点信息用于提示词"""
        formatted = ""

        for path_info in api_info['paths'][:10]:  # 限制显示的端点数量
            formatted += f"### {path_info['path']}\n"
            for op in path_info['operations']:
                formatted += f"- **{op['method']}**: {op['summary'] or op['description']}\n"
                if op['parameters']:
                    formatted += f"  - 参数: {len(op['parameters'])} 个\n"
                if op['responses']:
                    formatted += f"  - 响应: {', '.join(op['responses'].keys())}\n"
            formatted += "\n"

        return formatted

    def generate_mindmap_from_test_cases(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        从测试用例生成思维导图数据

        参数:
            test_cases: 测试用例列表

        返回:
            思维导图的 JSON 数据结构
        """
        if not test_cases:
            return {"name": "测试用例", "children": []}

        # 创建根节点
        mindmap = {
            "name": "测试用例总览",
            "children": []
        }

        # 按优先级分组
        priority_groups = {}
        for tc in test_cases:
            priority = tc.get('priority', 'Medium')
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(tc)

        # 为每个优先级创建分支
        for priority, cases in priority_groups.items():
            priority_node = {
                "name": f"{priority} 优先级 ({len(cases)}个)",
                "children": []
            }

            for tc in cases:
                test_case_node = {
                    "name": tc.get('title', tc.get('id', '未知测试用例')),
                    "children": []
                }

                # 添加描述节点
                if tc.get('description'):
                    test_case_node["children"].append({
                        "name": f"描述: {tc['description'][:50]}{'...' if len(tc['description']) > 50 else ''}",
                        "children": []
                    })

                # 添加前置条件节点
                if tc.get('preconditions'):
                    test_case_node["children"].append({
                        "name": f"前置条件: {tc['preconditions'][:50]}{'...' if len(tc['preconditions']) > 50 else ''}",
                        "children": []
                    })

                # 添加测试步骤节点
                if tc.get('steps'):
                    steps_node = {
                        "name": f"测试步骤 ({len(tc['steps'])}步)",
                        "children": []
                    }

                    for step in tc['steps'][:5]:  # 限制显示的步骤数量
                        step_node = {
                            "name": f"步骤{step.get('step_number', '?')}: {step.get('description', '')[:30]}{'...' if len(step.get('description', '')) > 30 else ''}",
                            "children": [{
                                "name": f"预期: {step.get('expected_result', '')[:40]}{'...' if len(step.get('expected_result', '')) > 40 else ''}",
                                "children": []
                            }]
                        }
                        steps_node["children"].append(step_node)

                    test_case_node["children"].append(steps_node)

                priority_node["children"].append(test_case_node)

            mindmap["children"].append(priority_node)

        # 添加统计信息节点
        stats_node = {
            "name": "统计信息",
            "children": [
                {"name": f"总测试用例: {len(test_cases)}", "children": []},
                {"name": f"优先级分布: {len(priority_groups)}种", "children": []},
                {"name": f"平均步骤数: {self._calculate_average_steps(test_cases):.1f}", "children": []}
            ]
        }
        mindmap["children"].append(stats_node)

        return mindmap

    def _calculate_average_steps(self, test_cases: List[Dict[str, Any]]) -> float:
        """计算测试用例的平均步骤数"""
        total_steps = 0
        valid_cases = 0

        for tc in test_cases:
            if tc.get('steps'):
                total_steps += len(tc['steps'])
                valid_cases += 1

        return total_steps / valid_cases if valid_cases > 0 else 0


# 服务实例
ai_service = AIService()
