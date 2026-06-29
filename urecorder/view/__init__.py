try:
    from .qwen_vl_service import qwen_vl_bp
except ImportError:
    qwen_vl_bp = None  # 依赖未安装（autogen_agentchat 等），蓝图不可用
