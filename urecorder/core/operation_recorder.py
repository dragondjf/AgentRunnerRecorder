"""
操作录制模块 - 重构版本
通过事件监听的方式复用现有的mouse_monitor和keyboard_monitor

注意：此文件现在是一个兼容性别名，实际实现在event_recorder.py中
"""

# 导入新的事件录制器实现
from .event_recorder import EventRecorder as _EventRecorder

# 为了向后兼容，保持原有的类名
class OperationRecorder(_EventRecorder):
    """操作录制器 - 通过监听其他监控器的事件来录制操作（重构版本）"""
    
    def __init__(self, output_dir="my_screenshots", records_file="records.json", base_url="http://127.0.0.1:12000"):
        """
        初始化操作录制器
        
        Args:
            output_dir (str): 截图保存目录
            records_file (str): records.json文件路径
            base_url (str): 基础URL，用于生成完整的图片URL
        """
        super().__init__(output_dir, records_file, base_url)
        print("🔄 使用重构版操作录制器（基于事件监听架构）")


# 向后兼容的测试函数
def test_operation_recorder():
    """测试操作录制功能"""
    from loguru import logger
    
    recorder = OperationRecorder(
        output_dir="test_screenshots",
        records_file="test_records.json"
    )
    
    logger.info("开始测试操作录制功能...")
    logger.info("请进行键盘和鼠标操作进行测试（按Ctrl+C停止）")
    
    try:
        recorder.start_recording()
        
        # 保持主线程运行
        import time
        while True:
            time.sleep(5)
            status = recorder.get_status()
            logger.info(f"录制状态: {status}")
            logger.info(f"Records摘要:\n{recorder.get_records_summary()}")
            
    except KeyboardInterrupt:
        logger.info("\n正在停止录制...")
        recorder.stop_recording()
        logger.info("测试结束")


if __name__ == "__main__":
    test_operation_recorder()