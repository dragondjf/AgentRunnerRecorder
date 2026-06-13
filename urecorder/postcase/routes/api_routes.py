"""PostCase 前端兼容路由

提供 /api 前缀的路由，用于前端兼容
"""
from flask import jsonify, request, Response
from .. import postcase_api_bp
from .test_cases import generate_test_cases, export_test_cases, download_excel


# 启动参数
STARTUP_PARAMETERS = {
    "context": "用户登录功能，包含用户名密码登录",
    "testCase": "需要生成包含正向测试、异常测试、边界测试的完整测试用例，重点关注安全性和用户体验。测试用例应该覆盖各种登录场景，包括正常登录、密码错误、账号不存在、网络异常等情况。",
    "url": "",
    "requirements": "需要生成包含正向测试、异常测试、边界测试的完整测试用例，重点关注安全性和用户体验。测试用例应该覆盖各种登录场景，包括正常登录、密码错误、账号不存在、网络异常等情况。"
}


@postcase_api_bp.route('/ping', methods=['GET'])
def api_ping():
    """健康检查 - 前端兼容路径"""
    return {'status': 'success', 'message': 'pong'}


@postcase_api_bp.route('/startup-parameters', methods=['GET'])
def api_startup_parameters():
    """获取启动参数 - 前端兼容路径"""
    return {
        'status': 'success',
        'data': STARTUP_PARAMETERS
    }


@postcase_api_bp.route('/test-cases/generate', methods=['POST'])
def api_generate_test_cases():
    """生成测试用例 - 前端兼容路径

    代理到 v1 蓝图中的实际处理函数
    """
    return generate_test_cases()


@postcase_api_bp.route('/test-cases/export', methods=['POST'])
def api_export_test_cases():
    """导出测试用例到 Excel - 前端兼容路径

    代理到 v1 蓝图中的实际处理函数
    """
    return export_test_cases()


@postcase_api_bp.route('/test-cases/download/<filename>', methods=['GET'])
def api_download_excel(filename):
    """下载 Excel 文件 - 前端兼容路径

    代理到 v1 蓝图中的实际处理函数
    """
    return download_excel(filename)

