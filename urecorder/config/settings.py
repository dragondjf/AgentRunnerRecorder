"""配置管理模块"""
import os
from pathlib import Path
from typing import Optional, Dict, List

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field


def _resolve_skills_dirs(skills_dir: str) -> List[str]:
    """解析 skills_dir 路径，支持多个路径（逗号分隔）
    
    - 支持逗号分隔的多个路径
    - 如果是绝对路径，直接返回
    - 如果是相对路径，相对于 .env 文件所在目录（即 src 目录）
    - 内置 skills 目录始终包含
    
    Returns:
        List[str]: 解析后的路径列表（内置目录 + 外部配置目录）
    """
    from loguru import logger
    
    # 内置 skills 目录（最高优先级）
    base_dir = Path(__file__).parent.parent  # agentrunner 目录
    builtin_dir = base_dir / "skills"
    
    logger.debug(f"_resolve_skills_dirs: base_dir={base_dir}, builtin_dir={builtin_dir}, exists={builtin_dir.exists()}")
    
    result = []
    
    # 内置目录始终包含（如果不存在，后续会处理）
    if builtin_dir.exists():
        result.append(str(builtin_dir.resolve()))
        logger.info(f"添加内置 skills 目录: {builtin_dir.resolve()}")
    else:
        logger.warning(f"内置 skills 目录不存在: {builtin_dir}")
    
    # 解析配置的目录
    if skills_dir:
        for path_str in skills_dir.split(","):
            path_str = path_str.strip()
            if not path_str:
                continue
                
            path = Path(path_str)
            if path.is_absolute():
                result.append(str(path))
                logger.info(f"添加外部 skills 目录(绝对路径): {path}")
            else:
                # 相对于 src 目录
                src_dir = base_dir.parent
                resolved = src_dir / path
                if resolved.exists():
                    result.append(str(resolved.resolve()))
                    logger.info(f"添加外部 skills 目录(相对路径): {resolved.resolve()}")
                else:
                    logger.warning(f"外部 skills 目录不存在: {resolved}")
    
    logger.info(f"最终 skills_dirs: {result}")
    return result


class LLMConfig(BaseModel):
    """大模型配置"""
    api_base: str = Field(default="https://api.openai.com/v1")
    api_key: Optional[str] = None
    model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0)
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None


class AgentConfig(BaseModel):
    """Agent 核心配置"""
    max_iterations: int = Field(default=1000)
    skills_dirs: List[str] = Field(default_factory=list)  # 支持多个 skill 目录
    verbose: bool = Field(default=True)


class Config(BaseModel):
    """完整配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """从环境变量加载配置

        Args:
            env_file: .env 文件路径，如果为 None 则自动查找
        """
        # 加载 .env 文件
        if env_file:
            load_dotenv(env_file)
        else:
            # 尝试从多个位置查找 .env 文件
            import pathlib
            script_dir = pathlib.Path(__file__).parent.parent.parent  # agentrunner 目录
            env_paths = [
                script_dir / ".env",
                script_dir.parent / ".env",
                pathlib.Path.cwd() / ".env",
            ]
            for env_path in env_paths:
                if env_path.exists():
                    load_dotenv(env_path)
                    break

        return cls(
            llm=LLMConfig(
                api_base=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
                temperature=float(os.getenv("TEMPERATURE", "0")),
            ),
            agent=AgentConfig(
                max_iterations=int(os.getenv("MAX_ITERATIONS", "1000")),
                skills_dirs=_resolve_skills_dirs(os.getenv("SKILLS_DIR", "")),
                verbose=os.getenv("VERBOSE", "true").lower() == "true",
            ),
        )


# ============ 预设配置 ============

class ModelPresets:
    """模型预设配置"""
    
    # OpenAI 官方
    OPENAI = {
        "api_base": "https://api.openai.com/v1",
        "models": {
            "gpt-4o-mini": {"type": "text", "vision": False},
            "gpt-4o": {"type": "text", "vision": True},
            "gpt-4-turbo": {"type": "text", "vision": True},
            "gpt-4": {"type": "text", "vision": False},
            "gpt-3.5-turbo": {"type": "text", "vision": False},
        }
    }
    
    # 阿里云通义千问 (DashScope)
    QWEN = {
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {
            "qwen-turbo": {"type": "text", "vision": False},
            "qwen-plus": {"type": "text", "vision": False},
            "qwen-max": {"type": "text", "vision": False},
            "qwen-max-longcontext": {"type": "text", "vision": False},
            "qwen-vl-plus": {"type": "multimodal", "vision": True},
            "qwen-vl-max": {"type": "multimodal", "vision": True},
            "qwen2.5-vl-72b-instruct": {"type": "multimodal", "vision": True},
            "qwen2.5-coder-32b-instruct": {"type": "code", "vision": False},
        }
    }
    
    # DeepSeek
    DEEPSEEK = {
        "api_base": "https://api.deepseek.com/v1",
        "models": {
            "deepseek-chat": {"type": "text", "vision": False},
            "deepseek-coder": {"type": "code", "vision": False},
            "deepseek-prover": {"type": "text", "vision": False},
        }
    }
    
    # 硅基流动 (SiliconFlow) - 兼容多模型
    SILICONFLOW = {
        "api_base": "https://api.siliconflow.cn/v1",
        "models": {
            "Qwen/Qwen2-VL-72B-Instruct": {"type": "multimodal", "vision": True},
            "Qwen/Qwen2.5-72B-Instruct": {"type": "text", "vision": False},
            "deepseek-ai/DeepSeek-V2-Chat": {"type": "text", "vision": False},
            "THUDG/glm-4v-flash": {"type": "multimodal", "vision": True},
        }
    }
    
    # Kimi (月之暗面)
    KIMI = {
        "api_base": "https://api.moonshot.cn/v1",
        "models": {
            "kimi-flash": {"type": "text", "vision": False},
            "kimi-flash-8k": {"type": "text", "vision": False},
            "kimi-long": {"type": "text", "vision": False},
        }
    }
    
    # 智谱清言
    ZHIPU = {
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "models": {
            "glm-4": {"type": "text", "vision": False},
            "glm-4-flash": {"type": "text", "vision": False},
            "glm-4v-flash": {"type": "multimodal", "vision": True},
            "glm-4v-plus": {"type": "multimodal", "vision": True},
        }
    }
    
    @classmethod
    def get_provider(cls, api_base: str) -> Optional[str]:
        """根据 API base URL 判断供应商"""
        base_lower = api_base.lower()
        
        if "dashscope" in base_lower or "aliyuncs" in base_lower:
            return "qwen"
        elif "deepseek" in base_lower:
            return "deepseek"
        elif "siliconflow" in base_lower:
            return "siliconflow"
        elif "moonshot" in base_lower:
            return "kimi"
        elif "bigmodel" in base_lower:
            return "zhipu"
        elif "openai" in base_lower:
            return "openai"
        
        return None
    
    @classmethod
    def get_model_info(cls, api_base: str, model: str) -> Dict:
        """获取模型信息"""
        provider = cls.get_provider(api_base)
        
        if provider:
            preset = getattr(cls, provider.upper(), {})
            return preset.get("models", {}).get(model, {"type": "unknown", "vision": False})
        
        return {"type": "unknown", "vision": False}
    
    @classmethod
    def supports_vision(cls, api_base: str, model: str) -> bool:
        """检查模型是否支持视觉"""
        info = cls.get_model_info(api_base, model)
        return info.get("vision", False)


# 全局配置实例
config = Config.from_env()
