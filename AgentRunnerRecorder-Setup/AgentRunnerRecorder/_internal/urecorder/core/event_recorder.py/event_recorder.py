"""
操作录制模块 - 纯数据记录版本
EventRecorder是一个完全独立的纯数据记录模块
不依赖任何外部组件，只负责数据记录和文件操作
"""

import os
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from loguru import logger


def number_to_chinese_step(number):
    """将数字转换为中文步骤格式"""
    chinese_numbers = {
        1: "第一步", 2: "第二步", 3: "第三步", 4: "第四步", 5: "第五步",
        6: "第六步", 7: "第七步", 8: "第八步", 9: "第九步", 10: "第十步",
        11: "第十一步", 12: "第十二步", 13: "第十三步", 14: "第十四步", 15: "第十五步",
        16: "第十六步", 17: "第十七步", 18: "第十八步", 19: "第十九步", 20: "第二十步"
    }
    return chinese_numbers.get(number, f"第{number}步")


class EventRecorder:
    """事件录制器 - 通过监听SystemMonitor的监控器事件来录制操作"""
    
    def __init__(self, output_dir="my_screenshots", records_file="records.json", base_url="http://127.0.0.1:12000"):
        """
        初始化事件录制器
        
        Args:
            output_dir (str): 截图保存目录
            records_file (str): records.json文件路径
            base_url (str): 基础URL，用于生成完整的图片URL
        """
        self.output_dir = output_dir
        self.records_file = records_file
        self.base_url = base_url
        
        # 录制状态
        self.is_recording = False
        self.operation_id = 1
        self.slides = []
        
        # 线程锁
        self._lock = threading.Lock()
        
        # 加载现有records.json
        self._load_existing_records()
        
        logger.info(f"EventRecorder初始化完成: 输出目录={output_dir}, 记录文件={records_file}, 基础URL={base_url}")
    
    def _number_to_chinese_step(self, number):
        """将数字转换为中文步骤格式"""
        return number_to_chinese_step(number)
    
    def _load_existing_records(self):
        """加载现有的records.json文件"""
        try:
            if os.path.exists(self.records_file):
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.slides = data.get('slides', [])
                    # 设置下一个ID
                    if self.slides:
                        max_id = max(slide.get('id', 0) for slide in self.slides)
                        self.operation_id = max_id + 1
                    logger.info(f"已加载现有records.json，包含 {len(self.slides)} 个记录")
        except Exception as e:
            logger.warning(f"加载records.json失败: {e}")
            self.slides = []
    
    def _save_records(self):
        """保存records.json文件"""
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(self.records_file) if os.path.dirname(self.records_file) else '.', exist_ok=True)
            
            records_data = {
                "slides": self.slides,
                "lastUpdated": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            with open(self.records_file, 'w', encoding='utf-8') as f:
                json.dump(records_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"已保存records.json，包含 {len(self.slides)} 个记录")
        except Exception as e:
            logger.error(f"保存records.json失败: {e}")
    
    def _create_thumbnail_svg(self, title, image_filename):
        """创建SVG缩略图"""
        # SVG模板
        svg_template = '''<svg xmlns='http://www.w3.org/2000/svg' width='168' height='100' viewBox='0 0 168 100'>
    <rect width='168' height='100' fill='#ffffff'/>
    <rect x='10' y='10' width='148' height='80' rx='4' fill='#eef2f7' stroke='#cbd5e0'/>
    <text x='50%' y='40%' dominant-baseline='middle' text-anchor='middle' font-family='Segoe UI, SF Pro Display, -apple-system, BlinkMacSystemFont, Roboto, Helvetica Neue, sans-serif' font-size='12' fill='#0066cc'>{title}</text>
    <text x='50%' y='60%' dominant-baseline='middle' text-anchor='middle' font-family='Segoe UI, SF Pro Display, -apple-system, BlinkMacSystemFont, Roboto, Helvetica Neue, sans-serif' font-size='10' fill='#4a5568'>{subtitle}</text>
</svg>'''
        
        # 截取标题和副标题
        display_title = title[:20] + "..." if len(title) > 20 else title
        subtitle = f"操作 {self.operation_id}"
        
        return svg_template.format(title=display_title, subtitle=subtitle)
    
    def record_operation(self, operation_type, operation_details, screenshot_filename=None):
        """
        记录一次操作

        Args:
            operation_type (str): 操作类型 ('keyboard', 'mouse')
            operation_details (dict): 操作详情
            screenshot_filename (str, optional): 截图文件名,如果为None则不包含截图
        """
        try:
            with self._lock:
                # 构建context信息
                context_parts = [
                    f"操作类型: {operation_type}",
                    f"时间戳: {datetime.now().isoformat()}"
                ]

                # 添加操作详情
                for key, value in operation_details.items():
                    context_parts.append(f"{key}: {value}")

                context = "; \n".join(context_parts)

                # 构建markdown内容 - 使用完整的绝对URL（与旧版本兼容）
                if screenshot_filename:
                    # 获取项目名称(从records文件路径提取父目录名)
                    project_name = Path(self.records_file).parent.name if self.records_file else "mydata"
                    # 生成完整的绝对URL
                    full_image_url = f"{self.base_url}/api/v1/file?path={project_name}/my_screenshots/{screenshot_filename}"
                    markdown = f"![操作截图]({full_image_url})"
                else:
                    markdown = f"操作记录: {operation_type}"
                
                # 创建缩略图
                thumbnail = self._create_thumbnail_svg(
                    f"{operation_type}操作", 
                    screenshot_filename or "no_screenshot"
                )
                
                # 构建operation_details对象
                operation_details_obj = {}
                for key, value in operation_details.items():
                    # 将中文键转换为英文键，保持与旧版本一致
                    if "位置" in str(key):
                        operation_details_obj["位置"] = str(value)
                    elif "按钮" in str(key):
                        operation_details_obj["按钮"] = str(value)
                    elif "时间戳" in str(key):
                        operation_details_obj["时间戳"] = str(value)
                    else:
                        operation_details_obj[key] = value
                
                # 构建slide数据（与旧版本格式完全兼容）
                slide_data = {
                    "context": context,
                    "id": self.operation_id,
                    "link": "",
                    "markdown": markdown,
                    "operation_details": operation_details_obj,
                    "remark": "",
                    "testCase": "需要生成包含正向测试、异常测试、边界测试的完整测试用例，重点关注安全性和用户体验。",
                    "thumbnail": thumbnail,
                    "title": f"{self._number_to_chinese_step(self.operation_id)}：{operation_type}",
                    "url": full_image_url if screenshot_filename else "",
                    "ai_result": ""
                }
                
                # 添加到slides列表
                self.slides.append(slide_data)
                
                logger.info(f"记录操作 #{self.operation_id}: {operation_type}")
                if screenshot_filename:
                    logger.info(f"  截图: {screenshot_filename}")
                    logger.info(f"  完整URL: {full_image_url}")
                logger.info(f"  Context: {context}")
                
                # 保存到文件
                self._save_records()
                
                # 增加ID
                self.operation_id += 1
                
        except Exception as e:
            logger.error(f"记录操作时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def start_recording(self):
        """开始录制操作"""
        if self.is_recording:
            logger.warning("事件录制已在运行中")
            return
        
        self.is_recording = True
        
        logger.info("🎬 事件录制已开始")
        logger.info(f"📁 截图保存目录: {self.output_dir}")
        logger.info(f"📄 Records文件: {self.records_file}")
        logger.info("📝 EventRecorder准备记录操作数据")
    
    def stop_recording(self):
        """停止录制操作"""
        if not self.is_recording:
            logger.warning("事件录制未在运行")
            return
        
        self.is_recording = False
        
        # 保存最终数据
        self._save_records()
        
        logger.info("🛑 事件录制已停止")
        logger.info(f"📊 总共记录了 {len(self.slides)} 个操作")
    
    def get_status(self):
        """获取录制状态"""
        return {
            "is_recording": self.is_recording,
            "total_operations": len(self.slides),
            "current_id": self.operation_id,
            "output_dir": self.output_dir,
            "records_file": self.records_file,
            "module_type": "pure_data_recorder"
        }
    
    def get_records_summary(self):
        """获取records.json摘要信息"""
        if not self.slides:
            return "暂无记录"
        
        summary = []
        summary.append(f"总操作数: {len(self.slides)}")
        
        # 统计操作类型
        keyboard_count = sum(1 for slide in self.slides if "keyboard" in slide.get("title", ""))
        mouse_count = sum(1 for slide in self.slides if "mouse" in slide.get("title", ""))
        
        summary.append(f"键盘操作: {keyboard_count}")
        summary.append(f"鼠标操作: {mouse_count}")
        
        if self.slides:
            summary.append(f"首个操作: {self.slides[0].get('title', 'N/A')}")
            summary.append(f"最后操作: {self.slides[-1].get('title', 'N/A')}")
        
        return "\n".join(summary)


# 向后兼容性别名
OperationRecorder = EventRecorder


# 测试函数
def test_event_recorder():
    """测试纯数据记录功能"""
    logger.info("开始测试EventRecorder纯数据记录功能...")
    
    # 创建独立的EventRecorder
    recorder = EventRecorder(
        output_dir="test_screenshots",
        records_file="test_records.json"
    )
    
    # 启动录制
    recorder.start_recording()
    
    # 模拟一些操作记录
    mock_mouse_event = {
        "position": {"x": 100, "y": 200},
        "button": "left",
        "timestamp": "2025-11-02T12:37:48.798858"
    }
    
    recorder.record_operation("mouse", mock_mouse_event, "test_mouse_screenshot.png")
    
    mock_keyboard_event = {
        "input_string": "test input",
        "input_length": 10,
        "first_char": "t",
        "last_char": "t",
        "end_reason": "manual",
        "timestamp": "2025-11-02T12:37:48.894025"
    }
    
    recorder.record_operation("keyboard", mock_keyboard_event, "test_keyboard_screenshot.png")
    
    # 停止录制
    recorder.stop_recording()
    
    # 显示状态
    logger.info(f"录制状态: {recorder.get_status()}")
    logger.info(f"Records摘要:\n{recorder.get_records_summary()}")
    
    logger.info("测试完成")


if __name__ == "__main__":
    test_event_recorder()