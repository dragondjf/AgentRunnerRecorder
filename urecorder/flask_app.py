#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API服务器 - UIRecorder主应用
简洁的Flask应用入口，所有API路由已迁移到api_blueprint.py
"""

from flask import Flask, request, jsonify, send_from_directory
try:
    from flask_cors import CORS
except ImportError:
    CORS = None
import os
import json
from pathlib import Path
import sys
import threading
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger("urecorder")
    logger.setLevel(logging.INFO)
    logger.info = logger.info

# 设置默认日志等级为 WARNING
logger.remove()  # 关键！清除默认 DEBUG 输出
logger.add(sys.stderr, level="WARNING")


def load_application_config():
    """加载应用程序配置"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'application.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"✅ 成功加载配置文件: {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"⚠️ 配置文件不存在: {config_path}，使用默认配置")
        return get_default_config()
    except json.JSONDecodeError as e:
        logger.error(f"❌ 配置文件格式错误: {e}，使用默认配置")
        return get_default_config()


def get_default_config():
    """获取默认配置"""
    return {
        "server": {
            "flask": {
                "host": "0.0.0.0",
                "port": 12000,
                "debug": True
            },
            "static_file_server": {
                "host": "0.0.0.0",
                "port": 12001
            },
            "ai": {
                "host": "127.0.0.1",
                "port": 12000
            }
        },
        "paths": {
            "data_dir": "./filestorage",
            "static_dir": "./static",
            "exports_dir": "./data/exports"
        },
        "features": {
            "enable_cors": True,
            "enable_logging": True
        }
    }


# 加载应用程序配置
APP_CONFIG = load_application_config()

# 从配置中获取服务器设置
FLASK_HOST = APP_CONFIG['server']['flask']['host']
FLASK_PORT = APP_CONFIG['server']['flask']['port']
FLASK_DEBUG = APP_CONFIG['server']['flask']['debug']

STATIC_FILE_HOST = APP_CONFIG['server']['static_file_server']['host']
STATIC_FILE_PORT = APP_CONFIG['server']['static_file_server']['port']

AI_Server_HOST = APP_CONFIG['server']['ai']['host']
AI_Server_PORT = APP_CONFIG['server']['ai']['port']


# 初始化Flask应用
app = Flask(__name__, static_folder='static', static_url_path='/static')

# 注册API蓝图
from view.api_blueprint import api_blueprint
app.register_blueprint(api_blueprint, url_prefix='/api/v1')

# 注册Qwen VL蓝图
try:
    from view import qwen_vl_bp
    app.register_blueprint(qwen_vl_bp, url_prefix='/api/v1/vl')
    logger.info("✅ 成功加载view模块和qwen_vl_bp蓝图")
except ImportError as e:
    logger.warning(f"⚠️ 导入view模块失败: {e}")


# 根据配置启用CORS
if APP_CONFIG.get('features', {}).get('enable_cors', True) and CORS is not None:
    CORS(app)

# 配置JSON响应支持中文显示
app.config['JSON_AS_ASCII'] = False

# 数据文件存储目录
DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__)), "filestorage")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
app.config['DATA_DIR'] = str(DATA_DIR)

# 配置应用全局变量
app.config['FLASK_HOST'] = FLASK_HOST
app.config['FLASK_PORT'] = FLASK_PORT
app.config['STATIC_FILE_HOST'] = STATIC_FILE_HOST
app.config['STATIC_FILE_PORT'] = STATIC_FILE_PORT
app.config['AI_SERVER_HOST'] = AI_Server_HOST
app.config['AI_SERVER_PORT'] = AI_Server_PORT

# 监控器相关配置
app.config['MONITOR_INSTANCE'] = None
app.config['MONITOR_THREAD'] = None
app.config['MONITOR_LOCK'] = threading.Lock()
app.config['CURRENT_PROJECT_NAME'] = None


# 添加项目路径以导入core模块
sys.path.insert(0, str(Path(__file__).parent))


# ============================================================================
# 基础路由
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """主页面 - 提供前端界面访问"""
    return send_from_directory(app.static_folder, 'index.html')


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': '接口不存在',
        'timestamp': None
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误',
        'timestamp': None
    }), 500


# ============================================================================
# 打印服务器信息
# ============================================================================

def print_server_info():
    """打印服务器信息"""
    logger.info("🚀 启动系统监控平台...")
    logger.info(f"📁 数据目录: {DATA_DIR}")
    logger.info("🌐 访问地址:")
    logger.info(f"  Flask API服务器: http://{FLASK_HOST}:{FLASK_PORT}")
    logger.info(f"  静态文件服务器: http://{STATIC_FILE_HOST}:{STATIC_FILE_PORT}")
    logger.info(f"  AI服务器: http://{AI_Server_HOST}:{AI_Server_PORT}")
    logger.info(f"  前端界面: http://{FLASK_HOST}:{FLASK_PORT}/static/index.html")
    logger.info("📡 API端点:")
    logger.info("  GET  /api/v1/uirecoreder?filename=records.json - 读取JSON数据")
    logger.info("  POST /api/v1/uirecoreder?filename=records.json - 保存JSON数据")
    logger.info("  GET  /api/v1/config - 读取配置文件")
    logger.info("  POST /api/v1/config - 保存配置文件")
    logger.info("  GET  /api/v1/loadproject?project=mydata - 加载项目设置")
    logger.info("  GET  /api/v1/start?project=mydata - 启动系统监控")
    logger.info("  GET  /api/v1/stop - 停止系统监控")
    logger.info("  GET  /api/v1/status - 获取监控状态")
    logger.info("  GET  /api/v1/export?type={format} - 导出数据")
    logger.info("  GET  /api/v1/export/formats - 获取支持的导出格式")
    logger.info("  GET  /api/v1/webocr?url={image_url} - WebOCR图像识别")
    logger.info("  POST /api/v1/webrecoreder - WebRecorder数据导入")
    logger.info("  GET  /api/v1/health - 健康检查")
    logger.info("=" * 60)


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == '__main__':
    # 打印服务器信息
    print_server_info()

    # 自动打开浏览器
    import webbrowser
    webbrowser.open(f'http://{FLASK_HOST}:{FLASK_PORT}/static/index.html?project=mydata')
    
    # 启动Flask应用
    logger.info(f"🔧 启动Flask API服务器...")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
