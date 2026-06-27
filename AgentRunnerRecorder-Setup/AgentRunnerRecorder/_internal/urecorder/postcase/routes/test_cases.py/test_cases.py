"""PostCase 测试用例 API 路由"""
import os
import uuid
from flask import Blueprint, request, jsonify, Response, send_file, current_app
from typing import List, Dict, Any, Union
import json

# 导入服务
from ..services.ai_service import ai_service
from ..services.excel_service import excel_service
from .. import postcase_bp

# 配置上传目录
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
RESULTS_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)


@postcase_bp.route('/generate', methods=['POST'])
def generate_test_cases():
    """
    从上传的文件、上下文和需求生成测试用例

    参数 (表单数据):
        file: 上传的文件（图像、PDF 或 OpenAPI 文档）
        context: 测试用例生成的上下文信息
        requirements: 测试用例生成的需求

    返回:
        流式响应的 Markdown 格式测试用例
    """
    # 检查是否有文件
    if 'file' not in request.files:
        return jsonify({'error': '没有文件上传'}), 400

    file = request.files.get('file')
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    # 获取表单参数
    context = request.form.get('context', '')
    requirements = request.form.get('requirements', '')

    # 保存上传的文件
    file_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1].lower()
    file_path = os.path.join(UPLOAD_FOLDER, f"{file_id}{file_extension}")

    file.save(file_path)

    # 检查文件类型是否支持
    supported_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.pdf', '.json', '.yaml', '.yml']
    if file_extension not in supported_extensions:
        # 清理临时文件
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({
            'error': f'不支持的文件类型: {file_extension}. 支持的类型: {", ".join(supported_extensions)}'
        }), 400

    def generate_stream():
        """流式生成测试用例"""
        try:
            for chunk in ai_service.generate_test_cases_stream(file_path, context, requirements):
                yield chunk
        except Exception as e:
            yield f"\n\n**错误**: {str(e)}\n"
        finally:
            # 清理临时文件
            if os.path.exists(file_path):
                os.remove(file_path)

    return Response(generate_stream(), mimetype='text/plain; charset=utf-8')


@postcase_bp.route('/generate-mindmap', methods=['POST'])
def generate_mindmap():
    """
    从测试用例生成思维导图数据

    参数 (JSON):
        test_cases: 测试用例列表

    返回:
        思维导图的 JSON 数据
    """
    data = request.get_json()
    if not data or 'test_cases' not in data:
        return jsonify({'error': '缺少 test_cases 参数'}), 400

    try:
        mindmap_data = ai_service.generate_mindmap_from_test_cases(data['test_cases'])
        return jsonify({'mindmap': mindmap_data})
    except Exception as e:
        return jsonify({'error': f'生成思维导图失败: {str(e)}'}), 500


@postcase_bp.route('/export', methods=['POST'])
def export_test_cases():
    """
    将测试用例导出到 Excel

    参数 (JSON):
        test_cases: 要导出的测试用例列表
        或者直接传测试用例数组: [测试用例1, 测试用例2, ...]

    返回:
        Excel 文件下载
    """
    # 记录调试信息
    from loguru import logger
    logger.info(f"Export request received. Content-Type: {request.content_type}")
    logger.info(f"Request data: {request.data[:200]}...")  # 只记录前200字符
    logger.info(f"Request form: {request.form}")

    try:
        data = request.get_json()
        logger.info(f"Parsed JSON data type: {type(data)}")

        # 兼容两种数据格式:
        # 1. { test_cases: [...] }
        # 2. 直接是数组 [...]
        if isinstance(data, list):
            # 格式2: 直接是数组
            test_cases = data
            logger.info(f"Received direct array format with {len(test_cases)} test cases")
        elif isinstance(data, dict):
            # 格式1: 包含 test_cases 键
            if 'test_cases' in data:
                test_cases = data['test_cases']
                logger.info(f"Received object format with {len(test_cases)} test cases")
            else:
                logger.warning(f"Missing test_cases parameter. Data keys: {data.keys()}")
                return jsonify({'error': '缺少 test_cases 参数'}), 400
        else:
            logger.error(f"Invalid data format: {type(data)}")
            return jsonify({'error': '无效的数据格式'}), 400

        # 验证测试用例不为空
        if not test_cases:
            logger.warning("Empty test cases array")
            return jsonify({'error': '测试用例列表为空'}), 400

    except Exception as e:
        logger.error(f"Failed to parse JSON: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'JSON解析失败: {str(e)}'}), 400

    try:
        # 更新 Excel 服务的结果目录
        excel_service.results_dir = RESULTS_FOLDER

        # 生成 Excel 文件
        logger.info(f"Generating Excel for {len(test_cases)} test cases...")
        excel_path = excel_service.generate_excel(test_cases)
        logger.info(f"Excel file generated: {excel_path}")

        # 返回文件供下载
        return send_file(
            excel_path,
            as_attachment=True,
            download_name=os.path.basename(excel_path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        import traceback
        logger.error(f"Export failed: {str(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return jsonify({'error': f'导出失败: {str(e)}'}), 500


@postcase_bp.route('/download/<filename>', methods=['GET'])
def download_excel(filename: str):
    """
    下载生成的 Excel 文件

    参数:
        filename: 要下载的 Excel 文件名

    返回:
        供下载的 Excel 文件
    """
    file_path = os.path.join(RESULTS_FOLDER, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@postcase_bp.route('/api/ping', methods=['GET'])
def api_ping():
    """健康检查 - v1 蓝图中的路由"""
    return jsonify({'status': 'success', 'message': 'pong'})


@postcase_bp.route('/ping', methods=['GET'])
def ping():
    """健康检查"""
    return jsonify({'status': 'success', 'message': 'pong'})


# 启动参数（示例）
STARTUP_PARAMETERS = {
    "context": "用户登录功能，包含用户名密码登录",
    "testCase": "需要生成包含正向测试、异常测试、边界测试的完整测试用例，重点关注安全性和用户体验。测试用例应该覆盖各种登录场景，包括正常登录、密码错误、账号不存在、网络异常等情况。",
    "url": ""
}


@postcase_bp.route('/startup-parameters', methods=['GET'])
def get_startup_parameters():
    """获取启动参数"""
    return jsonify({
        'status': 'success',
        'data': STARTUP_PARAMETERS
    })
