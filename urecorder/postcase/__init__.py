"""PostCase 测试用例生成蓝图

提供测试用例生成、导出、思维导图等功能
"""
from flask import Blueprint

# PostCase API 蓝图 (v1 前缀)
postcase_bp = Blueprint('postcase', __name__, static_folder='static', static_url_path='/static/postcase')

# PostCase 前端兼容蓝图 (api 前缀)
postcase_api_bp = Blueprint('postcase_api_v2', __name__, url_prefix='/api')

# 导入路由以注册到蓝图
from . import routes
