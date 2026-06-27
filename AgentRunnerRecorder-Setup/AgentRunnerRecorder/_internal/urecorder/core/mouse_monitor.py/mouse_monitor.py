"""
鼠标事件监听模块
监听鼠标点击事件，记录位置、时间戳并截取当前窗口
"""

import threading
import time
from datetime import datetime, timedelta
from pynput import mouse
from loguru import logger
from .screenshot import ScreenshotManager


class MouseMonitor:
    """鼠标事件监控器"""
    
    def __init__(self, screenshot_manager=None, data_callback=None, double_click_interval=0.3):
        """
        初始化鼠标监控器
        
        Args:
            screenshot_manager (ScreenshotManager): 截图管理器实例
            data_callback (callable): 数据回调函数，用于处理记录的鼠标事件数据
            double_click_interval (float): 双击间隔时间（秒），默认0.3秒
        """
        self.screenshot_manager = screenshot_manager or ScreenshotManager()
        self.data_callback = data_callback
        self.mouse_listener = None
        self.is_monitoring = False
        self.click_count = 0
        self.keyboard_monitor = None  # 键盘监控器引用，用于触发会话结束
        
        # 双击检测相关变量
        self.double_click_interval = double_click_interval
        self.last_click_time = None
        self.last_click_position = None
        self.last_click_button = None
        self.click_timer = None
        self.pending_single_click = None
        
        # 线程锁
        self._lock = threading.Lock()
    
    def on_click(self, x, y, button, pressed):
        """
        鼠标点击事件处理函数
        
        Args:
            x, y (float): 鼠标点击位置
            button: 鼠标按钮
            pressed (bool): 是否按下（True为按下，False为释放）
        """
        if not pressed:  # 只记录点击释放事件
            return
        
        try:
            current_time = datetime.now()
            
            with self._lock:
                # 检查是否是双击
                is_double_click = False
                
                if (self.last_click_time and 
                    self.last_click_position and 
                    self.last_click_button and
                    button == self.last_click_button):
                    logger.info(f"is_double_click---------1")
                    # 检查时间间隔
                    time_diff = (current_time - self.last_click_time).total_seconds()
                    position_diff = abs(x - self.last_click_position[0]) + abs(y - self.last_click_position[1])
                    logger.info(f"is_double_click---------{time_diff}----{position_diff}")
                    # 如果在双击间隔内且位置相近，则认为是双击
                    if time_diff <= self.double_click_interval and position_diff < 10:
                        is_double_click = True
                
                logger.info(f"is_double_click={is_double_click}")
                if is_double_click:
                    # 双击事件 - 取消待处理的单击事件
                    if self.click_timer:
                        self.click_timer.cancel()
                        self.click_timer = None
                    
                    # 记录双击
                    self.click_count += 1
                    
                    # 截取当前激活窗口
                    screenshot_result = self.screenshot_manager.capture_cursor_position(
                        int(x), int(y), mode="active_window"
                    )
                    
                    # 构建双击事件数据
                    event_data = {
                        "event_type": "mouse_double_click",
                        "timestamp": current_time.isoformat(),
                        "position": {
                            "x": int(x),
                            "y": int(y)
                        },
                        "button": str(button),
                        "click_count": self.click_count,
                        "screenshot": {
                            "success": screenshot_result["success"],
                            "filepath": screenshot_result.get("filepath", ""),
                            "filename": screenshot_result.get("filename", "")
                        },
                        "window_info": screenshot_result.get("window_info", {}),
                        "click_interval": time_diff if 'time_diff' in locals() else 0
                    }
                    
                    # 触发键盘会话结束（如果存在键盘监控器）
                    if self.keyboard_monitor:
                        self.keyboard_monitor.trigger_session_end("mouse_double_click")
                    
                    # 调用回调函数处理数据
                    if self.data_callback:
                        try:
                            self.data_callback(event_data)
                        except Exception as e:
                            logger.error(f"数据回调函数执行错误: {e}")
                    
                    logger.info(f"鼠标双击记录: 位置({int(x)}, {int(y)}), 时间: {current_time.strftime('%H:%M:%S.%f')[:-3]}")
                    
                    # 清除双击检测状态
                    self.last_click_time = None
                    self.last_click_position = None
                    self.last_click_button = None
                    
                else:
                    # 可能是单击事件，启动延迟定时器
                    self.last_click_time = current_time
                    self.last_click_position = (x, y)
                    self.last_click_button = button
                    
                    # 取消之前的单击定时器
                    if self.click_timer:
                        self.click_timer.cancel()
                    
                    # 创建新的单击定时器
                    self.click_timer = threading.Timer(
                        self.double_click_interval, 
                        self._process_single_click,
                        args=[x, y, button, current_time]
                    )
                    self.click_timer.start()
                    
        except Exception as e:
            logger.error(f"鼠标点击事件处理错误: {e}")
    
    def _process_single_click(self, x, y, button, timestamp):
        """
        处理单击事件（在双击间隔后触发）
        
        Args:
            x, y (float): 鼠标点击位置
            button: 鼠标按钮
            timestamp (datetime): 点击时间戳
        """
        try:
            with self._lock:
                # 确认这是单击（没有被双击取消）
                if self.last_click_time and abs((timestamp - self.last_click_time).total_seconds()) < self.double_click_interval + 0.1:
                    self.click_count += 1
                    
                    # 截取当前激活窗口
                    screenshot_result = self.screenshot_manager.capture_cursor_position(
                        int(x), int(y), mode="active_window"
                    )
                    
                    # 构建单击事件数据
                    event_data = {
                        "event_type": "mouse_single_click",
                        "timestamp": timestamp.isoformat(),
                        "position": {
                            "x": int(x),
                            "y": int(y)
                        },
                        "button": str(button),
                        "click_count": self.click_count,
                        "screenshot": {
                            "success": screenshot_result["success"],
                            "filepath": screenshot_result.get("filepath", ""),
                            "filename": screenshot_result.get("filename", "")
                        },
                        "window_info": screenshot_result.get("window_info", {})
                    }
                    
                    # 触发键盘会话结束（如果存在键盘监控器）
                    if self.keyboard_monitor:
                        self.keyboard_monitor.trigger_session_end("mouse_single_click")
                    
                    # 调用回调函数处理数据
                    if self.data_callback:
                        try:
                            self.data_callback(event_data)
                        except Exception as e:
                            logger.error(f"数据回调函数执行错误: {e}")
                    
                    logger.info(f"鼠标单击记录: 位置({int(x)}, {int(y)}), 时间: {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
                    
                    # 清除状态，准备下一次点击
                    self.last_click_time = None
                    self.last_click_position = None
                    self.last_click_button = None
                    
        except Exception as e:
            logger.error(f"处理单击事件错误: {e}")
    
    def on_click_old(self, x, y, button, pressed):
        """
        鼠标点击事件处理函数（保留向后兼容的旧版本）
        
        Args:
            x, y (float): 鼠标点击位置
            button: 鼠标按钮
            pressed (bool): 是否按下（True为按下，False为释放）
        """
        if not pressed:  # 只记录点击释放事件
            return
        
        try:
            with self._lock:
                self.click_count += 1
                timestamp = datetime.now()
                
                # 截取当前激活窗口
                screenshot_result = self.screenshot_manager.capture_cursor_position(
                    int(x), int(y), mode="active_window"
                )
                
                # 构建事件数据
                event_data = {
                    "event_type": "mouse_click",
                    "timestamp": timestamp.isoformat(),
                    "position": {
                        "x": int(x),
                        "y": int(y)
                    },
                    "button": str(button),
                    "click_count": self.click_count,
                    "screenshot": {
                        "success": screenshot_result["success"],
                        "filepath": screenshot_result.get("filepath", ""),
                        "filename": screenshot_result.get("filename", "")
                    },
                    "window_info": screenshot_result.get("window_info", {})
                }
                
                # 触发键盘会话结束（如果存在键盘监控器）
                if self.keyboard_monitor:
                    self.keyboard_monitor.trigger_session_end("mouse_click")
                
                # 调用回调函数处理数据
                if self.data_callback:
                    try:
                        self.data_callback(event_data)
                    except Exception as e:
                        logger.error(f"数据回调函数执行错误: {e}")
                
                logger.info(f"鼠标点击记录: 位置({int(x)}, {int(y)}), 时间: {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
                
        except Exception as e:
            logger.error(f"鼠标点击事件处理错误: {e}")
    
    def start_monitoring(self):
        """开始监听鼠标事件"""
        if self.is_monitoring:
            logger.warning("鼠标监控已在运行中")
            return False
        
        try:
            # 创建鼠标监听器
            self.mouse_listener = mouse.Listener(
                on_click=self.on_click,
                suppress=False
            )
            
            # 启动监听器
            self.mouse_listener.start()
            self.is_monitoring = True
            
            logger.info("鼠标事件监控已启动")
            return True
            
        except Exception as e:
            logger.error(f"启动鼠标监控失败: {e}")
            self.is_monitoring = False
            return False
    
    def stop_monitoring(self):
        """停止监听鼠标事件"""
        if not self.is_monitoring:
            logger.warning("鼠标监控未在运行")
            return
        
        try:
            # 取消待处理的单击定时器
            if self.click_timer:
                self.click_timer.cancel()
                self.click_timer = None
            
            if self.mouse_listener:
                # 先停止监听器
                self.mouse_listener.stop()
                
                # 等待监听器完全停止（最多等待2秒）
                import time
                wait_count = 0
                while self.mouse_listener.is_alive() and wait_count < 20:
                    time.sleep(0.1)
                    wait_count += 1
                
                # 如果监听器仍然活跃，强制清理
                if self.mouse_listener.is_alive():
                    logger.warning("鼠标监听器未正常停止，强制清理")
                
                self.mouse_listener = None
            
            self.is_monitoring = False
            logger.info("鼠标事件监控已停止")
            
        except Exception as e:
            logger.error(f"停止鼠标监控失败: {e}")
            # 即使出错也要清理状态
            self.is_monitoring = False
            self.mouse_listener = None
            self.click_timer = None
    
    def get_status(self):
        """
        获取监控状态
        
        Returns:
            dict: 监控状态信息
        """
        return {
            "is_monitoring": self.is_monitoring,
            "click_count": self.click_count,
            "listener_active": self.mouse_listener is not None if self.mouse_listener else False,
            "double_click_interval": self.double_click_interval,
            "has_pending_single_click": self.click_timer is not None,
            "last_click_time": self.last_click_time.isoformat() if self.last_click_time else None,
            "last_click_position": self.last_click_position
        }
    
    def reset_count(self):
        """重置点击计数"""
        with self._lock:
            self.click_count = 0
    
    def reset_click_detection(self):
        """
        重置双击检测状态
        """
        with self._lock:
            self.last_click_time = None
            self.last_click_position = None
            self.last_click_button = None
            if self.click_timer:
                self.click_timer.cancel()
                self.click_timer = None
    
    def set_double_click_interval(self, interval):
        """
        设置双击间隔时间
        
        Args:
            interval (float): 双击间隔时间（秒）
        """
        if interval <= 0:
            raise ValueError("双击间隔时间必须大于0")
        
        with self._lock:
            self.double_click_interval = interval
            # 如果有等待的单击事件，重新设置定时器
            if self.click_timer and self.last_click_time and self.last_click_position and self.last_click_button:
                # 取消旧的定时器
                old_timer = self.click_timer
                self.click_timer = None
                
                # 创建新的定时器
                self.click_timer = threading.Timer(
                    self.double_click_interval,
                    self._process_single_click,
                    args=[
                        self.last_click_position[0],
                        self.last_click_position[1],
                        self.last_click_button,
                        self.last_click_time
                    ]
                )
                self.click_timer.start()
                
                logger.info(f"双击间隔时间已更新为: {interval}秒")


# 测试函数
def test_mouse_monitor():
    """测试鼠标监控功能（支持单击和双击）"""
    def data_handler(data):
        """数据处理回调函数"""
        event_type = data['event_type']
        logger.info(f"接收到鼠标事件数据: {event_type}")
        logger.info(f"  位置: ({data['position']['x']}, {data['position']['y']})")
        logger.info(f"  时间: {data['timestamp']}")
        logger.info(f"  按钮: {data['button']}")
        logger.info(f"  截图: {data['screenshot']['success']}")
        if data['screenshot']['success']:
            logger.info(f"  截图文件: {data['screenshot']['filepath']}")
        
        # 显示双击特有的信息
        if event_type == "mouse_double_click":
            logger.info(f"  双击间隔: {data.get('click_interval', 0):.3f}秒")
        
        logger.info("-" * 50)
    
    # 创建监控器，设置双击间隔为0.3秒
    monitor = MouseMonitor(data_callback=data_handler, double_click_interval=0.3)
    
    logger.info("开始测试鼠标监控功能（单击和双击）...")
    logger.info("请在屏幕上进行以下测试:")
    logger.info("1. 单击鼠标 - 应该记录为 mouse_single_click")
    logger.info("2. 双击鼠标 - 应该记录为 mouse_double_click（不会触发单击）")
    logger.info("3. 按Ctrl+C停止测试")
    logger.info(f"双击间隔时间: {monitor.double_click_interval}秒")
    logger.info("-" * 50)
    
    try:
        monitor.start_monitoring()
        
        # 保持主线程运行
        import time
        while True:
            time.sleep(1)
            status = monitor.get_status()
            logger.info(f"监控状态: {status}")
            
    except KeyboardInterrupt:
        logger.info("\n正在停止监控...")
        monitor.stop_monitoring()
        logger.info("测试结束")


def test_backward_compatibility():
    """测试向后兼容性（使用旧的事件类型）"""
    def old_style_handler(data):
        """旧样式的数据处理回调函数"""
        logger.info(f"旧样式事件: {data['event_type']}")
        logger.info(f"  位置: ({data['position']['x']}, {data['position']['y']})")
        logger.info(f"  时间: {data['timestamp']}")
        logger.info("-" * 30)
    
    # 创建使用旧事件类型的监控器
    monitor = MouseMonitor(data_callback=old_style_handler)
    
    # 临时使用旧的事件处理方法
    monitor.on_click = monitor.on_click_old
    
    logger.info("开始测试向后兼容性...")
    logger.info("使用旧的事件处理方法")
    logger.info("按Ctrl+C停止测试")
    
    try:
        monitor.start_monitoring()
        
        import time
        while True:
            time.sleep(1)
            status = monitor.get_status()
            logger.info(f"监控状态: {status}")
            
    except KeyboardInterrupt:
        logger.info("\n正在停止监控...")
        monitor.stop_monitoring()
        logger.info("向后兼容性测试结束")


def test_click_detection_accuracy():
    """测试点击检测准确性"""
    def data_handler(data):
        """数据处理回调函数"""
        logger.info(f"事件类型: {data['event_type']}")
        logger.info(f"时间: {data['timestamp']}")
        logger.info(f"位置: ({data['position']['x']}, {data['position']['y']})")
        logger.info(f"按钮: {data['button']}")
        
        if data['event_type'] == "mouse_double_click":
            logger.info(f"双击间隔: {data.get('click_interval', 0):.3f}秒")
        
        logger.info("-" * 40)
    
    # 创建监控器
    monitor = MouseMonitor(data_callback=data_handler, double_click_interval=0.4)
    
    logger.info("开始测试点击检测准确性...")
    logger.info("测试场景:")
    logger.info("1. 快速双击 - 应该识别为双击")
    logger.info("2. 慢速双击 - 应该识别为两个单击")
    logger.info("3. 远距离双击 - 应该识别为两个单击")
    logger.info(f"双击间隔时间: {monitor.double_click_interval}秒")
    logger.info("按Ctrl+C停止测试")
    
    try:
        monitor.start_monitoring()
        
        import time
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n正在停止监控...")
        monitor.stop_monitoring()
        logger.info("点击检测准确性测试结束")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_mode = sys.argv[1].lower()
        
        if test_mode == "single":
            test_mouse_monitor()
        elif test_mode == "compatibility":
            test_backward_compatibility()
        elif test_mode == "accuracy":
            test_click_detection_accuracy()
        else:
            print("使用方法:")
            print("  python mouse_monitor.py single      # 测试单击和双击功能")
            print("  python mouse_monitor.py compatibility # 测试向后兼容性")
            print("  python mouse_monitor.py accuracy     # 测试点击检测准确性")
            print("  python mouse_monitor.py              # 默认测试单击和双击功能")
    else:
        test_mouse_monitor()