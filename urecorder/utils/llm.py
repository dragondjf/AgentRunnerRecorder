"""大模型调用封装 - 支持多模态"""
import base64
import json
import requests
import time
from typing import Optional, Callable, List, Dict, Any, Union
from pathlib import Path
from requests.exceptions import ReadTimeout, RequestException

from ..config.settings import LLMConfig
from loguru import logger




class LLMClient:
    """大模型客户端"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._validate_config()
    
    def _validate_config(self):
        """验证配置有效性"""
        if not self.config.api_key:
            raise ValueError("请设置 OPENAI_API_KEY 环境变量")
    
    def call(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """调用大模型 API

        Args:
            messages: 消息列表，支持多模态内容
                格式: [{"role": "user", "content": [
                    {"type": "text", "text": "描述"},
                    {"type": "image_url", "image_url": {"url": "https://..."}}
                ]}]
            temperature: 温度参数
            stream_callback: 流式回调函数

        Returns:
            模型响应文本
        """
        url = f"{self.config.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
        }

        # 打印实际使用的模型配置
        logger.info(f"[LLM Request] model={self.config.model}, api_base={self.config.api_base}, temperature={temperature or self.config.temperature}, top_p={self.config.top_p}, frequency_penalty={self.config.frequency_penalty}, presence_penalty={self.config.presence_penalty}, max_tokens={self.config.max_tokens}")

        if self.config.max_tokens:
            payload["max_tokens"] = self.config.max_tokens

        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p

        if self.config.frequency_penalty is not None:
            payload["frequency_penalty"] = self.config.frequency_penalty

        if self.config.presence_penalty is not None:
            payload["presence_penalty"] = self.config.presence_penalty

        if stream_callback:
            payload["stream"] = True
            return self._stream_call(url, headers, payload, stream_callback)

        # 非流式调用也添加重试
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=120)
                response.raise_for_status()
                resp_json = response.json()
                # 保存 usage 到实例属性，供回调使用
                self._last_usage = resp_json.get("usage")
                return resp_json["choices"][0]["message"]["content"]
            except (ReadTimeout, RequestException) as e:
                logger.warning(f"LLM 非流式调用超时/网络错误 (尝试 {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise

        return ""

    @property
    def last_usage(self) -> Optional[dict]:
        """获取最后一次调用的 usage 信息"""
        return getattr(self, "_last_usage", None)
    
    def _stream_call(
        self,
        url: str,
        headers: dict,
        payload: dict,
        callback: Callable[[str], None],
        max_retries: int = 2,
        timeout: int = 120,
    ):
        """流式调用（带超时和重试）

        Args:
            max_retries: 最大重试次数
            timeout: 单次请求超时时间（秒）
        """
        payload["stream"] = True

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"LLM 流式调用尝试 {attempt + 1}/{max_retries + 1}")
                return self._do_stream(url, headers, payload, callback, timeout)
            except ReadTimeout as e:
                last_error = e
                logger.warning(f"LLM 调用超时 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(1)  # 短暂等待后重试
                continue
            except RequestException as e:
                last_error = e
                logger.warning(f"LLM 调用网络错误 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(2)
                continue

        # 所有重试都失败
        raise last_error or RuntimeError("LLM 调用失败")

    def _do_stream(
        self,
        url: str,
        headers: dict,
        payload: dict,
        callback: Callable[[str], None],
        timeout: int = 120,
    ):
        """执行实际的流式调用"""
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=timeout)
        response.raise_for_status()

        result = ""
        self._last_usage = None  # 重置，确保不残留上次数据
        # 记录发送的消息总长度，用于估算 prompt tokens
        messages_text = ""
        for msg in payload.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, str):
                messages_text += content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        messages_text += part.get("text", "")
        estimated_prompt_chars = len(messages_text)
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        # 提取 usage（OpenAI 兼容 API 在最后一个 chunk 中返回）
                        if "usage" in chunk and chunk["usage"]:
                            self._last_usage = chunk["usage"]
                        # 提取 delta content（防御性处理：某些 API 可能返回空 choices 列表）
                        choices = chunk.get("choices") or []
                        if not choices:
                            logger.debug(f"流式 chunk 无 choices 字段或为空: {data}")
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            result += content
                            callback(content)
                        # 检测 finish_reason（某些 API 不发送 [DONE]）
                        finish_reason = choices[0].get("finish_reason")
                        if finish_reason and finish_reason != "null":
                            break
                    except json.JSONDecodeError as e:
                        logger.warning(f"无法解析流式响应: {data}, 错误: {e}")
                    except Exception as e:
                        logger.warning(f"处理流式响应时出错: {e}")

        # 降级：当 API 未返回 usage 时，用字符数近似估算（约 4 字符/token）
        if not self._last_usage and result:
            approx_prompt = estimated_prompt_chars // 4
            approx_completion = len(result) // 4
            self._last_usage = {
                "prompt_tokens": approx_prompt,
                "completion_tokens": approx_completion,
                "total_tokens": approx_prompt + approx_completion,
            }
            logger.info(f"[LLM] usage 未返回，使用估算值: prompt≈{approx_prompt}, completion≈{approx_completion}")

        logger.debug(f"流式调用完成，总长度: {len(result)}, usage: {self._last_usage}")
        return result


def call_llm(messages: List[Dict[str, Any]], config: Optional[LLMConfig] = None) -> str:
    """便捷的 LLM 调用函数"""
    from config.settings import config as global_config
    cfg = config or global_config.llm
    client = LLMClient(cfg)
    return client.call(messages)


# ============ 多模态消息构建工具 ============

def text_message(content: str) -> Dict[str, str]:
    """创建文本消息"""
    return {"type": "text", "text": content}


def image_url_message(url: str, detail: str = "high") -> Dict[str, Any]:
    """创建图像URL消息
    
    Args:
        url: 图像URL或base64数据
        detail: 详细程度 "low", "high", "auto"
    """
    # 如果是本地文件路径，转换为 base64
    if url.startswith("file://") or Path(url).exists():
        image_path = url.replace("file://", "")
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{encode_image_base64(image_path)}",
                "detail": detail
            }
        }
    
    return {
        "type": "image_url",
        "image_url": {
            "url": url,
            "detail": detail
        }
    }


def encode_image_base64(image_path: str) -> str:
    """将图像文件编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_multimodal_message(
    text: str, 
    images: Optional[List[str]] = None,
    role: str = "user"
) -> Dict[str, Any]:
    """构建多模态消息
    
    Args:
        text: 文本内容
        images: 图像URL或本地路径列表
        role: 消息角色
    
    Returns:
        符合 OpenAI API 格式的消息
    """
    content = []
    
    # 添加文本
    if text:
        content.append(text_message(text))
    
    # 添加图像
    if images:
        for img in images:
            content.append(image_url_message(img))
    
    return {"role": role, "content": content}


def build_user_message(
    text: str, 
    images: Optional[List[str]] = None
) -> Dict[str, Any]:
    """构建用户消息（便捷函数）"""
    return build_multimodal_message(text, images, "user")
