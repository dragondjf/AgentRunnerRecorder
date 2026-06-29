# vl_blueprint.py
import os
import tempfile
import json
import requests
import time
import urllib.parse
from flask import Blueprint, request, Response, jsonify, send_from_directory, current_app
from werkzeug.utils import secure_filename
from typing import AsyncGenerator
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import MultiModalMessage as AGMultiModalMessage
from autogen_core import Image as AGImage
from PIL import Image as PILImage
from autogen_ext.models.openai import OpenAIChatCompletionClient
import asyncio
import httpx
from loguru import logger
from dotenv import load_dotenv
from pathlib import Path
import os

# Windows SSL 兼容：httpx 跳过证书验证（解决代理/系统 CA bundle 问题）
_http_client = httpx.AsyncClient(verify=False)


# 从脚本所在目录的上级（uirecordercore/）加载 .env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)
logger.info(f"加载 .env: {_env_path} (exists={_env_path.exists()})")
logger.info(f"MODEL_NAME={os.getenv('MODEL_NAME', 'NOT SET')}")

# 创建蓝图
qwen_vl_bp = Blueprint("vl", __name__, static_folder="static")

# 配置（每次调用时实时读取，支持运行时热更新）
def _get_model_config():
    """动态读取最新模型配置"""
    load_dotenv(_env_path)  # 重新加载 .env
    return {
        'model': os.getenv("MODEL_NAME", "qwen-vl-max-latest"),
        'api_key': os.getenv("OPENAI_API_KEY", "your-api-key"),
        'base_url': os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    }

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

async def generate_with_autogen(file_path: str, context: str, requirements: str) -> AsyncGenerator[str, None]:
    cfg = _get_model_config()
    model_client = OpenAIChatCompletionClient(
        model=cfg['model'],
        api_key=cfg['api_key'],
        base_url=cfg['base_url'],
        http_client=_http_client,
        model_info={
            "vision": True,
            "function_calling": False,
            "json_output": False,
            "family": "qwen",
            "multiple_system_messages": True,
            "structured_output": False,
        }
    )

    pil_image = PILImage.open(file_path)
    ag_image = AGImage(pil_image)

    prompt = "分析图像，输出标题和描述信息"
    if context.strip():
        prompt += f"\n上下文：{context}"
    if requirements.strip():
        prompt += f"\n需求：{requirements}"

    user_message = AGMultiModalMessage(content=[prompt, ag_image], source="user")

    system_message = (
        "你是一位多模态交互界面设计专家。请为图像生成一个简洁突出功能的标题和一段不超过500字的描述。忽略背景图片。\n"
        "严格遵循这个格式输出{\"title\": "", \"description\": ""}，标题需简洁点明核心功能，描述聚焦功能本身，不提及技术实现或输入方式。"
    )

    agent = AssistantAgent(
        name="vl_agent",
        model_client=model_client,
        system_message=system_message,
        model_client_stream=True,
    )

    # yield "data: # 正在生成标题和描述...\n\n"
    # yield f"data: - 模型: {MODEL_NAME}\n\n"
    # yield "data: ---\n\n"

    async for event in agent.run_stream(task=user_message):
        from autogen_agentchat.messages import ModelClientStreamingChunkEvent
        from autogen_agentchat.base import TaskResult

        if isinstance(event, ModelClientStreamingChunkEvent):
            yield f"data: {event.content}\n\n"
        elif isinstance(event, TaskResult):
            break

async def ai_analysis(image_source: str, context: str = "", requirements: str = "") -> dict:
    """非流式AI分析核心函数
    
    Args:
        image_source: 图片URL或文件路径
        context: 上下文信息
        requirements: 需求说明
    
    Returns:
        dict: 分析结果 {"title": "标题", "description": "描述"}
    """
    # 处理图片来源 - 如果是URL，下载到临时文件
    temp_file = None
    try:
        if image_source.startswith(('http://', 'https://')):
            # 从URL下载图片
            response = requests.get(image_source, timeout=30, verify=False)
            response.raise_for_status()
            
            # 获取文件扩展名
            parsed_url = urllib.parse.urlparse(image_source)
            file_extension = os.path.splitext(parsed_url.path)[1]
            if not file_extension:
                # 根据内容类型推断扩展名
                content_type = response.headers.get('content-type', '')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    file_extension = '.jpg'
                elif 'png' in content_type:
                    file_extension = '.png'
                elif 'webp' in content_type:
                    file_extension = '.webp'
                else:
                    file_extension = '.jpg'  # 默认
            
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
            temp_file.write(response.content)
            temp_file.close()
            file_path = temp_file.name
        else:
            # 直接使用文件路径
            file_path = image_source
        
        # 使用非流式方式调用AI分析
        result = await generate_with_autogen_non_streaming(file_path, context, requirements)
        return result
    
    except Exception as e:
        print(f"AI分析错误: {str(e)}")
        return {"title": "", "description": f"分析失败: {str(e)}"}
    
    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

async def generate_with_autogen_non_streaming(file_path: str, context: str, requirements: str) -> dict:
    """非流式AI分析实现"""
    cfg = _get_model_config()
    model_client = OpenAIChatCompletionClient(
        model=cfg['model'],
        api_key=cfg['api_key'],
        base_url=cfg['base_url'],
        http_client=_http_client,
        model_info={
            "vision": True,
            "function_calling": False,
            "json_output": False,
            "family": "qwen",
            "multiple_system_messages": True,
            "structured_output": False,
        }
    )

    pil_image = PILImage.open(file_path)
    ag_image = AGImage(pil_image)

    prompt = "分析图像，输出标题和描述信息"
    if context.strip():
        prompt += f"\n上下文：{context}"
    if requirements.strip():
        prompt += f"\n需求：{requirements}"

    user_message = AGMultiModalMessage(content=[prompt, ag_image], source="user")

    system_message = (
        "你是一位多模态交互界面设计专家。请为图像生成一个简洁突出功能的标题和一段不超过500字的描述。忽略背景图片。\n"
        "严格遵循这个格式输出{\"title\": \"\", \"description\": \"\"}，标题需简洁点明核心功能，描述聚焦功能本身，不提及技术实现或输入方式。"
    )

    agent = AssistantAgent(
        name="vl_agent",
        model_client=model_client,
        system_message=system_message,
        model_client_stream=False,  # 非流式
    )

    # 收集所有输出
    full_response = ""
    async for event in agent.run_stream(task=user_message):
        from autogen_agentchat.base import TaskResult
        
        if isinstance(event, TaskResult):
            # 获取最终结果
            if hasattr(event, 'messages') and event.messages:
                for message in event.messages:
                    if hasattr(message, 'content') and message.type == 'TextMessage':
                        full_response += str(message.content)
    
    # 解析JSON结果
    try:
        # 尝试直接解析JSON
        start_index = full_response.find('{')
        end_index = full_response.rfind('}') + 1
        if start_index != -1 and end_index > start_index:
            json_str = full_response[start_index:end_index]
            result = json.loads(json_str)
            # 确保返回结果格式正确
            return {
                "title": result.get("title", ""),
                "description": result.get("description", "")
            }
        else:
            # 如果没有找到JSON格式，尝试从响应中提取信息
            return {
                "title": full_response[:50] + "..." if len(full_response) > 50 else full_response,
                "description": full_response
            }
    except json.JSONDecodeError:
        # JSON解析失败，返回原始响应
        return {
            "title": full_response[:50] + "..." if len(full_response) > 50 else full_response,
            "description": full_response
        }

@qwen_vl_bp.route("/generate", methods=["POST"])
def generate():
    if "image" not in request.files:
        return jsonify({"error": "缺少图像文件"}), 400

    file = request.files["image"]
    context = request.form.get("context", "")
    requirements = request.form.get("requirements", "")

    if not allowed_file(file.filename):
        return jsonify({"error": "不支持的图像格式"}), 400

    filename = secure_filename(file.filename)
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    def sync_generator():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        agen = generate_with_autogen(temp_path, context, requirements)
        try:
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    return Response(sync_generator(), mimetype="text/event-stream")

@qwen_vl_bp.route("/generateAll", methods=["GET", "POST"])
def generate_all():
    """批量AI分析接口（流式输出）"""
    try:
        # 在请求上下文中获取project参数
        if request.method == "GET":
            # GET请求从URL参数获取
            project = request.args.get('project', 'default')
        else:
            # POST请求从JSON或form数据获取
            request_data = request.get_json() if request.is_json else request.form
            project = request_data.get('project', 'default')
        logger.info(project)
        
        DATA_DIR = current_app.config['DATA_DIR']
        project = os.path.join(DATA_DIR, project)

        # 构建基于project的文件路径
        records_file_path = f"{project}/records.json"

        if not os.path.exists(records_file_path):
            return jsonify({'error': f'{project}/records.json文件不存在'}), 400

        # 读取并验证数据格式
        with open(records_file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # 支持两种格式：直接数组或 {"slides": [...]}
            if isinstance(raw_data, list):
                records = raw_data
            elif isinstance(raw_data, dict) and 'slides' in raw_data:
                records = raw_data['slides']
            else:
                return jsonify({'error': f'{project}/records.json格式错误，应为数组或包含slides字段的对象'}), 400

        if not isinstance(records, list):
            return jsonify({'error': f'{project}/records.json格式错误，应为数组'}), 400

        # 构建基于project的目录路径
        screenshots_dir = f"{project}/my_screenshots"

        # 确保my_screenshots目录存在
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)

        def sync_generator():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 发送开始消息
                yield f"data: {json.dumps({'type': 'start', 'total': len(records), 'project': project}, ensure_ascii=False)}\n\n"
                
                success_count = 0
                error_count = 0
                
                for i, record in enumerate(records):
                    try:
                        # 发送进度消息
                        progress_message = f"正在处理第 {i + 1}/{len(records)} 个记录..."
                        message = json.dumps({
                            'type': 'progress', 
                            'current': i + 1, 
                            'total': len(records),
                            'status': 'processing',
                            'message': progress_message
                        }, ensure_ascii=False)
                        yield f"data: {message}\n\n"
                        
                        # 获取图片信息
                        image_url = record.get('image_url', '') or record.get('url', '')
                        if not image_url:
                            error_count += 1
                            message = json.dumps({
                                'type': 'item_complete',
                                'index': i,
                                'success': False,
                                'error': '缺少image_url字段'
                            }, ensure_ascii=False)
                            yield f"data: {message}\n\n"
                            continue
                        
                        # 从URL提取文件名
                        parsed_url = urllib.parse.urlparse(image_url)
                        original_filename = os.path.basename(parsed_url.path)
                        if not original_filename:
                            original_filename = f"image_{i}.jpg"
                        
                        # 查找或下载文件
                        local_file_path = os.path.join(screenshots_dir, original_filename)
                        

                        if not os.path.exists(local_file_path):
                            # 下载文件
                            try:
                                download_message = f"正在下载图片: {original_filename}"
                                message = json.dumps({
                                    'type': 'progress',
                                    'current': i + 1,
                                    'total': len(records),
                                    'status': 'downloading',
                                    'message': download_message
                                })
                                yield f"data: {message}\n\n"
                                
                                response = requests.get(image_url, timeout=30, verify=False)
                                response.raise_for_status()
                                
                                with open(local_file_path, 'wb') as f:
                                    f.write(response.content)
                            except Exception as e:
                                error_count += 1
                                message = json.dumps({
                                    'type': 'item_complete',
                                    'index': i,
                                    'success': False,
                                    'error': f'下载失败: {str(e)}'
                                })
                                yield f"data: {message}\n\n"
                                continue
                        
                        # 进行AI分析
                        context = record.get('context', '')
                        requirements = record.get('requirements', '')
                        
                        # 设置默认context和requirements
                        if not context:
                            context = f"这是第{i+1}个UI界面的截图"
                        if not requirements:
                            requirements = "请为这个UI界面生成简洁的标题和详细的功能描述"
                        
                        # 发送AI分析开始消息
                        analyze_message = f"正在进行AI分析: {original_filename}"
                        message = json.dumps({
                            'type': 'progress',
                            'current': i + 1,
                            'total': len(records),
                            'status': 'analyzing',
                            'message': analyze_message
                        }, ensure_ascii=False)
                        yield f"data: {message}\n\n"
                        
                        # 调用AI分析 - 参考generate函数的方式
                        analysis_result = loop.run_until_complete(ai_analysis(local_file_path, context, requirements))
                        
                        # 更新记录
                        record['ai_result'] = f"标题: {analysis_result.get('title', '')}\n\n描述: {analysis_result.get('description', '')}"
                        record['title'] = analysis_result.get('title', '')
                        record['remark'] = analysis_result.get('description', '')
                        
                        # 立即持久化到records.json
                        with open(records_file_path, 'w', encoding='utf-8') as f:
                            if isinstance(raw_data, dict):
                                json.dump(raw_data, f, ensure_ascii=False, indent=2)
                            else:
                                json.dump(records, f, ensure_ascii=False, indent=2)
                        
                        success_count += 1
                        
                        # 发送项目完成消息
                        title = analysis_result.get('title', '')
                        description = analysis_result.get('description', '')
                        desc_short = description[:100] + "..." if len(description) > 100 else description
                        
                        message = json.dumps({
                            'type': 'item_complete',
                            'index': i,
                            'success': True,
                            'data': record,
                            'description': desc_short,
                            'filename': original_filename
                        }, ensure_ascii=False)
                        yield f"data: {message}\n\n"
                        
                    except Exception as e:
                        error_count += 1
                        message = json.dumps({
                            'type': 'item_complete',
                            'index': i,
                            'success': False,
                            'error': f'处理失败: {str(e)}'
                        }, ensure_ascii=False)
                        yield f"data: {message}\n\n"
                
                # 发送完成消息
                complete_message = f"批量处理完成: 成功 {success_count} 个, 失败 {error_count} 个"
                message = json.dumps({
                    'type': 'complete',
                    'success_count': success_count,
                    'error_count': error_count,
                    'total': len(records),
                    'message': complete_message,
                    'project': project,
                    'records_file': f'{project}/records.json',
                    'screenshots_dir': f'{project}/my_screenshots'
                }, ensure_ascii=False)
                yield f"data: {message}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'批量处理失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            finally:
                loop.close()

        return Response(sync_generator(), mimetype="text/event-stream")
    except Exception as e:
        logger.error(f"generate_all函数错误: {str(e)}")
        return jsonify({'error': f'请求处理失败: {str(e)}'}), 500