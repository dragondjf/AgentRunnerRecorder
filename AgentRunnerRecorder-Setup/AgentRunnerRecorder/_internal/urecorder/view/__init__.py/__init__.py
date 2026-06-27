try:
    from .qwen_vl_service import qwen_vl_bp
except ImportError:
    # 不设置 qwen_vl_bp，让 flask_app.py 的 from view import qwen_vl_bp 抛出 ImportError
    pass
