"""
系统行为监控主控制器
整合鼠标监控、键盘监控、数据记录等功能，提供统一的启动/停止接口
"""

import os
import sys
import time
import threading
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from .screenshot import ScreenshotManager
from .mouse_monitor import MouseMonitor
from .keyboard_monitor import KeyboardMonitor
from .event_recorder import EventRecorder
from ..utils.data_recorder import DataRecorder


class SystemMonitor:
    """系统行为监控主控制器"""
    
    def __init__(self, 
                 data_dir="my_data",
                 enable_mouse=True, 
                 enable_keyboard=True,
                 keyboard_timeout=3.0,
                 enable_event_recording=True,
                 base_url="http://127.0.0.1:12000"):
        """
        初始化系统监控器
        
        Args:
            data_dir (str): 数据保存目录，所有文件将统一存放在此目录下
            enable_mouse (bool): 是否启用鼠标监控
            enable_keyboard (bool): 是否启用键盘监控
            keyboard_timeout (float): 键盘输入超时时间（秒）
            enable_event_recording (bool): 是否启用事件录制
            base_url (str): 基础URL，用于生成完整的图片URL
        """
        # 根据data_dir动态生成子目录路径
        data_path = Path(data_dir)
        screenshot_dir = data_path / "my_screenshots"
        records_file = data_path / "records.json"
        
        # 初始化组件
        self.screenshot_manager = ScreenshotManager(str(screenshot_dir))
        self.data_recorder = DataRecorder(data_dir)
        
        # 初始化事件录制器
        self.event_recorder = None
        if enable_event_recording:
            self.event_recorder = EventRecorder(
                output_dir=str(screenshot_dir),
                records_file=str(records_file),
                base_url=base_url
            )
        
        # 初始化监控器
        self.mouse_monitor = None
        self.keyboard_monitor = None
        
        if enable_mouse:
            self.mouse_monitor = MouseMonitor(
                screenshot_manager=self.screenshot_manager,
                data_callback=self._handle_mouse_event
            )
            # 将键盘监控器引用传递给鼠标监控器
            if enable_keyboard:
                self.mouse_monitor.keyboard_monitor = self.keyboard_monitor
        
        if enable_keyboard:
            self.keyboard_monitor = KeyboardMonitor(
                screenshot_manager=self.screenshot_manager,
                data_callback=self._handle_keyboard_event,
                input_timeout=keyboard_timeout
            )
        
        # 监控状态
        self.is_monitoring = False
        self.start_time = None
        self.monitoring_thread = None
        
        # 配置选项
        self.config = {
            "enable_mouse": enable_mouse,
            "enable_keyboard": enable_keyboard,
            "keyboard_timeout": keyboard_timeout,
            "enable_event_recording": enable_event_recording,
            "screenshot_dir": str(screenshot_dir),
            "data_dir": data_dir,
            "records_file": str(records_file)
        }
    
    def _handle_mouse_event(self, event_data):
        """处理鼠标事件数据"""
        try:
            # 记录到数据文件
            self.data_recorder.record_event(event_data)
            
            # 如果启用了事件录制，记录操作
            if self.event_recorder and self.event_recorder.is_recording:
                # 从事件数据中提取操作详情
                operation_details = {
                    "位置": f"({event_data['position']['x']}, {event_data['position']['y']})",
                    "按钮": event_data['button'],
                    "时间戳": event_data['timestamp']
                }
                
                # 获取截图文件名
                screenshot_filename = None
                if 'screenshot' in event_data and 'filename' in event_data['screenshot']:
                    screenshot_filename = event_data['screenshot']['filename']
                
                # 调用EventRecorder记录操作
                self.event_recorder.record_operation("mouse", operation_details, screenshot_filename)
            
            # 打印事件信息
            logger.info(f"🖱️  鼠标点击: ({event_data['position']['x']}, {event_data['position']['y']}) - {event_data['timestamp']}")
            
        except Exception as e:
            logger.error(f"处理鼠标事件失败: {e}")
    
    def _handle_keyboard_event(self, event_data):
        """处理键盘事件数据"""
        try:
            # 记录到数据文件
            self.data_recorder.record_event(event_data)
            
            # 如果启用了事件录制，记录操作
            if self.event_recorder and self.event_recorder.is_recording:
                # 从事件数据中提取操作详情
                operation_details = {
                    "输入内容": event_data.get('input_string', ''),
                    "长度": event_data.get('input_length', 0),
                    "首字符": event_data.get('first_char', ''),
                    "末字符": event_data.get('last_char', ''),
                    "结束原因": event_data.get('end_reason', ''),
                    "时间戳": event_data.get('timestamp', '')
                }
                
                # 获取截图文件名 - 处理screenshots数据结构
                screenshots = event_data.get('screenshots', {})
                
                # 分别处理first_char和last_char的截图
                if 'first_char' in screenshots and screenshots['first_char'].get('success'):
                    first_char_filename = screenshots['first_char'].get('filename')
                    if first_char_filename:
                        # 为首字符截图记录操作
                        first_char_details = operation_details.copy()
                        first_char_details['截图类型'] = '首字符'
                        self.event_recorder.record_operation("keyboard", first_char_details, first_char_filename)
                        logger.debug(f"记录首字符截图: {first_char_filename}")
                
                if 'last_char' in screenshots and screenshots['last_char'].get('success'):
                    last_char_filename = screenshots['last_char'].get('filename')
                    if last_char_filename:
                        # 为末字符截图记录操作
                        last_char_details = operation_details.copy()
                        last_char_details['截图类型'] = '末字符'
                        self.event_recorder.record_operation("keyboard", last_char_details, last_char_filename)
                        logger.debug(f"记录末字符截图: {last_char_filename}")
            
            # 打印事件信息
            input_str = event_data['input_string'].replace('\n', '\\n').replace('\t', '\\t')
            end_reason = event_data.get('end_reason', 'timeout')
            logger.info(f"⌨️  键盘输入: '{input_str}' (长度: {event_data['input_length']}, 结束原因: {end_reason}) - {event_data['timestamp']}")
            
        except Exception as e:
            logger.error(f"处理键盘事件失败: {e}")
    
    def start_monitoring(self):
        """
        开始监控
        
        Returns:
            bool: 是否成功启动
        """
        if self.is_monitoring:
            logger.warning("监控已在运行中")
            return False
        
        try:
            logger.info("正在启动系统监控...")
            
            # 启动鼠标监控
            if self.mouse_monitor:
                self.mouse_monitor.start_monitoring()
                logger.info("✅ 鼠标监控已启动")
            
            # 启动键盘监控
            if self.keyboard_monitor:
                self.keyboard_monitor.start_monitoring()
                logger.info("✅ 键盘监控已启动")
            
            # 启动事件录制
            if self.event_recorder:
                self.event_recorder.start_recording()
                logger.info("✅ 事件录制已启动")
            
            # 更新状态
            self.is_monitoring = True
            self.start_time = datetime.now()
            
            logger.info(f"""
╔═══════════════════════════════════════╗
║          系统监控已启动                ║
╠═══════════════════════════════════════╣
║  监控模式: {'鼠标+键盘' if self.config['enable_mouse'] and self.config['enable_keyboard'] else '仅鼠标' if self.config['enable_mouse'] else '仅键盘'}               ║
║  启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}           ║
║  数据目录: {self.config['data_dir']}                ║
║  截图目录: {self.config['screenshot_dir']}                ║
║                                       ║
║  按 Ctrl+C 停止监控                    ║
╚═══════════════════════════════════════╝
            """)
            
            return True
            
        except Exception as e:
            logger.error(f"启动监控失败: {e}")
            self.is_monitoring = False
            return False
    
    def stop_monitoring(self):
        """
        停止监控
        
        Returns:
            bool: 是否成功停止
        """
        if not self.is_monitoring:
            logger.warning("监控未在运行")
            return False
        
        try:
            logger.info("正在停止系统监控...")
            
            # 停止鼠标监控
            if self.mouse_monitor:
                self.mouse_monitor.stop_monitoring()
                logger.info("✅ 鼠标监控已停止")
            
            # 停止键盘监控
            if self.keyboard_monitor:
                self.keyboard_monitor.stop_monitoring()
                logger.info("✅ 键盘监控已停止")
            
            # 停止事件录制
            if self.event_recorder:
                self.event_recorder.stop_recording()
                logger.info("✅ 事件录制已停止")
            
            # 更新状态
            self.is_monitoring = False
            end_time = datetime.now()
            
            # 计算运行时间
            if self.start_time:
                duration = end_time - self.start_time
                duration_str = str(duration).split('.')[0]  # 移除微秒
            
            # 获取最终统计信息
            stats = self.data_recorder.get_stats()
            
            logger.info(f"""
╔═══════════════════════════════════════╗
║          系统监控已停止                ║
╠═══════════════════════════════════════╣
║  停止时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}           ║
║  运行时间: {duration_str if self.start_time else '未知'}                    ║
║  总事件数: {stats['total_events']}                    ║
║  鼠标点击: {stats['mouse_clicks']}                    ║
║  键盘输入: {stats['keyboard_inputs']}                    ║
║                                       ║
║  数据已保存至: {self.config['data_dir']}             ║
║  截图已保存至: {self.config['screenshot_dir']}             ║
╚═══════════════════════════════════════╝
            """)
            
            # 导出数据摘要
            self.data_recorder.export_summary()
            
            return True
            
        except Exception as e:
            logger.error(f"停止监控失败: {e}")
            return False
    
    def get_status(self):
        """
        获取监控状态
        
        Returns:
            dict: 状态信息
        """
        status = {
            "is_monitoring": self.is_monitoring,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "config": self.config.copy(),
            "stats": self.data_recorder.get_stats()
        }
        
        # 添加各监控器状态
        if self.mouse_monitor:
            status["mouse_monitor"] = self.mouse_monitor.get_status()
        
        if self.keyboard_monitor:
            status["keyboard_monitor"] = self.keyboard_monitor.get_status()
        
        # 添加事件录制器状态
        if self.event_recorder:
            status["event_recorder"] = self.event_recorder.get_status()
        
        return status
    
    def get_recent_events(self, limit=10):
        """
        获取最近的事件
        
        Args:
            limit (int): 限制数量
        
        Returns:
            list: 最近的事件列表
        """
        return self.data_recorder.load_events(limit=limit)
    
    def search_events(self, **kwargs):
        """
        搜索事件
        
        Args:
            **kwargs: 搜索参数（event_type, start_time, end_time, keyword）
        
        Returns:
            list: 匹配的事件列表
        """
        return self.data_recorder.search_events(**kwargs)
    
    def export_data(self, output_file=None, format="json"):
        """
        导出数据
        
        Args:
            output_file (str, optional): 输出文件路径
            format (str): 导出格式（json, csv）
        
        Returns:
            str: 导出文件路径
        """
        if format.lower() == "json":
            return self._export_json(output_file)
        elif format.lower() == "csv":
            return self._export_csv(output_file)
        else:
            raise ValueError(f"不支持的导出格式: {format}")
    
    def _export_json(self, output_file=None):
        """导出JSON格式数据"""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"export_{timestamp}.json"
        
        try:
            # 收集所有事件数据
            all_events = []
            data_files = list(Path(self.config['data_dir']).glob("monitoring_data_*.json"))
            
            for file_path in data_files:
                events = self.data_recorder.load_events(file_path.name)
                all_events.extend(events)
            
            # 创建导出数据
            export_data = {
                "exported_at": datetime.now().isoformat(),
                "total_events": len(all_events),
                "statistics": self.data_recorder.get_stats(),
                "events": all_events
            }
            
            # 保存文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"数据已导出至: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"导出数据失败: {e}")
            return None
    
    def _export_csv(self, output_file=None):
        """导出CSV格式数据"""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"export_{timestamp}.csv"
        
        try:
            import csv
            
            events = self.data_recorder.load_events()
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                if not events:
                    return output_file
                
                # 获取所有字段名
                fieldnames = set()
                for event in events:
                    fieldnames.update(event.keys())
                    if 'position' in event:
                        fieldnames.update([f'position_{k}' for k in event['position'].keys()])
                    if 'screenshots' in event:
                        fieldnames.update([f'screenshots_{k}_{subk}' for k, subdict in event['screenshots'].items() 
                                         for subk in subdict.keys()])
                
                fieldnames = sorted(list(fieldnames))
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                # 写入数据
                for event in events:
                    row = {}
                    for key, value in event.items():
                        if key == 'position' and isinstance(value, dict):
                            for pos_key, pos_value in value.items():
                                row[f'position_{pos_key}'] = pos_value
                        elif key == 'screenshots' and isinstance(value, dict):
                            for scr_key, scr_dict in value.items():
                                for sub_key, sub_value in scr_dict.items():
                                    row[f'screenshots_{scr_key}_{sub_key}'] = sub_value
                        else:
                            row[key] = value
                    
                    writer.writerow(row)
            
            logger.info(f"数据已导出至: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"导出CSV失败: {e}")
            return None
    
    def clear_all_data(self):
        """清空所有数据"""
        self.data_recorder.clear_all_data()
        
        # 清空截图目录
        import shutil
        screenshot_dir = Path(self.config['screenshot_dir'])
        if screenshot_dir.exists():
            shutil.rmtree(screenshot_dir)
            screenshot_dir.mkdir(exist_ok=True)
        
        logger.info("所有数据已清空")


# 示例使用
def main():
    """主函数示例"""
    # 创建监控器
    monitor = SystemMonitor(
        screenshot_dir="screenshots",
        data_dir="data",
        enable_mouse=True,
        enable_keyboard=True,
        keyboard_timeout=3.0
    )
    
    try:
        # 启动监控
        if monitor.start_monitoring():
            # 保持运行
            while monitor.is_monitoring:
                time.sleep(1)
                
                # 可选：定期显示状态
                if int(time.time()) % 30 == 0:  # 每30秒显示一次
                    status = monitor.get_status()
                    stats = status['stats']
                    logger.info(f"📊 运行中... 总事件: {stats['total_events']}, 鼠标: {stats['mouse_clicks']}, 键盘: {stats['keyboard_inputs']}")
    
    except KeyboardInterrupt:
        logger.info("\n收到停止信号...")
    
    finally:
        # 停止监控
        try:
            monitor.stop_monitoring()
        except Exception as e:
            logger.error(f"停止监控时发生错误: {e}")
        
        # 强制退出（如果程序仍然卡住）
        import os
        logger.info("程序即将退出...")
        os._exit(0)


if __name__ == "__main__":
    main()