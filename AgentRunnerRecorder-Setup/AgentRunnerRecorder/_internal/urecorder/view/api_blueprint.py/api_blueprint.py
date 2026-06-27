#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UIRecorder API Blueprint
所有API路由的集中管理
"""

from flask import Blueprint, request, jsonify, send_from_directory
from datetime import datetime
import os
import json
import re
import sys
from pathlib import Path
from loguru import logger

from ..core.uiexporter import export_data as uiexporter_export

# 创建蓝图
api_blueprint = Blueprint('uirecorder_api', __name__)


def number_to_chinese_step(number):
    """将数字转换为中文步骤格式"""
    chinese_numbers = {
        1: "第一步", 2: "第二步", 3: "第三步", 4: "第四步", 5: "第五步",
        6: "第六步", 7: "第七步", 8: "第八步", 9: "第九步", 10: "第十步",
        11: "第十一步", 12: "第十二步", 13: "第十三步", 14: "第十四步", 15: "第十五步",
        16: "第十六步", 17: "第十七步", 18: "第十八步", 19: "第十九步", 20: "第二十步"
    }
    return chinese_numbers.get(number, f"第{number}步")


def validate_filename(filename):
    """验证文件名安全性"""
    if not filename:
        return False, "文件名不能为空"
    
    # 检查是否包含危险字符
    if re.search(r'[<>:"|?*]', filename):
        return False, "文件名包含非法字符"
    
    # 防止路径遍历攻击
    if '..' in filename or filename.startswith('/'):
        return False, "非法文件路径"
    
    return True, "验证通过"


@api_blueprint.route('/file', methods=['GET'])
def serve_file():
    """提供文件访问接口 - 用于访问项目下的截图等文件"""
    from flask import current_app
    
    # 获取相对路径参数
    file_path = request.args.get('path', '')
    
    if not file_path:
        return jsonify({
            'success': False,
            'error': '缺少路径参数',
            'timestamp': datetime.now().isoformat()
        }), 400
    
    # 验证路径安全性
    if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
        return jsonify({
            'success': False,
            'error': '非法文件路径',
            'timestamp': datetime.now().isoformat()
        }), 400
    
    # 获取数据目录
    DATA_DIR = current_app.config.get('DATA_DIR', '')
    full_path = os.path.join(DATA_DIR, file_path)
    
    # 规范化路径并确保在数据目录内
    try:
        full_path = os.path.abspath(full_path)
        data_dir_abs = os.path.abspath(DATA_DIR)
        
        if not full_path.startswith(data_dir_abs):
            return jsonify({
                'success': False,
                'error': '访问被拒绝: 文件不在允许的目录内',
                'timestamp': datetime.now().isoformat()
            }), 403
    except Exception as e:
        logger.error(f"路径验证失败: {e}")
        return jsonify({
            'success': False,
            'error': '路径验证失败',
            'timestamp': datetime.now().isoformat()
        }), 400
    
    # 检查文件是否存在
    if not os.path.exists(full_path):
        return jsonify({
            'success': False,
            'error': f'文件不存在: {file_path}',
            'timestamp': datetime.now().isoformat()
        }), 404
    
    # 检查是否为文件
    if not os.path.isfile(full_path):
        return jsonify({
            'success': False,
            'error': '请求的不是文件',
            'timestamp': datetime.now().isoformat()
        }), 400
    
    # 发送文件
    try:
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        return send_from_directory(directory, filename)
    except Exception as e:
        logger.error(f"发送文件失败: {e}")
        return jsonify({
            'success': False,
            'error': f'发送文件失败: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# 数据记录相关接口
# ============================================================================

@api_blueprint.route('/uirecoreder', methods=['GET', 'POST'])
def handle_uirecoreder():
    """处理UI记录器的GET和POST请求"""
    filename = request.args.get('filename', 'records.json')
    
    # 验证文件名
    is_valid, error_msg = validate_filename(filename)
    if not is_valid:
        logger.error(f"文件名验证失败: {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg,
            'timestamp': datetime.now().isoformat()
        }), 400
    
    # 获取数据目录
    from flask import current_app
    DATA_DIR = current_app.config['DATA_DIR']
    current_project_name = current_app.config.get('CURRENT_PROJECT_NAME', None)
    
    file_path = os.path.join(DATA_DIR, current_project_name or '', filename) if current_project_name else os.path.join(DATA_DIR, filename)
    
    if request.method == 'GET':
        return _handle_get_request(file_path, filename)
    elif request.method == 'POST':
        return _handle_post_request(file_path, filename)


def _handle_get_request(file_path, filename):
    """处理GET请求 - 读取JSON文件"""
    try:
        if not os.path.exists(file_path):
            logger.info(f"文件不存在，创建默认文件: {filename}")
            # 创建默认的JSON结构
            default_data = {
                "slides": [],
                "lastUpdated": datetime.now().isoformat(),
                "version": "1.0"
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查是否有id参数
        slide_id = request.args.get('id')
        if slide_id is not None:
            try:
                slide_index = int(slide_id)
                slides = data.get('slides', [])
                
                if slide_index < 0 or slide_index >= len(slides):
                    logger.warning(f"请求的slide索引 {slide_index} 超出范围 (0-{len(slides)-1})")
                    return jsonify({
                        'success': False,
                        'error': f'slide索引 {slide_index} 超出范围，可用的索引范围: 0-{len(slides)-1}',
                        'available_slides': len(slides),
                        'filename': filename,
                        'timestamp': datetime.now().isoformat()
                    }), 400
                
                # 返回指定的slide
                selected_slide = slides[slide_index]
                logger.info(f"成功读取slide #{slide_index} 从文件: {filename}")
                return jsonify({
                    'success': True,
                    'data': selected_slide,
                    'slide_index': slide_index,
                    'filename': filename,
                    'timestamp': datetime.now().isoformat()
                })
                
            except ValueError:
                logger.warning(f"无效的slide id参数: {slide_id}")
                return jsonify({
                    'success': False,
                    'error': 'id参数必须是整数',
                    'filename': filename,
                    'timestamp': datetime.now().isoformat()
                }), 400
        
        # 没有id参数，返回完整数据
        logger.info(f"成功读取文件: {filename}")
        return jsonify({
            'success': True,
            'data': data,
            'filename': filename,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"读取文件失败 {filename}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"读取文件失败: {str(e)}",
            'filename': filename,
            'timestamp': datetime.now().isoformat()
        }), 500


def _handle_post_request(file_path, filename):
    """处理POST请求 - 保存JSON数据"""
    try:
        # 获取请求数据
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': '请求必须是JSON格式',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        request_data = request.get_json()
        
        # 验证数据格式
        if 'slides' not in request_data:
            return jsonify({
                'success': False,
                'error': '缺少slides字段',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        if not isinstance(request_data['slides'], list):
            return jsonify({
                'success': False,
                'error': 'slides必须是数组格式',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 添加时间戳和版本信息
        request_data['lastUpdated'] = datetime.now().isoformat()
        if 'version' not in request_data:
            request_data['version'] = "1.0"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(request_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功保存文件: {filename}")
        return jsonify({
            'success': True,
            'message': f'数据已成功保存到 {filename}',
            'filename': filename,
            'slideCount': len(request_data['slides']),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"保存文件失败 {filename}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"保存文件失败: {str(e)}",
            'filename': filename,
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# 配置管理接口
# ============================================================================

@api_blueprint.route('/config', methods=['GET', 'POST'])
def handle_config():
    """处理配置文件uiconfig.json的读写"""
    from flask import current_app
    DATA_DIR = current_app.config['DATA_DIR']
    config_file = os.path.join(DATA_DIR, 'uiconfig.json')
    
    if request.method == 'GET':
        return _handle_get_config(config_file)
    elif request.method == 'POST':
        return _handle_post_config(config_file)


def _handle_get_config(config_file):
    """处理GET请求 - 读取配置文件"""
    try:
        from flask import current_app, request
        FLASK_PORT = current_app.config.get('FLASK_PORT', 12000)
        AI_Server_HOST = current_app.config.get('AI_SERVER_HOST', '127.0.0.1')
        AI_Server_PORT = current_app.config.get('AI_SERVER_PORT', 12000)

        # 🆕 使用请求信息构建可访问的 URL（而非 FLASK_HOST=0.0.0.0）
        req_host = request.host.split(':')[0]  # 浏览器实际访问的地址
        
        if not os.path.exists(config_file):
            logger.info("配置文件不存在，创建默认配置")
            default_ai_source = "http://127.0.0.1:12000/static/postcase/index.html"
            default_config = {
                "dataSource": f"http://{req_host}:{FLASK_PORT}/api/v1/uirecoreder?filename=records.json",
                "aiSource": default_ai_source,
                "updateInterval": 1000,
                "autoUpdate": True,
                "maxRetries": 3,
                "retryInterval": 2000,
                "lastUpdated": datetime.now().isoformat(),
                "version": "1.0"
            }
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 🆕 始终用当前端口覆盖 dataSource（修复旧配置文件的过期端口）
        config_data["dataSource"] = f"http://{req_host}:{FLASK_PORT}/api/v1/uirecoreder?filename=records.json"
        # 使用 postcase 页面作为 AI 用例生成入口
        config_data["aiSource"] = "http://127.0.0.1:12000/static/postcase/index.html"
        
        logger.info("成功读取配置文件")
        return jsonify({
            'success': True,
            'config': config_data,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"读取配置文件失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"读取配置文件失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500


def _handle_post_config(config_file):
    """处理POST请求 - 保存配置文件"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': '请求必须是JSON格式',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        config_data = request.get_json()
        
        # 验证配置数据格式
        required_fields = ['dataSource', 'aiSource', 'updateInterval', 'autoUpdate', 'maxRetries', 'retryInterval']
        for field in required_fields:
            if field not in config_data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必需字段: {field}',
                    'timestamp': datetime.now().isoformat()
                }), 400
        
        # 添加时间戳
        config_data['lastUpdated'] = datetime.now().isoformat()
        if 'version' not in config_data:
            config_data['version'] = "1.0"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        # 写入配置文件
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        logger.info("成功保存配置文件")
        return jsonify({
            'success': True,
            'message': '配置文件已成功保存',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"保存配置文件失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"保存配置文件失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# 监控控制接口
# ============================================================================

@api_blueprint.route('/start', methods=['GET'])
def start_monitoring():
    """启动系统监控，支持延时启动"""
    from flask import current_app
    monitor_lock = current_app.config.get('MONITOR_LOCK')

    # 获取project参数
    project = request.args.get('project', 'my_data')

    # 获取delay参数（秒）
    delay_seconds = int(request.args.get('delay', 0))

    # 如果有延时参数，返回信息让前端处理倒计时
    if delay_seconds > 0:
        logger.info(f"⏰ 延时启动录制: 项目={project}, 延时={delay_seconds}秒")
        return jsonify({
            'success': True,
            'message': f'延时录制已设置，{delay_seconds}秒后开始',
            'project': project,
            'delay': delay_seconds,
            'timestamp': datetime.now().isoformat()
        })

    # 立即启动
    monitor_lock.acquire()

    try:
        # 确保project是安全的路径
        if '..' in project or project.startswith('/'):
            return jsonify({
                'success': False,
                'error': '非法的数据目录路径',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 保存目录名称到全局变量
        DATA_DIR = current_app.config['DATA_DIR']
        current_app.config['CURRENT_PROJECT_NAME'] = project
        
        monitor_instance = current_app.config.get('MONITOR_INSTANCE')
        monitor_thread = current_app.config.get('MONITOR_THREAD')
        
        # 先停止之前的监控（如果存在）
        if monitor_instance and monitor_instance.is_monitoring:
            logger.info("🛑 停止之前的监控...")
            monitor_instance.stop_monitoring()
            
            # 等待监控线程结束
            if monitor_thread and monitor_thread.is_alive():
                monitor_thread.join(timeout=5)
            
            # 清理监控资源
            current_app.config['MONITOR_INSTANCE'] = None
            current_app.config['MONITOR_THREAD'] = None
        
        data_path = os.path.join(DATA_DIR, project)
        
        # 导入监控模块
        from ..core import SystemMonitor, start_file_server_thread
        STATIC_FILE_HOST = current_app.config.get('STATIC_FILE_HOST', '0.0.0.0')
        STATIC_FILE_PORT = current_app.config.get('STATIC_FILE_PORT', 12001)

        # 启动监控线程
        import threading

        # 在线程外创建app引用，用于在worker中使用
        app_ref = current_app._get_current_object()

        # 获取实际的服务器地址（从请求中获取）
        base_url = request.host_url.rstrip('/')  # 移除末尾的斜杠

        def monitoring_worker(data_dir):
            """监控器工作线程"""
            from ..core import SystemMonitor, start_file_server_thread
            import time
            
            logger.info("🌐 启动新的文件服务器...")
            logger.info(f"📡 使用服务器地址: {base_url}")
            data_path = Path(data_dir)
            if not data_path.exists():
                data_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 创建数据目录: {data_path}")

            file_server_thread = start_file_server_thread(str(data_path), host=STATIC_FILE_HOST, port=STATIC_FILE_PORT)
            
            # 创建监控器
            monitor = SystemMonitor(
                data_dir=data_dir,
                enable_mouse=True,
                enable_keyboard=True,
                keyboard_timeout=3.0,
                enable_event_recording=True,
                base_url=base_url
            )
            
            # 使用app上下文保存监控实例
            with app_ref.app_context():
                app_ref.config['MONITOR_INSTANCE'] = monitor
            
            logger.info(f"✅ 监控器创建完成 (数据目录: {data_path.absolute()})")
            
            # 启动监控
            if monitor.start_monitoring():
                logger.info("✅ 监控已启动!")
                logger.info("💡 提示: 请在屏幕上点击鼠标或输入文本来测试")
                
                # 保持运行
                event_count = 0
                while monitor.is_monitoring:
                    time.sleep(1)
                    
                    # 每5秒显示一次事件计数
                    event_count += 1
                    if event_count % 5 == 0:
                        status = monitor.get_status()
                        stats = status['stats']
                        logger.info(f"📊 运行中... 总事件: {stats['total_events']} (鼠标: {stats['mouse_clicks']}, 键盘: {stats['keyboard_inputs']})")
            else:
                logger.error("❌ 监控启动失败")
        
        monitor_thread = threading.Thread(
            target=monitoring_worker, 
            args=(data_path,),
            daemon=True
        )
        monitor_thread.start()
        current_app.config['MONITOR_THREAD'] = monitor_thread
        
        logger.info(f"✅ 监控已启动 (数据目录: {data_path})")
        return jsonify({
            'success': True,
            'message': f'监控已启动，数据目录: {data_path}',
            'project': project,
            'data_path': data_path,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"启动监控失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"启动监控失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500
    finally:
        current_app.config['MONITOR_LOCK'].release()


@api_blueprint.route('/stop', methods=['GET'])
def stop_monitoring():
    """停止系统监控"""
    from flask import current_app
    monitor_lock = current_app.config.get('MONITOR_LOCK')
    monitor_lock.acquire()
    
    try:
        monitor_instance = current_app.config.get('MONITOR_INSTANCE')
        monitor_thread = current_app.config.get('MONITOR_THREAD')
        
        # 如果监控未在运行，直接返回成功（幂等操作）
        if not monitor_instance or not monitor_instance.is_monitoring:
            # 清理资源
            current_app.config['MONITOR_INSTANCE'] = None
            current_app.config['MONITOR_THREAD'] = None
            logger.info("ℹ️ 监控未在运行，已清理资源")
            return jsonify({
                'success': True,
                'message': '监控未在运行',
                'timestamp': datetime.now().isoformat()
            })
        
        # 停止监控
        monitor_instance.stop_monitoring()
        
        # 等待监控线程结束
        if monitor_thread and monitor_thread.is_alive():
            monitor_thread.join(timeout=5)
        
        # 清理监控资源
        current_app.config['MONITOR_INSTANCE'] = None
        current_app.config['MONITOR_THREAD'] = None
        
        logger.info("✅ 监控已停止")
        return jsonify({
            'success': True,
            'message': '监控已停止',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"停止监控失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"停止监控失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500
    finally:
        monitor_lock.release()


@api_blueprint.route('/status', methods=['GET'])
def get_monitor_status():
    """获取监控状态"""
    from flask import current_app
    monitor_instance = current_app.config.get('MONITOR_INSTANCE')
    
    if monitor_instance:
        try:
            status = monitor_instance.get_status()
            return jsonify({
                'success': True,
                'status': status,
                'is_monitoring': monitor_instance.is_monitoring,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"获取状态失败: {str(e)}")
            return jsonify({
                'success': False,
                'error': f"获取状态失败: {str(e)}",
                'timestamp': datetime.now().isoformat()
            }), 500
    else:
        return jsonify({
            'success': True,
            'status': None,
            'is_monitoring': False,
            'timestamp': datetime.now().isoformat()
        })


# ============================================================================
# 项目管理接口
# ============================================================================

@api_blueprint.route('/loadproject', methods=['GET'])
def load_project():
    """加载项目设置，可选是否自动启动监控"""
    try:
        from flask import current_app
        DATA_DIR = current_app.config['DATA_DIR']
        STATIC_FILE_HOST = current_app.config.get('STATIC_FILE_HOST', '0.0.0.0')
        STATIC_FILE_PORT = current_app.config.get('STATIC_FILE_PORT', 12001)
        project_name = request.args.get('project', '').strip()

        # 获取mode参数：record=启动录制模式, view=查看模式(默认)
        mode = request.args.get('mode', 'view').lower()

        # 根据mode参数决定是否自动启动监控
        # mode=record 时启动录制，其他模式（包括view或不指定）不自动启动
        auto_start = (mode == 'record')
        
        if not project_name:
            return jsonify({
                'success': False,
                'error': '项目名称不能为空',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 验证项目名称安全性
        if '..' in project_name or project_name.startswith('/'):
            return jsonify({
                'success': False,
                'error': '非法的项目名称',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 检查是否包含非法字符
        if re.search(r'[<>:"/\\|?*]', project_name):
            return jsonify({
                'success': False,
                'error': '项目名称包含非法字符',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 设置当前数据目录
        old_project_name = current_app.config.get('CURRENT_PROJECT_NAME')
        current_app.config['CURRENT_PROJECT_NAME'] = project_name

        data_path = os.path.join(DATA_DIR, project_name)
        
        # 确保目录存在
        os.makedirs(data_path, exist_ok=True)
        
        # 如果目录发生变化，更新文件服务器
        if old_project_name != project_name:
            try:
                from ..core import start_file_server_thread
                
                # 启动/切换文件服务器线程
                server_thread = start_file_server_thread(
                    root_dir=data_path,
                    host=STATIC_FILE_HOST,
                    port=STATIC_FILE_PORT,
                    daemon=True
                )
                
                logger.info(f"🔄 文件服务器根目录已更新: {old_project_name} → {project_name}")
                
            except Exception as e:
                logger.warning(f"更新文件服务器时出现警告: {e}")
        
        logger.info(f"✅ 项目已加载: {project_name}")

        # 根据auto_start参数决定是否启动监控
        if not auto_start:
            logger.info(f"📋 仅加载项目配置，不启动监控 (auto_start={auto_start})")
            return jsonify({
                'success': True,
                'message': f'项目 "{project_name}" 已加载（仅查看模式）',
                'project_name': project_name,
                'auto_start': auto_start,
                'timestamp': datetime.now().isoformat()
            })

        # 自动启动监控
        try:
            monitor_lock = current_app.config.get('MONITOR_LOCK')
            monitor_lock.acquire()
            
            monitor_instance = current_app.config.get('MONITOR_INSTANCE')
            monitor_thread = current_app.config.get('MONITOR_THREAD')
            
            # 先停止之前的监控（如果存在且与当前项目不同）
            if monitor_instance and monitor_instance.is_monitoring:
                logger.info("🛑 停止之前的监控...")
                monitor_instance.stop_monitoring()
                
                # 等待监控线程结束
                if monitor_thread and monitor_thread.is_alive():
                    monitor_thread.join(timeout=5)
                
                # 清理监控资源
                current_app.config['MONITOR_INSTANCE'] = None
                current_app.config['MONITOR_THREAD'] = None
            
            # 导入监控模块
            from ..core import SystemMonitor, start_file_server_thread
            import threading
            from pathlib import Path

            # 在线程外创建app引用，用于在worker中使用
            app_ref = current_app._get_current_object()

            # 获取实际的服务器地址（从请求中获取）
            base_url = request.host_url.rstrip('/')

            def monitoring_worker(data_dir):
                """监控器工作线程"""
                from ..core import SystemMonitor, start_file_server_thread
                import time
                
                logger.info("🌐 启动新的文件服务器...")
                logger.info(f"📡 使用服务器地址: {base_url}")
                data_path = Path(data_dir)
                if not data_path.exists():
                    data_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"📁 创建数据目录: {data_path}")

                file_server_thread = start_file_server_thread(str(data_path), host=STATIC_FILE_HOST, port=STATIC_FILE_PORT)
                
                # 创建监控器
                monitor = SystemMonitor(
                    data_dir=data_dir,
                    enable_mouse=True,
                    enable_keyboard=True,
                    keyboard_timeout=3.0,
                    enable_event_recording=True,
                    base_url=base_url
                )
                
                # 使用app上下文保存监控实例
                with app_ref.app_context():
                    app_ref.config['MONITOR_INSTANCE'] = monitor
                
                logger.info(f"✅ 监控器创建完成 (数据目录: {data_path.absolute()})")
                
                # 启动监控
                if monitor.start_monitoring():
                    logger.info("✅ 监控已启动!")
                    logger.info("💡 提示: 请在屏幕上点击鼠标或输入文本来测试")
                    
                    # 保持运行
                    event_count = 0
                    while monitor.is_monitoring:
                        time.sleep(1)
                        
                        # 每5秒显示一次事件计数
                        event_count += 1
                        if event_count % 5 == 0:
                            status = monitor.get_status()
                            stats = status['stats']
                            logger.info(f"📊 运行中... 总事件: {stats['total_events']} (鼠标: {stats['mouse_clicks']}, 键盘: {stats['keyboard_inputs']})")
                else:
                    logger.error("❌ 监控启动失败")
            
            monitor_thread = threading.Thread(
                target=monitoring_worker, 
                args=(data_path,),
                daemon=True
            )
            monitor_thread.start()
            current_app.config['MONITOR_THREAD'] = monitor_thread
            
            logger.info(f"✅ 监控已自动启动 (数据目录: {data_path})")
            
        except Exception as e:
            logger.error(f"启动监控失败: {str(e)}")
        finally:
            monitor_lock.release()
        
        return jsonify({
            'success': True,
            'message': f'项目 "{project_name}" 已成功加载',
            'project': project_name,
            'current_project_name': project_name,
            'data_path': data_path,
            'monitoring_started': True,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"加载项目失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"加载项目失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# 导出接口
# ============================================================================

@api_blueprint.route('/export', methods=['GET'])
def export_data():
    """导出数据接口"""
    import time as _time
    _t0 = _time.time()
    
    try:
        from flask import current_app
        DATA_DIR = current_app.config['DATA_DIR']
        
        # 获取导出格式
        export_type = request.args.get('type', '').lower()
        
        logger.info(f"[导出入口] 开始处理导出请求: type={export_type}, args={dict(request.args)}")
        
        # 验证导出格式
        supported_types = ['zip', 'word', 'pdf', 'markdown', 'html', 'test-docs', 'help-docs', 'gui-runner']
        if export_type not in supported_types:
            logger.warning(f"[导出入口] 不支持的格式: {export_type}")
            return jsonify({
                'success': False,
                'error': f'不支持的导出格式: {export_type}',
                'supported_types': supported_types,
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 获取数据目录
        project = request.args.get('project', '')
        if not project:
            project = current_app.config.get('CURRENT_PROJECT_NAME', '')
        
        data_path = Path(DATA_DIR, project)

        if not data_path or not os.path.exists(data_path):
            logger.error(f"[导出入口] 数据目录不存在: data_path={data_path}")
            return jsonify({
                'success': False,
                'error': '数据目录不存在或未指定',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        logger.info(f"[导出入口] 数据目录确认存在: {data_path}, 大小={sum(f.stat().st_size for f in data_path.rglob('*') if f.is_file()) / 1024:.1f}KB")
        
        # ── GuiRunner: 直接复用 recorder 的完整导出管线，不走 uiexporter ──
        if export_type == 'gui-runner':
            from flask import current_app
            guirunner_url = current_app.config.get('GUIRUNNER_URL', 'http://127.0.0.1:60000')
            
            # 找到录制目录 — project 名称即 recording_ 目录名
            recordings_root = os.environ.get("SCREENRECORDINGS_DIR")
            if not recordings_root:
                from recorder.platform_utils import get_default_recordings_dir
                recordings_root = get_default_recordings_dir()
            
            rec_dir = os.path.join(recordings_root, project)
            if not os.path.isdir(rec_dir):
                logger.error(f"[导出入口] GuiRunner 录制目录不存在: {rec_dir}")
                return jsonify({
                    'success': False,
                    'error': f'未找到录制目录: {rec_dir}，请先在 recorder 中录制对应项目',
                    'timestamp': datetime.now().isoformat()
                }), 404
            
            from recorder.click_icon_extractor import export_recording_to_guirunner
            result = export_recording_to_guirunner(rec_dir, guirunner_url)
            if result.get('ok'):
                result['success'] = True
                result['timestamp'] = datetime.now().isoformat()
                return jsonify(result)
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('message', 'GuiRunner 推送失败'),
                    'timestamp': datetime.now().isoformat()
                }), 500

        # 调用uiexporter模块进行导出
        try:
            _t1 = _time.time()
            success, output_path = uiexporter_export(export_type, str(data_path))
            _elapsed = _time.time() - _t1

            logger.info(f"[导出入口] uiexporter 返回: success={success}, output_path={output_path}, 耗时={_elapsed:.2f}s")

            if success and output_path:
                logger.info(f"导出成功: {output_path}")

                # 返回文件下载响应
                return send_from_directory(
                    directory=os.path.dirname(output_path),
                    path=os.path.basename(output_path),
                    as_attachment=True,
                    download_name=os.path.basename(output_path)
                )
            else:
                logger.error(f"导出失败")
                return jsonify({
                    'success': False,
                    'error': '导出过程中发生错误',
                    'timestamp': datetime.now().isoformat()
                }), 500
                
        except ImportError as e:
            logger.error(f"导入uiexporter模块失败: {e}")
            return jsonify({
                'success': False,
                'error': '导出模块加载失败',
                'details': str(e),
                'timestamp': datetime.now().isoformat()
            }), 500
        except Exception as e:
            logger.error(f"导出过程异常: {e}")
            return jsonify({
                'success': False,
                'error': f'导出异常: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 500
            
    except Exception as e:
        logger.error(f"导出接口异常: {e}")
        return jsonify({
            'success': False,
            'error': '服务器内部错误',
            'timestamp': datetime.now().isoformat()
        }), 500


@api_blueprint.route('/export/formats', methods=['GET'])
def get_export_formats():
    """获取支持的导出格式列表"""
    try:
        from ..core.uiexporter import list_supported_formats, get_format_info
        
        formats = list_supported_formats()
        format_details = {}
        
        for fmt in formats:
            format_details[fmt] = get_format_info(fmt)
        
        return jsonify({
            'success': True,
            'data': {
                'supported_formats': formats,
                'format_details': format_details
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"获取导出格式列表失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取格式列表失败',
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# WebOCR接口
# ============================================================================

@api_blueprint.route('/webocr', methods=['GET'])
def web_ocr():
    """WebOCR API接口 - 支持网络图像OCR识别"""
    try:
        # 获取URL参数
        image_url = request.args.get('url', '').strip()
        
        if not image_url:
            return jsonify({
                'success': False,
                'error': '缺少URL参数',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 解码URL
        from urllib.parse import unquote
        image_url = unquote(image_url)
        
        # 导入gui_web_ocr函数
        try:
            from guiocr import gui_web_ocr
        except ImportError as e:
            logger.error(f"导入gui_web_ocr失败: {e}")
            return jsonify({
                'success': False,
                'error': 'OCR模块加载失败',
                'timestamp': datetime.now().isoformat()
            }), 500
        
        # 调用OCR函数
        logger.info(f"开始OCR识别: {image_url}")
        result = gui_web_ocr(image_url, output='json')
        
        logger.info(f"OCR识别完成: {len(result.get('ocr_text', ''))}个字符")
        
        return jsonify({
            'success': True,
            'data': result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        import traceback
        logger.error(traceback.format_exc())
        logger.error(f"WebOCR处理失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"OCR处理失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# WebRecorder导入接口
# ============================================================================

@api_blueprint.route('/webrecoreder', methods=['POST'])
def webrecorder_import():
    """接收WebRecorder的步骤数据并创建对应的项目目录和文件"""
    try:
        from flask import current_app
        DATA_DIR = current_app.config['DATA_DIR']
        
        # 获取请求数据
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '请求数据为空',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 获取项目名称，默认为test
        project_name = data.get('projectName', 'test')
        description = data.get('description', '')
        steps = data.get('steps', [])
        
        if not steps:
            return jsonify({
                'success': False,
                'error': '没有步骤数据',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 创建项目目录
        project_dir = os.path.join(DATA_DIR, project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        # 创建screenshots目录
        screenshots_dir = os.path.join(project_dir, 'my_screenshots')
        os.makedirs(screenshots_dir, exist_ok=True)
        
        # 转换步骤数据为records.json格式
        records = []
        
        for step in steps:
            # 保存截图到本地文件
            screenshot_data = step.get('screenshot', '')
            screenshot_filename = None
            
            if screenshot_data and screenshot_data.startswith('data:image/'):
                # 从base64数据中提取图片数据
                import base64
                
                # 解析base64数据
                header, encoded = screenshot_data.split(',', 1)
                image_format = header.split('/')[1].split(';')[0]
                
                # 生成文件名
                timestamp = step.get('timestamp', datetime.now().isoformat())
                # 清理时间戳中的特殊字符
                clean_timestamp = timestamp.replace(':', '').replace('.', '').replace('-', '')
                screenshot_filename = f"step_{step.get('stepNumber', 0)}_{clean_timestamp}.png"
                
                # 保存图片文件
                screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
                try:
                    with open(screenshot_path, 'wb') as f:
                        f.write(base64.b64decode(encoded))
                    logger.info(f"保存截图: {screenshot_filename}")
                except Exception as e:
                    logger.error(f"保存截图失败: {e}")
                    screenshot_filename = None
            
            # 转换为records.json格式
            record = {
                "id": step.get('stepNumber', 0),
                "title": step.get('title', f"第{step.get('stepNumber', 0)}步"),
                "context": f"操作类型: {step.get('type', 'unknown')}; 时间戳: {step.get('timestamp', '')}",
                "markdown": f"![操作截图](http://127.0.0.1:{current_app.config.get('STATIC_FILE_PORT', 12001)}/my_screenshots/{screenshot_filename})" if screenshot_filename else "",
                "url": f"http://127.0.0.1:{current_app.config.get('STATIC_FILE_PORT', 12001)}/my_screenshots/{screenshot_filename}" if screenshot_filename else "",
                "operation_details": {
                    "位置": f"({step.get('point', {}).get('x', 0)}, {step.get('point', {}).get('y', 0)})",
                    "时间戳": step.get('timestamp', ''),
                    "操作类型": step.get('type', 'unknown')
                },
                "testCase": "需要生成包含正向测试、异常测试、边界测试的完整测试用例，重点关注安全性和用户体验。",
                "thumbnail": f"<svg xmlns='http://www.w3.org/2000/svg' width='168' height='100' viewBox='0 0 168 100'>\\n    <rect width='168' height='100' fill='#ffffff'/>\\n    <rect x='10' y='10' width='148' height='80' rx='4' fill='#eef2f7' stroke='#cbd5e0'/>\\n    <text x='50%' y='40%' dominant-baseline='middle' text-anchor='middle' font-family='Segoe UI, SF Pro Display, -apple-system, BlinkMacSystemFont, Roboto, Helvetica Neue, sans-serif' font-size='12' fill='#0066cc'>{step.get('type', '操作')}</text>\\n    <text x='50%' y='60%' dominant-baseline='middle' text-anchor='middle' font-family='Segoe UI, SF Pro Display, -apple-system, BlinkMacSystemFont, Roboto, Helvetica Neue, sans-serif' font-size='10' fill='#4a5568'>操作 {step.get('stepNumber', 0)}</text>\\n</svg>",
                "ai_result": "",
                "link": "",
                "remark": ""
            }
            
            records.append(record)
        
        # 保存records.json文件
        records_path = os.path.join(project_dir, 'records.json')
        with open(records_path, 'w', encoding='utf-8') as f:
            json.dump({"slides": records}, f, ensure_ascii=False, indent=2)
        
        # 保存input.json文件（原始数据）
        input_path = os.path.join(project_dir, 'input.json')
        with open(input_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ WebRecorder导入成功: {project_name} - {len(steps)}个步骤")
        
        return jsonify({
            'success': True,
            'message': '数据导入成功',
            'data': {
                'projectName': project_name,
                'projectDir': project_dir,
                'recordsCount': len(records),
                'screenshotsCount': len([s for s in steps if s.get('screenshot')]),
                'recordsPath': records_path,
                'inputPath': input_path
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"WebRecorder导入失败: {e}")
        return jsonify({
            'success': False,
            'error': f'数据导入失败: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500



# ============================================================================
# 服务器配置接口
# ============================================================================

@api_blueprint.route('/server-config', methods=['GET'])
def get_server_config():
    """获取服务器配置信息"""
    from flask import request
    
    # 获取当前请求的协议和主机信息
    protocol = request.scheme
    host = request.host.split(':')[0]  # 移除端口部分
    port = request.environ.get('SERVER_PORT', '12000')
    
    # 构建基础URL
    base_url = f"{protocol}://{host}"
    if port and port != '80' and port != '443':
        base_url += f":{port}"
    
    return jsonify({
        'success': True,
        'config': {
            'baseUrl': base_url,
            'apiBaseUrl': f"{base_url}/api/v1",
            'host': host,
            'port': int(port) if port.isdigit() else 12000,
            'protocol': protocol
        },
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# 健康检查接口
# ============================================================================

@api_blueprint.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    from flask import current_app
    monitor_instance = current_app.config.get('MONITOR_INSTANCE')
    
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# 项目管理接口
# ============================================================================

@api_blueprint.route('/listprojects', methods=['GET'])
def list_projects():
    """列出所有项目"""
    try:
        from flask import current_app
        DATA_DIR = current_app.config['DATA_DIR']
        
        projects = []
        if os.path.exists(DATA_DIR):
            for project_name in os.listdir(DATA_DIR):
                project_path = os.path.join(DATA_DIR, project_name)
                if os.path.isdir(project_path):
                    # 读取项目描述
                    description = ''
                    desc_file = os.path.join(project_path, 'description.txt')
                    if os.path.exists(desc_file):
                        try:
                            with open(desc_file, 'r', encoding='utf-8') as f:
                                description = f.read()
                        except:
                            pass
                    
                    # 获取记录数量
                    record_count = 0
                    records_file = os.path.join(project_path, 'records.json')
                    if os.path.exists(records_file):
                        try:
                            with open(records_file, 'r', encoding='utf-8') as f:
                                records = json.load(f)
                                record_count = len(records) if isinstance(records, list) else 0
                        except:
                            pass
                    
                    # 获取创建和更新时间
                    created_at = os.path.getctime(project_path)
                    updated_at = os.path.getmtime(project_path)
                    
                    projects.append({
                        'name': project_name,
                        'description': description,
                        'record_count': record_count,
                        'created_at': datetime.fromtimestamp(created_at).isoformat(),
                        'updated_at': datetime.fromtimestamp(updated_at).isoformat()
                    })
        
        # 按更新时间降序排序
        projects.sort(key=lambda x: x['updated_at'], reverse=True)
        
        return jsonify({
            'success': True,
            'projects': projects,
            'count': len(projects),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"列出项目失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"列出项目失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500


@api_blueprint.route('/updateproject', methods=['POST'])
def update_project():
    """更新项目信息"""
    try:
        from flask import current_app
        DATA_DIR = current_app.config['DATA_DIR']
        
        data = request.get_json()
        project_name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not project_name:
            return jsonify({
                'success': False,
                'error': '项目名称不能为空',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 验证项目名称安全性
        if '..' in project_name or project_name.startswith('/'):
            return jsonify({
                'success': False,
                'error': '非法的项目名称',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 检查项目是否存在
        project_path = os.path.join(DATA_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({
                'success': False,
                'error': '项目不存在',
                'timestamp': datetime.now().isoformat()
            }), 404
        
        # 保存项目描述
        desc_file = os.path.join(project_path, 'description.txt')
        with open(desc_file, 'w', encoding='utf-8') as f:
            f.write(description)
        
        logger.info(f"项目 '{project_name}' 描述已更新")
        
        return jsonify({
            'success': True,
            'message': f'项目 "{project_name}" 更新成功',
            'project': project_name,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"更新项目失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"更新项目失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500


@api_blueprint.route('/deleteproject', methods=['POST'])
def delete_project():
    """删除项目"""
    try:
        from flask import current_app
        DATA_DIR = current_app.config['DATA_DIR']
        
        data = request.get_json()
        project_name = data.get('name', '').strip()
        
        if not project_name:
            return jsonify({
                'success': False,
                'error': '项目名称不能为空',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 验证项目名称安全性
        if '..' in project_name or project_name.startswith('/'):
            return jsonify({
                'success': False,
                'error': '非法的项目名称',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # 检查项目是否存在
        project_path = os.path.join(DATA_DIR, project_name)
        if not os.path.exists(project_path):
            return jsonify({
                'success': False,
                'error': '项目不存在',
                'timestamp': datetime.now().isoformat()
            }), 404
        
        # 停止监控（如果正在运行）
        try:
            from flask import current_app
            monitor_lock = current_app.config.get('MONITOR_LOCK')
            monitor_instance = current_app.config.get('MONITOR_INSTANCE')
            monitor_thread = current_app.config.get('MONITOR_THREAD')
            current_project_name = current_app.config.get('CURRENT_PROJECT_NAME')
            
            if monitor_lock and current_project_name == project_name:
                monitor_lock.acquire()
                try:
                    if monitor_instance and monitor_instance.is_monitoring:
                        logger.info(f"停止项目 '{project_name}' 的监控...")
                        monitor_instance.stop_monitoring()
                        
                        if monitor_thread and monitor_thread.is_alive():
                            monitor_thread.join(timeout=5)
                        
                        current_app.config['MONITOR_INSTANCE'] = None
                        current_app.config['MONITOR_THREAD'] = None
                finally:
                    monitor_lock.release()
        except Exception as e:
            logger.warning(f"停止监控时出现警告: {e}")
        
        # 删除项目目录
        import shutil
        shutil.rmtree(project_path)
        
        logger.info(f"项目 '{project_name}' 已删除")
        
        return jsonify({
            'success': True,
            'message': f'项目 "{project_name}" 删除成功',
            'project': project_name,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"删除项目失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"删除项目失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }), 500
