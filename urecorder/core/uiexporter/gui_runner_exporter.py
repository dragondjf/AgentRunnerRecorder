#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUIRunner脚本导出器
基于监控数据生成可执行的GUI测试脚本
"""

import os
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

from .base_exporter import BaseExporter


class GuiRunnerExporter(BaseExporter):
    """GUIRunner脚本导出器"""
    
    def export(self) -> str:
        """
        导出GUIRunner脚本
        
        Returns:
            str: 输出文件路径，导出失败返回空字符串
        """
        try:
            # 生成输出文件路径
            timestamp = self.export_time.strftime('%Y%m%d_%H%M%S')
            output_dir = self.data_dir.parent / 'data' / 'exports'
            output_file = output_dir / f'export_gui-runner_{timestamp}.py'
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"开始导出GUIRunner脚本: {output_file}")
            
            # 生成Python脚本内容
            script_content = self._generate_gui_runner_script()
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            logger.info(f"GUIRunner脚本导出成功: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"GUIRunner脚本导出失败: {e}")
            return ""
    
    def _generate_gui_runner_script(self) -> str:
        """生成GUIRunner脚本"""
        monitoring_data = self.load_monitoring_data()
        
        script = []
        
        # 脚本头部信息
        script.append("#!/usr/bin/env python3")
        script.append("# -*- coding: utf-8 -*-")
        script.append(f'"""')
        script.append(f"GUIRunner自动化测试脚本")
        script.append(f"")
        script.append(f"生成时间: {self.export_time.strftime('%Y-%m-%d %H:%M:%S')}")
        script.append(f"数据来源: {self.data_dir}")
        script.append(f"操作记录数: {len(monitoring_data.get('operations', [])) if monitoring_data else 0}")
        script.append(f'"""')
        script.append("")
        
        # 导入必要的库
        script.append("import time")
        script.append("import json")
        script.append("from datetime import datetime")
        script.append("from pathlib import Path")
        script.append("")
        script.append("# GUI自动化库 (需要安装)")
        script.append("try:")
        script.append("    import pyautogui")
        script.append("    from pynput import keyboard, mouse")
        script.append("    from pynput.keyboard import Key, Controller as KeyboardController")
        script.append("    from pynput.mouse import Button, Controller as MouseController")
        script.append("except ImportError:")
        script.append("    print('请安装必要的库: pip install pyautogui pynput')")
        script.append("    exit(1)")
        script.append("")
        
        # 配置设置
        script.append("# 配置设置")
        script.append("CONFIG = {")
        script.append("    'screenshot_dir': 'screenshots',")
        script.append("    'delay_between_actions': 0.5,  # 操作间隔时间(秒)")
        script.append("    'screenshot_on_action': True,  # 是否在操作时截图")
        script.append("    'verbose': True,  # 是否显示详细信息")
        script.append("}")
        script.append("")
        
        # 控制器类
        script.append("class GUIRunner:")
        script.append("    \"\"\"GUI自动化测试执行器\"\"\"")
        script.append("")
        script.append("    def __init__(self, config=None):")
        script.append("        self.config = config or CONFIG")
        script.append("        self.keyboard = KeyboardController()")
        script.append("        self.mouse = MouseController()")
        script.append("        self.start_time = None")
        script.append("        self.action_count = 0")
        script.append("")
        script.append("    def log(self, message):")
        script.append("        \"\"\"日志输出\"\"\"")
        script.append("        if self.config.get('verbose', True):")
        script.append("            timestamp = datetime.now().strftime('%H:%M:%S')")
        script.append("            print(f'[{timestamp}] {message}')")
        script.append("")
        script.append("    def take_screenshot(self, name=None):")
        script.append("        \"\"\"截图功能\"\"\"")
        script.append("        if not self.config.get('screenshot_on_action', True):")
        script.append("            return")
        script.append("        ")
        script.append("        screenshot_dir = Path(self.config.get('screenshot_dir', 'screenshots'))")
        script.append("        screenshot_dir.mkdir(exist_ok=True)")
        script.append("        ")
        script.append("        if name is None:")
        script.append("            name = f'action_{{self.action_count:03d}}_{{int(time.time())}}.png'")
        script.append("        ")
        script.append("        screenshot_path = screenshot_dir / name")
        script.append("        pyautogui.screenshot(str(screenshot_path))")
        script.append("        self.log(f'截图已保存: {{screenshot_path}}')")
        script.append("")
        script.append("    def delay(self, seconds=None):")
        script.append("        \"\"\"延迟执行\"\"\"")
        script.append("        delay_time = seconds or self.config.get('delay_between_actions', 0.5)")
        script.append("        if delay_time > 0:")
        script.append("            self.log(f'等待 {{delay_time}} 秒...')")
        script.append("            time.sleep(delay_time)")
        script.append("")
        script.append("    def execute_keyboard_action(self, action):")
        script.append("        \"\"\"执行键盘操作\"\"\"")
        script.append("        action_type = action.get('type', '')")
        script.append("        details = action.get('details', {})")
        script.append("        ")
        script.append("        if action_type == '键盘输入':")
        script.append("            text = details.get('text', '')")
        script.append("            if text:")
        script.append("                self.log(f'输入文本: {{text}}')")
        script.append("                self.keyboard.type(text)")
        script.append("                ")
        script.append("        elif action_type == '特殊键':")
        script.append("            key_name = details.get('key', '')")
        script.append("            if key_name:")
        script.append("                self.log(f'按下特殊键: {{key_name}}')")
        script.append("                try:")
        script.append("                    key = getattr(Key, key_name.lower(), None)")
        script.append("                    if key:")
        script.append("                        self.keyboard.press(key)")
        script.append("                        self.keyboard.release(key)")
        script.append("                    else:")
        script.append("                        # 尝试作为字符串键处理")
        script.append("                        self.keyboard.press(key_name)")
        script.append("                        self.keyboard.release(key_name)")
        script.append("                except Exception as e:")
        script.append("                    self.log(f'特殊键操作失败: {{e}}')")
        script.append("        ")
        script.append("        self.delay()")
        script.append("        self.take_screenshot(f'keyboard_{{self.action_count:03d}}.png')")
        script.append("")
        script.append("    def execute_mouse_action(self, action):")
        script.append("        \"\"\"执行鼠标操作\"\"\"")
        script.append("        action_type = action.get('type', '')")
        script.append("        details = action.get('details', {})")
        script.append("        ")
        script.append("        if action_type == '鼠标点击':")
        script.append("            x = details.get('x', 0)")
        script.append("            y = details.get('y', 0)")
        script.append("            button = details.get('button', 'left')")
        script.append("            ")
        script.append("            self.log(f'鼠标点击: ({{x}}, {{y}}) 按钮: {{button}}')")
        script.append("            ")
        script.append("            # 移动到目标位置")
        script.append("            self.mouse.position = (x, y)")
        script.append("            time.sleep(0.1)  # 短暂延迟确保移动完成")
        script.append("            ")
        script.append("            # 执行点击")
        script.append("            if button.lower() == 'left':")
        script.append("                self.mouse.click(Button.left)")
        script.append("            elif button.lower() == 'right':")
        script.append("                self.mouse.click(Button.right)")
        script.append("            elif button.lower() == 'middle':")
        script.append("                self.mouse.click(Button.middle)")
        script.append("            ")
        script.append("        elif action_type == '鼠标移动':")
        script.append("            x = details.get('x', 0)")
        script.append("            y = details.get('y', 0)")
        script.append("            ")
        script.append("            self.log(f'鼠标移动到: ({{x}}, {{y}})')")
        script.append("            self.mouse.position = (x, y)")
        script.append("            ")
        script.append("        elif action_type == '鼠标滚轮':")
        script.append("            delta = details.get('delta', 0)")
        script.append("            self.log(f'鼠标滚轮: {{delta}}')")
        script.append("            pyautogui.scroll(delta)")
        script.append("        ")
        script.append("        self.delay()")
        script.append("        self.take_screenshot(f'mouse_{{self.action_count:03d}}.png')")
        script.append("")
        script.append("    def execute_action(self, action):")
        script.append("        \"\"\"执行单个操作\"\"\"")
        script.append("        self.action_count += 1")
        script.append("        action_type = action.get('type', 'Unknown')")
        script.append("        timestamp = action.get('timestamp', '')")
        script.append("        ")
        script.append("        self.log(f'执行操作 #{{self.action_count}}: {{action_type}} ({{timestamp}})')")
        script.append("        ")
        script.append("        if action_type in ['键盘输入', '特殊键']:")
        script.append("            self.execute_keyboard_action(action)")
        script.append("        elif action_type in ['鼠标点击', '鼠标移动', '鼠标滚轮']:")
        script.append("            self.execute_mouse_action(action)")
        script.append("        else:")
        script.append("            self.log(f'未知操作类型: {{action_type}}')")
        script.append("")
        script.append("    def run_script(self, operations):")
        script.append("        \"\"\"运行测试脚本\"\"\"")
        script.append("        self.log('开始执行GUIRunner测试脚本')")
        script.append("        self.start_time = time.time()")
        script.append("        ")
        script.append("        try:")
        script.append("            for i, operation in enumerate(operations):")
        script.append("                self.log(f'进度: {{i+1}}/{{len(operations)}}')")
        script.append("                self.execute_action(operation)")
        script.append("            ")
        script.append("            end_time = time.time()")
        script.append("            duration = end_time - self.start_time")
        script.append("            ")
        script.append("            self.log(f'脚本执行完成')")
        script.append("            self.log(f'总操作数: {{self.action_count}}')")
        script.append("            self.log(f'执行时长: {{duration:.2f}} 秒')")
        script.append("            ")
        script.append("        except KeyboardInterrupt:")
        script.append("            self.log('用户中断执行')")
        script.append("        except Exception as e:")
        script.append("            self.log(f'执行过程中发生错误: {{e}}')")
        script.append("            raise")
        script.append("")
        
        # 主函数
        script.append("def main():")
        script.append("    \"\"\"主函数\"\"\"")
        script.append("    print('=' * 60)")
        script.append("    print('GUIRunner自动化测试脚本')")
        script.append("    print('=' * 60)")
        script.append("    ")
        script.append("    # 加载监控数据")
        script.append("    data_file = Path(__file__).parent / 'monitoring_data.json'")
        script.append("    if not data_file.exists():")
        script.append("        print(f'错误: 数据文件不存在 {{data_file}}')")
        script.append("        return")
        script.append("    ")
        script.append("    try:")
        script.append("        with open(data_file, 'r', encoding='utf-8') as f:")
        script.append("            data = json.load(f)")
        script.append("    except Exception as e:")
        script.append("        print(f'错误: 无法加载数据文件 {{e}}')")
        script.append("        return")
        script.append("    ")
        script.append("    operations = data.get('operations', [])")
        script.append("    if not operations:")
        script.append("        print('警告: 没有找到操作记录')")
        script.append("        return")
        script.append("    ")
        script.append(f"    print(f'找到 {{len(operations)}} 个操作记录')")
        script.append("    print('按回车键开始执行，按Ctrl+C中断...')")
        script.append("    input()")
        script.append("    ")
        script.append("    # 创建并运行GUIRunner")
        script.append("    runner = GUIRunner(CONFIG)")
        script.append("    runner.run_script(operations)")
        script.append("")
        script.append("if __name__ == '__main__':")
        script.append("    main()")
        script.append("")
        
        # 使用说明
        script.append("# 使用说明:")
        script.append("# 1. 安装依赖: pip install pyautogui pynput")
        script.append("# 2. 将监控数据文件重命名为 'monitoring_data.json'")
        script.append("# 3. 运行脚本: python gui_runner_script.py")
        script.append("# 4. 按回车开始执行，按Ctrl+C中断")
        script.append("")
        script.append("# 注意事项:")
        script.append("# - 请确保在安全的环境中运行，避免意外操作")
        script.append("# - 建议先在测试环境中验证脚本")
        script.append("# - 某些操作可能需要管理员权限")
        script.append("# - 脚本执行时不要移动鼠标或操作键盘")
        
        return '\n'.join(script)