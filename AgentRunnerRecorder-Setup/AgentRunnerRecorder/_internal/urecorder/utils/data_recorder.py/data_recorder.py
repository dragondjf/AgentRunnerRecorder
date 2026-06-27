"""
数据记录和JSON序列化模块
负责将监控数据保存到JSON文件中，并提供数据管理功能
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Lock


class DataRecorder:
    """数据记录器"""
    
    def __init__(self, data_dir="data", max_file_size_mb=10, max_files=100):
        """
        初始化数据记录器
        
        Args:
            data_dir (str): 数据保存目录
            max_file_size_mb (int): 单个文件最大大小（MB）
            max_files (int): 最大文件数量，超出时删除旧文件
        """
        self.data_dir = Path(data_dir)
        self.max_file_size_mb = max_file_size_mb
        self.max_files = max_files
        self.current_file = None
        self.file_lock = Lock()
        
        # 确保数据目录存在
        self.data_dir.mkdir(exist_ok=True)
        
        # 初始化统计信息
        self.stats = {
            "total_events": 0,
            "mouse_clicks": 0,
            "keyboard_inputs": 0,
            "start_time": None,
            "last_event_time": None
        }
        
        # 创建新的数据文件
        self._create_new_file()
    
    def _create_new_file(self):
        """创建新的数据文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"monitoring_data_{timestamp}.json"
        filepath = self.data_dir / filename
        
        # 创建文件并写入头部信息
        file_header = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "description": "系统行为监控数据"
            },
            "events": []
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(file_header, f, ensure_ascii=False, indent=2)
            
            self.current_file = filepath
            print(f"创建新的数据文件: {filepath}")
            
        except Exception as e:
            print(f"创建数据文件失败: {e}")
    
    def _cleanup_old_files(self):
        """清理旧的数据文件"""
        try:
            # 获取所有数据文件
            data_files = list(self.data_dir.glob("monitoring_data_*.json"))
            data_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # 如果文件数量超过限制，删除旧文件
            if len(data_files) > self.max_files:
                files_to_delete = data_files[self.max_files:]
                for file_path in files_to_delete:
                    try:
                        file_path.unlink()
                        print(f"删除旧数据文件: {file_path}")
                    except Exception as e:
                        print(f"删除文件失败 {file_path}: {e}")
            
            # 检查当前文件大小
            if self.current_file and self.current_file.exists():
                file_size_mb = self.current_file.stat().st_size / (1024 * 1024)
                if file_size_mb >= self.max_file_size_mb:
                    self._create_new_file()
                    
        except Exception as e:
            print(f"清理旧文件失败: {e}")
    
    def record_event(self, event_data):
        """
        记录事件数据
        
        Args:
            event_data (dict): 事件数据
        """
        with self.file_lock:
            try:
                # 更新统计信息
                self._update_stats(event_data)
                
                # 确保有当前文件
                if not self.current_file or not self.current_file.exists():
                    self._create_new_file()
                
                # 读取现有数据
                with open(self.current_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 添加新事件
                data["events"].append(event_data)
                
                # 写入更新后的数据
                with open(self.current_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 清理旧文件
                self._cleanup_old_files()
                
                print(f"事件已记录: {event_data['event_type']}")
                
            except Exception as e:
                print(f"记录事件失败: {e}")
    
    def _update_stats(self, event_data):
        """更新统计信息"""
        event_type = event_data.get("event_type", "")
        
        self.stats["total_events"] += 1
        
        if event_type == "mouse_click":
            self.stats["mouse_clicks"] += 1
        elif event_type == "keyboard_input":
            self.stats["keyboard_inputs"] += 1
        
        self.stats["last_event_time"] = event_data.get("timestamp")
        
        if self.stats["start_time"] is None:
            self.stats["start_time"] = event_data.get("timestamp")
    
    def get_stats(self):
        """
        获取统计信息
        
        Returns:
            dict: 统计信息
        """
        return self.stats.copy()
    
    def export_summary(self, output_file=None):
        """
        导出数据摘要
        
        Args:
            output_file (str, optional): 输出文件路径
        
        Returns:
            dict: 数据摘要
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.data_dir / f"summary_{timestamp}.json"
        
        summary = {
            "generated_at": datetime.now().isoformat(),
            "statistics": self.stats,
            "files": []
        }
        
        # 收集所有文件信息
        try:
            data_files = list(self.data_dir.glob("monitoring_data_*.json"))
            for file_path in data_files:
                try:
                    stat = file_path.stat()
                    summary["files"].append({
                        "filename": file_path.name,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    print(f"获取文件信息失败 {file_path}: {e}")
            
            # 保存摘要
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            print(f"数据摘要已导出至: {output_file}")
            return summary
            
        except Exception as e:
            print(f"导出摘要失败: {e}")
            return {}
    
    def load_events(self, filename=None, limit=None):
        """
        加载事件数据
        
        Args:
            filename (str, optional): 指定文件名，默认加载最新文件
            limit (int, optional): 限制加载的事件数量
        
        Returns:
            list: 事件数据列表
        """
        try:
            if filename:
                file_path = self.data_dir / filename
            else:
                # 加载最新的文件
                data_files = list(self.data_dir.glob("monitoring_data_*.json"))
                if not data_files:
                    return []
                
                data_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                file_path = data_files[0]
            
            if not file_path.exists():
                return []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            events = data.get("events", [])
            
            if limit:
                events = events[-limit:]  # 返回最新的limit个事件
            
            return events
            
        except Exception as e:
            print(f"加载事件数据失败: {e}")
            return []
    
    def search_events(self, event_type=None, start_time=None, end_time=None, keyword=None):
        """
        搜索事件数据
        
        Args:
            event_type (str, optional): 事件类型过滤
            start_time (str, optional): 开始时间过滤 (ISO格式)
            end_time (str, optional): 结束时间过滤 (ISO格式)
            keyword (str, optional): 关键词搜索
        
        Returns:
            list: 匹配的事件列表
        """
        events = self.load_events()
        filtered_events = []
        
        for event in events:
            # 事件类型过滤
            if event_type and event.get("event_type") != event_type:
                continue
            
            # 时间范围过滤
            event_time = event.get("timestamp", "")
            if start_time and event_time < start_time:
                continue
            if end_time and event_time > end_time:
                continue
            
            # 关键词搜索
            if keyword:
                event_str = json.dumps(event, ensure_ascii=False)
                if keyword not in event_str:
                    continue
            
            filtered_events.append(event)
        
        return filtered_events
    
    def clear_all_data(self):
        """清空所有数据文件"""
        try:
            data_files = list(self.data_dir.glob("monitoring_data_*.json"))
            for file_path in data_files:
                file_path.unlink()
            
            # 重置统计信息
            self.stats = {
                "total_events": 0,
                "mouse_clicks": 0,
                "keyboard_inputs": 0,
                "start_time": None,
                "last_event_time": None
            }
            
            # 创建新文件
            self._create_new_file()
            
            print("所有数据已清空")
            
        except Exception as e:
            print(f"清空数据失败: {e}")


# 测试函数
def test_data_recorder():
    """测试数据记录器功能"""
    recorder = DataRecorder()
    
    # 测试数据
    test_events = [
        {
            "event_type": "mouse_click",
            "timestamp": datetime.now().isoformat(),
            "position": {"x": 100, "y": 200},
            "button": "Button.left"
        },
        {
            "event_type": "keyboard_input",
            "timestamp": datetime.now().isoformat(),
            "input_string": "Hello World",
            "input_length": 11
        }
    ]
    
    print("测试数据记录器...")
    
    # 记录测试事件
    for event in test_events:
        recorder.record_event(event)
    
    # 获取统计信息
    stats = recorder.get_stats()
    print(f"统计信息: {stats}")
    
    # 导出摘要
    summary = recorder.export_summary()
    print(f"摘要: {summary}")
    
    # 加载事件
    events = recorder.load_events(limit=10)
    print(f"加载的事件数量: {len(events)}")
    
    # 搜索事件
    mouse_events = recorder.search_events(event_type="mouse_click")
    print(f"鼠标事件数量: {len(mouse_events)}")
    
    print("数据记录器测试完成")


if __name__ == "__main__":
    test_data_recorder()