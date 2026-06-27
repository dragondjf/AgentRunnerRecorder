#!/usr/bin/env python3
"""
静态文件服务器模块
提供增强CORS支持的HTTP静态文件服务器
"""

import os
import http.server
import urllib.parse
import shutil
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from loguru import logger

# 全局变量管理文件服务器线程
_server_thread = None
_server_lock = threading.Lock()
_server_instance = None  # 存储服务器实例以便停止
_current_root_dir = None  # 当前服务的根目录


class StaticServer(SimpleHTTPRequestHandler):
    """静态文件服务器 - 增强CORS支持"""
    
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        """处理GET请求"""
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self._send_cors_headers()
            self.end_headers()
            self.list_directory(path)
        elif os.path.isfile(path):
            self.send_response(200)
            self.send_header("Content-type", self.guess_type(path))
            self._send_cors_headers()
            self.end_headers()
            with open(path, "rb") as file:
                self.copyfile(file, self.wfile)
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        """处理POST请求（文件上传）"""
        content_length = int(self.headers["Content-Length"])
        form_data = self.rfile.read(content_length).decode("utf-8")
        form_data = urllib.parse.parse_qs(form_data)
        path = self.translate_path(self.path)
        filename = form_data["filename"][0]
        filepath = os.path.join(path, filename)
        with open(filepath, "wb") as f:
            shutil.copyfileobj(self.rfile, f)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(b"<html><body>Upload successful</body></html>")

    def _send_cors_headers(self):
        """发送CORS相关头部"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Max-Age", "86400")  # 24小时缓存预检结果
        self.send_header("Access-Control-Allow-Credentials", "true")

    def end_headers(self):
        """重写end_headers方法，但不重复发送CORS头部"""
        SimpleHTTPRequestHandler.end_headers(self)

    def log_message(self, format, *args):
        """静默日志输出"""
        pass

    def copyfile(self, source, outputfile):
        """Copy all data between two file objects."""
        shutil.copyfileobj(source, outputfile)

    def list_directory(self, path):
        """列出目录内容"""
        self.wfile.write(b"<html><body>")
        self.wfile.write(f"<h1>Index of {path}</h1>".encode())
        self.wfile.write(b"<ul>")
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                item += "/"
            self.wfile.write(
                f"<li><a href='{urllib.parse.quote(item)}'>{item}</a></li>".encode()
            )
        self.wfile.write(b"</ul>")
        self.wfile.write(b"</body></html>")

    def translate_path(self, path):
        """转换路径"""
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]
        path = urllib.parse.unquote(path)
        # 使用全局的static_root变量
        global static_root
        if 'static_root' in globals():
            path = os.path.normpath(os.path.join(static_root, path.lstrip("/")))
        else:
            path = os.path.normpath(os.path.join(os.getcwd(), path.lstrip("/")))
        return path

    def guess_type(self, path):
        """猜测文件类型"""
        _, ext = os.path.splitext(path)
        if ext in (".html", ".htm"):
            return "text/html"
        elif ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp"):
            return f"image/{ext[1:]}"
        elif ext in (".js"):
            return "application/javascript"
        elif ext in (".css"):
            return "text/css"
        elif ext in (".json"):
            return "application/json"
        elif ext in (".svg"):
            return "image/svg+xml"
        elif ext in (".ico"):
            return "image/x-icon"
        else:
            return "application/octet-stream"


def start_file_server(root_dir, host="127.0.0.1", port=12000, stop_event=None):
    """
    启动静态文件服务器
    
    Args:
        root_dir (str): 服务根目录
        host (str): 监听主机地址
        port (int): 监听端口
        stop_event (threading.Event, optional): 停止事件，用于优雅关闭服务器
    
    Returns:
        ThreadingHTTPServer: 服务器实例
    """
    # 设置静态根目录
    globals()['static_root'] = root_dir
    
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, StaticServer)
    
    # 保存服务器实例到全局变量
    global _server_instance
    _server_instance = httpd
    
    logger.info(f"📁 文件服务器启动: http://{host}:{port} (服务目录: {root_dir})")
    
    # 如果提供了停止事件，使用它来控制服务器生命周期
    if stop_event:
        try:
            while not stop_event.is_set():
                httpd.handle_request()
        except Exception as e:
            if not stop_event.is_set():
                logger.error(f"文件服务器运行时出错: {e}")
    else:
        # 默认行为：无限循环
        httpd.serve_forever()
    
    # 清理服务器实例
    _server_instance = None
    logger.info("🛑 文件服务器已停止")
    
    return httpd


def stop_file_server_thread(timeout=5):
    """
    停止当前运行的文件服务器线程
    
    Args:
        timeout (int): 等待线程结束的超时时间（秒）
    
    Returns:
        bool: 成功停止返回True，超时返回False
    """
    global _server_thread, _server_instance
    
    with _server_lock:
        if not _server_thread or not _server_thread.is_alive():
            logger.info("📋 没有运行中的文件服务器线程")
            return True
        
        logger.info("🛑 正在停止文件服务器线程...")
        
        # 尝试停止服务器实例
        if _server_instance:
            try:
                # 移除shutdown()调用以避免阻塞，只关闭服务器
                _server_instance.server_close()
            except Exception as e:
                logger.warning(f"停止服务器实例时出现警告: {e}")
        
        # 等待线程结束
        if _server_thread.is_alive():
            _server_thread.join(timeout=timeout)
        
        if _server_thread.is_alive():
            logger.warning(f"⚠️ 文件服务器线程未能在 {timeout} 秒内停止")
            return False
        else:
            logger.info("✅ 文件服务器线程已成功停止")
            _server_thread = None
            _server_instance = None
            return True


# 注意：switch_file_server_root函数已合并到start_file_server_thread中
# 现在start_file_server_thread具备智能切换功能，支持多次调用


def start_file_server_thread(root_dir, host="127.0.0.1", port=12000, daemon=True, force_restart=False):
    """
    在独立线程中启动静态文件服务器（智能管理线程，支持多次调用）
    
    Args:
        root_dir (str): 服务根目录
        host (str): 监听主机地址
        port (int): 监听端口
        daemon (bool): 是否为守护线程
        force_restart (bool): 是否强制重启线程（默认False，智能切换）
    
    Returns:
        threading.Thread: 服务器线程
    """
    global _server_thread, _current_root_dir
    
    with _server_lock:
        # 如果线程不存在或已停止，或者强制重启，启动新线程
        if force_restart or not _server_thread or not _server_thread.is_alive():
            # 先停止之前的服务器线程（如果存在）
            if _server_thread and _server_thread.is_alive():
                stop_file_server_thread()
            
            logger.info(f"🆕 启动新的文件服务器线程 (根目录: {root_dir})")
            
            # 创建停止事件
            stop_event = threading.Event()
            
            def server_worker():
                """服务器工作函数"""
                start_file_server(root_dir, host, port, stop_event)
            
            # 创建新的服务器线程
            _server_thread = threading.Thread(
                target=server_worker,
                daemon=daemon
            )
            _server_thread.start()
            _current_root_dir = root_dir
            
            logger.info(f"🚀 新的文件服务器线程已启动 (根目录: {root_dir})")
            return _server_thread
        
        # 线程已存在且在运行，更新根目录（不重启线程）
        old_root = _current_root_dir
        _current_root_dir = root_dir
        
        logger.info(f"🔄 文件服务器根目录已切换: {old_root} → {root_dir}")
        
        # 更新全局静态根目录变量
        globals()['static_root'] = root_dir
        
        return _server_thread


def get_current_server_thread():
    """
    获取当前运行的文件服务器线程
    
    Returns:
        threading.Thread or None: 当前运行的服务器线程，如果不存在则返回None
    """
    return _server_thread if _server_thread and _server_thread.is_alive() else None


def get_current_server_root():
    """
    获取当前文件服务器根目录
    
    Returns:
        str or None: 当前根目录，如果不存在则返回None
    """
    return _current_root_dir


def is_server_running():
    """
    检查文件服务器是否正在运行
    
    Returns:
        bool: 如果服务器正在运行返回True，否则返回False
    """
    return _server_thread and _server_thread.is_alive()


if __name__ == "__main__":
    # 简单的测试启动
    import sys
    from pathlib import Path
    
    # 默认使用当前目录
    root_dir = sys.argv[1] if len(sys.argv) > 1 else str(Path.cwd())
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 12000
    
    print(f"启动静态文件服务器...")
    print(f"根目录: {root_dir}")
    print(f"地址: http://{host}:{port}")
    print("按 Ctrl+C 停止服务器")
    
    try:
        # 使用重构后的线程管理方式
        thread = start_file_server_thread(root_dir, host, port, daemon=False)
        
        # 等待用户中断
        try:
            thread.join()
        except KeyboardInterrupt:
            print("\n正在停止服务器...")
            stop_file_server_thread()
            print("服务器已停止")
    except Exception as e:
        print(f"启动服务器时出错: {e}")