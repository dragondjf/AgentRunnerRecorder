"""
屏幕截图功能模块
实现对当前激活窗口的截图功能
"""

import os
import sys
import time
from datetime import datetime
# === 高 DPI 支持（必须放在最前面！）===

import ctypes
if sys.platform == "win32":
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            ctypes.windll.user32.SetProcessDPIAware()
    except:
        logger.warn("Failed to set process DPI")
        pass

from PIL import Image, ImageGrab
import psutil
import platform
from loguru import logger


class ScreenshotManager:
    """屏幕截图管理器"""
    
    def __init__(self, output_dir="screenshots"):
        """
        初始化截图管理器
        
        Args:
            output_dir (str): 截图保存目录
        """
        self.output_dir = output_dir
        self.ensure_output_dir()
    
    def ensure_output_dir(self):
        """确保输出目录存在"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def get_active_window_info(self):
        """
        获取当前激活窗口信息
        
        Returns:
            dict: 窗口信息，包含标题和进程信息
        """
        try:
            system = platform.system()
            window_info = {
                "system": system,
                "timestamp": datetime.now().isoformat()
            }
            
            if system == "Windows":
                # Windows系统
                import win32gui
                import win32process
                
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    window_title = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    
                    try:
                        process = psutil.Process(pid)
                        process_name = process.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        process_name = "Unknown"
                    
                    window_info.update({
                        "title": window_title,
                        "hwnd": hwnd,
                        "pid": pid,
                        "process_name": process_name
                    })
            
            elif system == "Linux":
                # Linux系统
                try:
                    import subprocess
                    result = subprocess.run(
                        ['xdotool', 'getactivewindow', 'getwindowname'],
                        capture_output=True, text=True, timeout=1
                    )
                    if result.returncode == 0:
                        window_info["title"] = result.stdout.strip()
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    window_info["title"] = "Unknown Window"
            
            elif system == "Darwin":  # macOS
                # macOS系统 - 需要额外安装applescript支持
                try:
                    import subprocess
                    result = subprocess.run(
                        ['osascript', '-e', 'tell application "System Events" to get name of first process whose frontmost is true'],
                        capture_output=True, text=True, timeout=1
                    )
                    if result.returncode == 0:
                        window_info["title"] = result.stdout.strip()
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    window_info["title"] = "Unknown Window"
            
            return window_info
            
        except Exception as e:
            return {
                "system": platform.system(),
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def capture_active_window(self, filename=None, region=None):
        """
        截取当前激活窗口
        
        Args:
            filename (str, optional): 自定义文件名，如果为None则自动生成
            region (tuple, optional): 截图区域 (left, top, right, bottom)
        
        Returns:
            dict: 截图结果信息，包含文件路径、窗口信息等
        """
        try:
            # 获取窗口信息
            window_info = self.get_active_window_info()
            
            # 生成文件名
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"screenshot_{timestamp}.png"
            
            filepath = os.path.join(self.output_dir, filename)
            
            # 截取屏幕
            if region:
                # 指定区域截图
                screenshot = ImageGrab.grab(bbox=region)
            else:
                # 全屏截图
                screenshot = ImageGrab.grab()
            
            # 保存截图
            screenshot.save(filepath, "PNG", optimize=True)
            
            result = {
                "success": True,
                "filepath": filepath,
                "filename": filename,
                "window_info": window_info,
                "timestamp": datetime.now().isoformat(),
                "size": screenshot.size
            }
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def capture_region(self, left, top, right, bottom, filename=None):
        """
        截取指定区域
        
        Args:
            left, top, right, bottom (int): 区域坐标
            filename (str, optional): 自定义文件名
        
        Returns:
            dict: 截图结果信息
        """
        return self.capture_active_window(filename, region=(left, top, right, bottom))
    
    def capture_cursor_position(self, x, y, mode="active_window", filename=None):
        """
        截取鼠标点击位置的屏幕截图
        
        Args:
            x, y (int): 鼠标位置
            mode (str): 截图模式，"full_screen" 或 "active_window"
            filename (str, optional): 自定义文件名
        
        Returns:
            dict: 截图结果信息
        """
        if mode == "full_screen":
            # 全屏截图
            return self.capture_full_screen(filename)
        elif mode == "active_window":
            # 当前激活窗口截图
            return self.capture_active_window_only(filename)
        else:
            raise ValueError("mode 参数必须是 'full_screen' 或 'active_window'")
    
    def capture_full_screen(self, filename=None):
        """
        截取全屏
        
        Args:
            filename (str, optional): 自定义文件名
        
        Returns:
            dict: 截图结果信息
        """
        try:
            # 生成文件名
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"fullscreen_{timestamp}.png"
            
            filepath = os.path.join(self.output_dir, filename)
            
            # 全屏截图
            screenshot = ImageGrab.grab()
            
            # 保存截图
            screenshot.save(filepath, "PNG", quality=95)
            
            result = {
                "success": True,
                "filepath": filepath,
                "filename": filename,
                "mode": "full_screen",
                "timestamp": datetime.now().isoformat(),
                "size": screenshot.size
            }
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def capture_active_window_only(self, filename=None):
        """
        截取当前激活窗口（真正的窗口截图，不是全屏）
        
        Args:
            filename (str, optional): 自定义文件名
        
        Returns:
            dict: 截图结果信息
        """
        try:
            system = platform.system()
            window_info = self.get_active_window_info()
            
            # 生成文件名
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"active_window_{timestamp}.png"
            
            filepath = os.path.join(self.output_dir, filename)
            
            if system == "Windows":
                # Windows系统 - 使用win32gui获取窗口区域
                import win32gui
                import win32ui
                from ctypes import windll
                
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    # 获取窗口矩形
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    
                    # 截取窗口区域
                    hwndDC = win32gui.GetWindowDC(hwnd)
                    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
                    saveDC = mfcDC.CreateCompatibleDC()
                    saveBitMap = win32ui.CreateBitmap()
                    saveBitMap.CreateCompatibleBitmap(mfcDC, right - left, bottom - top)
                    saveDC.SelectObject(saveBitMap)
                    windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
                    
                    # 转换为PIL Image
                    bmpinfo = saveBitMap.GetInfo()
                    bmpstr = saveBitMap.GetBitmapBits(True)
                    img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
                    
                    # 清理资源
                    win32gui.DeleteObject(saveBitMap.GetHandle())
                    saveDC.DeleteDC()
                    mfcDC.DeleteDC()
                    win32gui.ReleaseDC(hwnd, hwndDC)
                    
                    # 保存截图
                    img.save(filepath, "PNG", quality=95)
                    
                    result = {
                        "success": True,
                        "filepath": filepath,
                        "filename": filename,
                        "window_info": window_info,
                        "mode": "active_window",
                        "timestamp": datetime.now().isoformat(),
                        "size": img.size,
                        "region": {"left": left, "top": top, "right": right, "bottom": bottom}
                    }
                    
                    return result
            
            elif system == "Linux":
                # Linux系统 - 使用scrot命令截取激活窗口
                try:
                    import subprocess
                    result = subprocess.run(
                        ['scrot', '-u', '-b', filepath],
                        capture_output=True, text=True, timeout=5
                    )
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "filepath": filepath,
                            "filename": filename,
                            "window_info": window_info,
                            "mode": "active_window",
                            "timestamp": datetime.now().isoformat()
                        }
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
            
            elif system == "Darwin":  # macOS
                # macOS系统 - 使用screencapture命令
                try:
                    import subprocess
                    result = subprocess.run(
                        ['screencapture', '-l', '1', filepath],
                        capture_output=True, text=True, timeout=5
                    )
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "filepath": filepath,
                            "filename": filename,
                            "window_info": window_info,
                            "mode": "active_window",
                            "timestamp": datetime.now().isoformat()
                        }
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
            
            # 如果平台不支持真正的窗口截图，回退到全屏截图
            return self.capture_full_screen(filename)
            
        except Exception as e:
            # 如果出现任何错误，回退到全屏截图
            return self.capture_full_screen(filename)


# 测试函数
if __name__ == "__main__":
    screenshot_manager = ScreenshotManager()
    
    # 测试截图功能
    logger.info("测试截图功能...")
    result = screenshot_manager.capture_active_window()
    logger.info(f"截图结果: {result}")
    
    if result["success"]:
        logger.info(f"截图保存至: {result['filepath']}")
        logger.info(f"窗口信息: {result['window_info']}")
