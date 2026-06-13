"""
键盘事件监听模块
监听键盘输入事件，记录3秒内的所有输入字符串，并截取首尾字符对应的图片
"""

import threading
import time
import platform
from datetime import datetime, timedelta
from collections import deque
from pynput import keyboard
from loguru import logger
from .screenshot import ScreenshotManager


class KeyboardMonitor:
    """键盘事件监控器"""
    
    @staticmethod
    def _execute_with_timeout(func, timeout_seconds=1.0, *args, **kwargs):
        """
        跨平台超时执行函数
        
        Args:
            func: 要执行的函数
            timeout_seconds: 超时时间（秒）
            *args, **kwargs: 函数参数
            
        Returns:
            tuple: (result, error) - 结果和错误信息
        """
        result = [None]
        error = [None]
        exception = [None]
        
        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        # 启动线程执行函数
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout_seconds)
        
        # 检查是否超时
        if thread.is_alive():
            # 超时了，返回None结果
            return None, f"函数执行超时 ({timeout_seconds}秒)"
        
        # 检查是否有异常
        if exception[0]:
            return None, str(exception[0])
        
        return result[0], None
    
    def __init__(self, screenshot_manager=None, data_callback=None, input_timeout=3.0):
        """
        初始化键盘监控器
        
        Args:
            screenshot_manager (ScreenshotManager): 截图管理器实例
            data_callback (callable): 数据回调函数，用于处理记录的键盘事件数据
            input_timeout (float): 输入超时时间（秒），超过此时间则认为输入结束
        """
        self.screenshot_manager = screenshot_manager or ScreenshotManager()
        self.data_callback = data_callback
        self.input_timeout = input_timeout
        self.keyboard_listener = None
        self.is_monitoring = False
        
        # 输入缓冲区
        self.input_buffer = deque()
        self.last_input_time = None
        self.input_session_id = 0
        
        # 线程锁
        self._lock = threading.Lock()
        
        # 定时器用于处理输入超时
        self.timeout_timer = None
        
        # 会话结束原因
        self.session_end_reason = None
    
    def _get_current_cursor_position(self):
        """
        获取当前光标位置（模拟实现）
        
        Returns:
            tuple: (x, y) 坐标位置
        """
        try:
            # 使用psutil获取屏幕信息，避免tkinter依赖
            import psutil
            screen_width = psutil.virtual_memory().total // (1024 * 1024)  # 简化的屏幕宽度估算
            screen_height = psutil.virtual_memory().available // (1024 * 1024)  # 简化的屏幕高度估算
            
            # 如果估算值不合理，使用默认值
            if screen_width < 100 or screen_height < 100:
                return (1920, 1080)  # 默认Full HD分辨率
            
            return (screen_width // 2, screen_height // 2)
        except:
            # 如果psutil不可用，返回默认位置
            return (1920, 1080)  # 使用常见的Full HD分辨率
    
    def trigger_session_end(self, reason="external"):
        """
        触发当前输入会话的结束（公共方法）
        
        Args:
            reason (str): 结束原因，如 "tab_key", "mouse_click", "external", "timeout"
        """
        # 直接调用_process_input_session，避免死锁
        self._process_input_session(reason)
    
    def _quick_process_input_session(self):
        """快速处理输入会话（停止时使用，不等待截图）"""
        # 先在锁内提取数据
        session_data, has_data = self._extract_session_data("stopped")
        
        if not has_data:
            return
        
        try:
            # 构建快速事件数据（不包含截图）
            event_data = {
                "event_type": "keyboard_input",
                "session_id": session_data["session_id"],
                "timestamp": session_data["end_time"].isoformat(),
                "start_time": session_data["start_time"].isoformat() if session_data["start_time"] else None,
                "end_time": session_data["end_time"].isoformat(),
                "duration_seconds": (session_data["end_time"] - session_data["start_time"]).total_seconds() if session_data["start_time"] else 0,
                "end_reason": "stopped",
                "input_string": session_data["input_string"],
                "input_length": len(session_data["input_string"]),
                "first_char": session_data["input_string"][0] if session_data["input_string"] else "",
                "last_char": session_data["input_string"][-1] if session_data["input_string"] else "",
                "cursor_position": {"x": 0, "y": 0},  # 默认位置
                "screenshots": {
                    "first_char": {"success": False, "filepath": "", "filename": ""},
                    "last_char": {"success": False, "filepath": "", "filename": ""}
                },
                "window_info": {}
            }
            
            # 调用回调函数处理数据
            if self.data_callback:
                try:
                    self.data_callback(event_data)
                except Exception as e:
                    logger.error(f"数据回调函数执行错误: {e}")
            
            logger.info(f"快速处理键盘输入: '{session_data['input_string']}' (长度: {len(session_data['input_string'])}, 结束原因: stopped)")
            
        except Exception as e:
            logger.error(f"快速处理输入会话时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _extract_session_data(self, reason=None):
        """
        在锁内提取会话数据（避免死锁）
        
        Returns:
            tuple: (session_data, has_data) - 会话数据和是否有有效数据
        """
        if not self.input_buffer:
            logger.debug("输入会话处理：无内容可处理")
            return None, False
        
        # 获取会话结束原因
        end_reason = reason or self.session_end_reason or "timeout"
        self.session_end_reason = None  # 重置原因
        
        # 获取输入内容
        input_chars = list(self.input_buffer)
        input_string = ''.join(input_chars)
        
        logger.info(f"🔄 开始处理输入会话，结束原因: {end_reason}")
        logger.info(f"📝 输入内容: '{input_string}' (长度: {len(input_string)})")
        
        if not input_string.strip():
            # 跳过空白输入
            logger.info("ℹ️ 输入内容为空或只有空白字符，跳过处理")
            self.input_buffer.clear()
            self.last_input_time = None
            return None, False
        
        # 生成会话ID
        session_id = self.input_session_id
        self.input_session_id += 1
        
        # 记录开始和结束时间
        start_time = self.last_input_time
        end_time = datetime.now()
        
        # 获取光标位置
        cursor_x, cursor_y = self._get_current_cursor_position()
        
        # 清空缓冲区（锁内操作）
        self.input_buffer.clear()
        self.last_input_time = None
        
        # 构建基础会话数据（锁外处理耗时操作）
        session_data = {
            "session_id": session_id,
            "end_reason": end_reason,
            "input_string": input_string,
            "start_time": start_time,
            "end_time": end_time,
            "cursor_x": cursor_x,
            "cursor_y": cursor_y
        }
        
        return session_data, True

    def _process_input_session(self, reason=None):
        """处理输入会话超时或提前结束（重构版本，避免死锁）"""
        # 先在锁内提取数据
        session_data, has_data = self._extract_session_data(reason)
        
        if not has_data:
            return
        
        # 锁外处理耗时操作（截图、回调等）
        try:
            # 截取首字符图片（带超时保护）
            first_char = session_data["input_string"][0] if session_data["input_string"] else ""
            first_screenshot = None
            if first_char:
                try:
                    # 使用跨平台超时执行
                    first_screenshot, error = self._execute_with_timeout(
                        self.screenshot_manager.capture_cursor_position,
                        0.5,  # 0.5秒超时
                        session_data["cursor_x"], session_data["cursor_y"], mode="active_window", 
                        filename=f"keyboard_first_{session_data['session_id']}_{int(time.time()*1000)}.png"
                    )
                    if error:
                        logger.warning(f"首字符截图超时: {error}")
                        first_screenshot = {"success": False, "filepath": "", "filename": ""}
                except Exception as e:
                    logger.warning(f"首字符截图失败: {e}")
                    first_screenshot = {"success": False, "filepath": "", "filename": ""}
            
            # 截取末字符图片（带超时保护）
            last_char = session_data["input_string"][-1] if session_data["input_string"] else ""
            last_screenshot = None
            if last_char:
                try:
                    # 使用跨平台超时执行
                    last_screenshot, error = self._execute_with_timeout(
                        self.screenshot_manager.capture_cursor_position,
                        0.5,  # 0.5秒超时
                        session_data["cursor_x"], session_data["cursor_y"], mode="active_window",
                        filename=f"keyboard_last_{session_data['session_id']}_{int(time.time()*1000)}.png"
                    )
                    if error:
                        logger.warning(f"末字符截图超时: {error}")
                        last_screenshot = {"success": False, "filepath": "", "filename": ""}
                except Exception as e:
                    logger.warning(f"末字符截图失败: {e}")
                    last_screenshot = {"success": False, "filepath": "", "filename": ""}
            
            # 构建完整事件数据
            event_data = {
                "event_type": "keyboard_input",
                "session_id": session_data["session_id"],
                "timestamp": session_data["end_time"].isoformat(),
                "start_time": session_data["start_time"].isoformat() if session_data["start_time"] else None,
                "end_time": session_data["end_time"].isoformat(),
                "duration_seconds": (session_data["end_time"] - session_data["start_time"]).total_seconds() if session_data["start_time"] else 0,
                "end_reason": session_data["end_reason"],
                "input_string": session_data["input_string"],
                "input_length": len(session_data["input_string"]),
                "first_char": first_char,
                "last_char": last_char,
                "cursor_position": {
                    "x": session_data["cursor_x"],
                    "y": session_data["cursor_y"]
                },
                "screenshots": {
                    "first_char": {
                        "success": first_screenshot["success"] if first_screenshot else False,
                        "filepath": first_screenshot.get("filepath", "") if first_screenshot else "",
                        "filename": first_screenshot.get("filename", "") if first_screenshot else ""
                    },
                    "last_char": {
                        "success": last_screenshot["success"] if last_screenshot else False,
                        "filepath": last_screenshot.get("filepath", "") if last_screenshot else "",
                        "filename": last_screenshot.get("filename", "") if last_screenshot else ""
                    }
                },
                "window_info": first_screenshot.get("window_info", {}) if first_screenshot else {}
            }
            
            # 调用回调函数处理数据（带超时保护）
            if self.data_callback:
                try:
                    # 使用跨平台超时执行
                    result, error = self._execute_with_timeout(
                        self.data_callback,
                        0.3,  # 0.3秒超时
                        event_data
                    )
                    if error:
                        logger.warning(f"数据回调函数执行超时: {error}")
                except Exception as e:
                    logger.error(f"数据回调函数执行错误: {e}")
            
            logger.info(f"✅ 键盘输入记录完成: '{session_data['input_string']}' (长度: {len(session_data['input_string'])}, 结束原因: {session_data['end_reason']}, 会话ID: {session_data['session_id']})")
            
        except Exception as e:
            logger.error(f"处理输入会话时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _handle_special_key(self, key):
        """
        处理特殊按键，包括数字小键盘
        
        Args:
            key: 按键对象
            
        Returns:
            str or None: 对应的字符，如果无法处理则返回None
        """
        try:
            # 首先尝试从key.char获取字符（这是最常见的情况）
            if hasattr(key, 'char') and key.char:
                char = key.char
                logger.debug(f"从char属性获取字符: '{key}' -> '{char}'")
                return char
            
            # 数字小键盘虚拟键码映射（Windows系统）
            numpad_vk_mapping = {
                96: '0',   # VK_NUMPAD0
                97: '1',   # VK_NUMPAD1 - 这是日志中显示的按键
                98: '2',   # VK_NUMPAD2
                99: '3',   # VK_NUMPAD3
                100: '4',  # VK_NUMPAD4
                101: '5',  # VK_NUMPAD5
                102: '6',  # VK_NUMPAD6
                103: '7',  # VK_NUMPAD7
                104: '8',  # VK_NUMPAD8
                105: '9',  # VK_NUMPAD9
                107: '+',  # VK_ADD
                109: '-',  # VK_SUBTRACT
                106: '*',  # VK_MULTIPLY
                111: '/',  # VK_DIVIDE
                110: '.',  # VK_DECIMAL
                13: '\n',  # VK_RETURN (回车)
            }
            
            # 数字小键盘按键名称映射
            numpad_name_mapping = {
                'numpad0': '0', 'numpad1': '1', 'numpad2': '2', 'numpad3': '3',
                'numpad4': '4', 'numpad5': '5', 'numpad6': '6', 'numpad7': '7',
                'numpad8': '8', 'numpad9': '9', 'numpad_add': '+', 'numpad_subtract': '-',
                'numpad_multiply': '*', 'numpad_divide': '/', 'numpad_decimal': '.', 'numpad_enter': '\n'
            }
            
            # 检查其他特殊按键
            if key == keyboard.Key.space:
                logger.debug(f"空格键识别: '{key}' -> ' '")
                return ' '
            elif key == keyboard.Key.enter:
                logger.debug(f"回车键识别: '{key}' -> '\\n'")
                return '\n'
            elif key == keyboard.Key.tab:
                # TAB键特殊处理，不在这里返回字符
                logger.debug(f"TAB键检测到（特殊处理）: {key}")
                return None
            elif key == keyboard.Key.backspace or key == keyboard.Key.delete:
                # DELETE键特殊处理，不在这里返回字符
                logger.debug(f"DELETE键检测到（特殊处理）: {key}")
                return None
            
            # 优先检查虚拟键码（vk属性）- 这是处理数字小键盘的关键
            if hasattr(key, 'vk') and key.vk is not None:
                vk = key.vk
                logger.debug(f"检查虚拟键码: vk={vk}")
                if vk in numpad_vk_mapping:
                    char = numpad_vk_mapping[vk]
                    logger.debug(f"从虚拟键码映射识别数字小键盘: vk {vk} -> '{char}'")
                    return char
            
            # 尝试从key.name获取字符
            if hasattr(key, 'name') and key.name:
                name = key.name
                logger.debug(f"从name属性获取: '{key}' -> name: '{name}'")
                
                # 直接映射name到字符
                if name in numpad_name_mapping:
                    char = numpad_name_mapping[name]
                    logger.debug(f"数字小键盘按键识别: name '{name}' -> '{char}'")
                    return char
                
                # 处理其他常见的按键名称
                if name == 'space':
                    return ' '
                elif name == 'enter':
                    return '\n'
                elif name == 'add':
                    return '+'
                elif name == 'subtract':
                    return '-'
                elif name == 'multiply':
                    return '*'
                elif name == 'divide':
                    return '/'
                elif name == 'decimal':
                    return '.'
            
            # 检查按键的字符串表示（处理 <97> 格式）
            key_str = str(key)
            logger.debug(f"检查按键字符串表示: '{key}' -> str: '{key_str}'")
            
            # 处理 <数字> 格式的虚拟键码表示
            if key_str.startswith('<') and key_str.endswith('>'):
                try:
                    vk_code = int(key_str[1:-1])  # 移除 < 和 >，转换为数字
                    logger.debug(f"从字符串提取虚拟键码: {vk_code}")
                    if vk_code in numpad_vk_mapping:
                        char = numpad_vk_mapping[vk_code]
                        logger.debug(f"从字符串虚拟键码映射识别: {vk_code} -> '{char}'")
                        return char
                except ValueError:
                    logger.debug(f"无法解析虚拟键码字符串: {key_str}")
            
            # 尝试从字符串表示中提取信息
            if key_str.startswith('Key.'):
                key_name = key_str[4:]  # 移除 'Key.' 前缀
                if key_name in numpad_name_mapping:
                    char = numpad_name_mapping[key_name]
                    logger.debug(f"从字符串表示识别数字小键盘: '{key_name}' -> '{char}'")
                    return char
            
            # 尝试从字符串表示中提取数字
            if key_str.isdigit():
                logger.debug(f"从字符串表示获取数字: '{key_str}' -> '{key_str}'")
                return key_str
            
            # 尝试从字符串表示中提取单个字符
            if len(key_str) == 1:
                logger.debug(f"从字符串表示获取字符: '{key_str}' -> '{key_str}'")
                return key_str
            
            # 无法处理的按键
            logger.debug(f"无法处理的特殊按键: {key} (类型: {type(key).__name__}, str: '{key_str}')")
            return None
            
        except Exception as e:
            logger.debug(f"处理特殊按键时出错: {key}, 错误: {e}")
            return None

    def _reset_timeout_timer(self):
        """重置超时定时器"""
        if self.timeout_timer:
            self.timeout_timer.cancel()
        
        self.timeout_timer = threading.Timer(self.input_timeout, self._process_input_session)
        self.timeout_timer.start()
    
    def on_press(self, key):
        """
        键盘按下事件处理函数
        
        Args:
            key: 按键对象
        """
        try:
            with self._lock:
                current_time = datetime.now()
                
                # 处理特殊按键
                if key == keyboard.Key.space:
                    char = ' '
                elif key == keyboard.Key.enter:
                    char = '\n'
                elif key == keyboard.Key.tab:
                    # TAB键触发会话结束
                    logger.info(f"🔄 Tab键按下检测到，当前缓冲区长度: {len(self.input_buffer)}")
                    if self.input_buffer:
                        # 获取即将处理的输入内容用于日志
                        pending_input = ''.join(self.input_buffer)
                        logger.info(f"📝 Tab键触发会话结束，输入内容: '{pending_input}' (长度: {len(pending_input)})")
                        # 先释放锁，然后处理会话（避免自死锁）
                        self._process_input_session(reason="tab_key")
                        logger.info(f"✅ Tab键会话处理完成，缓冲区已清空")
                    else:
                        logger.info("ℹ️ Tab键按下，但缓冲区为空，无需处理")
                    # TAB键本身不添加到缓冲区
                    return
                elif key == keyboard.Key.backspace or key == keyboard.Key.delete:
                    # DELETE键移除上一个字符
                    if self.input_buffer:
                        removed_char = self.input_buffer.pop()
                        logger.debug(f"DELETE键移除字符: '{removed_char}', 剩余长度: {len(self.input_buffer)}")
                    # DELETE键本身不添加到缓冲区
                    return
                elif hasattr(key, 'char') and key.char:
                    char = key.char
                else:
                    # 处理数字小键盘和其他特殊按键
                    char = self._handle_special_key(key)
                    if char is None:
                        # 跳过无法处理的特殊按键
                        return
                
                # 添加到输入缓冲区
                self.input_buffer.append(char)
                
                # 更新最后输入时间
                if self.last_input_time is None:
                    self.last_input_time = current_time
                
                # 重置超时定时器
                self._reset_timeout_timer()
                
        except AttributeError:
            # 忽略无法处理的按键
            pass
        except Exception as e:
            logger.error(f"键盘按下事件处理错误: {e}")
    
    def on_release(self, key):
        """
        键盘释放事件处理函数
        
        Args:
            key: 按键对象
        """
        # 检查是否应该停止监控
        if key == keyboard.Key.esc:
            # 可以在这里添加停止逻辑，但通常由外部控制
            pass
    
    def start_monitoring(self):
        """开始监听键盘事件"""
        if self.is_monitoring:
            logger.warning("键盘监控已在运行中")
            return False
        
        try:
            # 创建键盘监听器
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_press,
                on_release=self.on_release,
                suppress=False
            )
            
            # 启动监听器
            self.keyboard_listener.start()
            self.is_monitoring = True
            
            logger.info("键盘事件监控已启动")
            return True
            
        except Exception as e:
            logger.error(f"启动键盘监控失败: {e}")
            self.is_monitoring = False
            return False
    
    def stop_monitoring(self):
        """停止监听键盘事件"""
        if not self.is_monitoring:
            logger.warning("键盘监控未在运行")
            return
        
        try:
            # 立即取消定时器
            if self.timeout_timer:
                self.timeout_timer.cancel()
                self.timeout_timer = None
            
            # 立即停止监听器
            if self.keyboard_listener:
                try:
                    # 立即停止监听器
                    self.keyboard_listener.stop()
                except Exception as e:
                    logger.warning(f"停止键盘监听器时出错: {e}")
                
                # 强制清理监听器引用
                self.keyboard_listener = None
            
            # 处理剩余的输入会话（快速处理，无超时保护）
            try:
                # 快速处理，不等待截图
                self._quick_process_input_session()
            except Exception as e:
                logger.warning(f"快速处理输入会话时出错: {e}")
            
            self.is_monitoring = False
            logger.info("键盘事件监控已停止")
            
        except Exception as e:
            logger.error(f"停止键盘监控失败: {e}")
            # 即使出错也要清理状态
            self.is_monitoring = False
            self.keyboard_listener = None
            self.is_monitoring = False
            self.keyboard_listener = None
            self.timeout_timer = None
    
    def get_status(self):
        """
        获取监控状态
        
        Returns:
            dict: 监控状态信息
        """
        return {
            "is_monitoring": self.is_monitoring,
            "buffer_length": len(self.input_buffer),
            "session_id": self.input_session_id,
            "listener_active": self.keyboard_listener is not None if self.keyboard_listener else False,
            "has_pending_input": len(self.input_buffer) > 0
        }
    
    def clear_buffer(self):
        """清空输入缓冲区"""
        with self._lock:
            self.input_buffer.clear()
            self.last_input_time = None


# 测试函数
def test_keyboard_monitor():
    """测试键盘监控功能"""
    def data_handler(data):
        """数据处理回调函数"""
        logger.info(f"接收到键盘事件数据: {data['event_type']}")
        logger.info(f"  会话ID: {data['session_id']}")
        logger.info(f"  输入内容: '{data['input_string']}'")
        logger.info(f"  长度: {data['input_length']}")
        logger.info(f"  首字符: '{data['first_char']}'")
        logger.info(f"  末字符: '{data['last_char']}'")
        logger.info(f"  持续时间: {data['duration_seconds']:.2f}秒")
        logger.info(f"  首字符截图: {data['screenshots']['first_char']['success']}")
        logger.info(f"  末字符截图: {data['screenshots']['last_char']['success']}")
        logger.info("-" * 50)
    
    # 创建监控器
    monitor = KeyboardMonitor(data_callback=data_handler, input_timeout=3.0)
    
    logger.info("开始测试键盘监控功能...")
    logger.info("请在键盘上输入内容进行测试（按Ctrl+C停止）")
    logger.info("输入会每3秒或停止输入时自动记录")
    
    try:
        monitor.start_monitoring()
        
        # 保持主线程运行
        import time
        while True:
            time.sleep(1)
            status = monitor.get_status()
            status = monitor.get_status()
            logger.info(f"监控状态: {status}")
            
    except KeyboardInterrupt:
        logger.info("\n正在停止监控...")
        monitor.stop_monitoring()
        logger.info("测试结束")


if __name__ == "__main__":
    test_keyboard_monitor()