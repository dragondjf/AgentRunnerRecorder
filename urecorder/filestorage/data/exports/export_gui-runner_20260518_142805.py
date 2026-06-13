#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUIRunner自动化测试脚本

生成时间: 2026-05-18 14:28:05
数据来源: F:\workspace\yfjzworkspace\webspace\ai-template\agentrunner\uirecordercore\filestorage\dsdssd
操作记录数: 0
"""

import time
import json
from datetime import datetime
from pathlib import Path

# GUI自动化库 (需要安装)
try:
    import pyautogui
    from pynput import keyboard, mouse
    from pynput.keyboard import Key, Controller as KeyboardController
    from pynput.mouse import Button, Controller as MouseController
except ImportError:
    print('请安装必要的库: pip install pyautogui pynput')
    exit(1)

# 配置设置
CONFIG = {
    'screenshot_dir': 'screenshots',
    'delay_between_actions': 0.5,  # 操作间隔时间(秒)
    'screenshot_on_action': True,  # 是否在操作时截图
    'verbose': True,  # 是否显示详细信息
}

class GUIRunner:
    """GUI自动化测试执行器"""

    def __init__(self, config=None):
        self.config = config or CONFIG
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.start_time = None
        self.action_count = 0

    def log(self, message):
        """日志输出"""
        if self.config.get('verbose', True):
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f'[{timestamp}] {message}')

    def take_screenshot(self, name=None):
        """截图功能"""
        if not self.config.get('screenshot_on_action', True):
            return
        
        screenshot_dir = Path(self.config.get('screenshot_dir', 'screenshots'))
        screenshot_dir.mkdir(exist_ok=True)
        
        if name is None:
            name = f'action_{{self.action_count:03d}}_{{int(time.time())}}.png'
        
        screenshot_path = screenshot_dir / name
        pyautogui.screenshot(str(screenshot_path))
        self.log(f'截图已保存: {{screenshot_path}}')

    def delay(self, seconds=None):
        """延迟执行"""
        delay_time = seconds or self.config.get('delay_between_actions', 0.5)
        if delay_time > 0:
            self.log(f'等待 {{delay_time}} 秒...')
            time.sleep(delay_time)

    def execute_keyboard_action(self, action):
        """执行键盘操作"""
        action_type = action.get('type', '')
        details = action.get('details', {})
        
        if action_type == '键盘输入':
            text = details.get('text', '')
            if text:
                self.log(f'输入文本: {{text}}')
                self.keyboard.type(text)
                
        elif action_type == '特殊键':
            key_name = details.get('key', '')
            if key_name:
                self.log(f'按下特殊键: {{key_name}}')
                try:
                    key = getattr(Key, key_name.lower(), None)
                    if key:
                        self.keyboard.press(key)
                        self.keyboard.release(key)
                    else:
                        # 尝试作为字符串键处理
                        self.keyboard.press(key_name)
                        self.keyboard.release(key_name)
                except Exception as e:
                    self.log(f'特殊键操作失败: {{e}}')
        
        self.delay()
        self.take_screenshot(f'keyboard_{{self.action_count:03d}}.png')

    def execute_mouse_action(self, action):
        """执行鼠标操作"""
        action_type = action.get('type', '')
        details = action.get('details', {})
        
        if action_type == '鼠标点击':
            x = details.get('x', 0)
            y = details.get('y', 0)
            button = details.get('button', 'left')
            
            self.log(f'鼠标点击: ({{x}}, {{y}}) 按钮: {{button}}')
            
            # 移动到目标位置
            self.mouse.position = (x, y)
            time.sleep(0.1)  # 短暂延迟确保移动完成
            
            # 执行点击
            if button.lower() == 'left':
                self.mouse.click(Button.left)
            elif button.lower() == 'right':
                self.mouse.click(Button.right)
            elif button.lower() == 'middle':
                self.mouse.click(Button.middle)
            
        elif action_type == '鼠标移动':
            x = details.get('x', 0)
            y = details.get('y', 0)
            
            self.log(f'鼠标移动到: ({{x}}, {{y}})')
            self.mouse.position = (x, y)
            
        elif action_type == '鼠标滚轮':
            delta = details.get('delta', 0)
            self.log(f'鼠标滚轮: {{delta}}')
            pyautogui.scroll(delta)
        
        self.delay()
        self.take_screenshot(f'mouse_{{self.action_count:03d}}.png')

    def execute_action(self, action):
        """执行单个操作"""
        self.action_count += 1
        action_type = action.get('type', 'Unknown')
        timestamp = action.get('timestamp', '')
        
        self.log(f'执行操作 #{{self.action_count}}: {{action_type}} ({{timestamp}})')
        
        if action_type in ['键盘输入', '特殊键']:
            self.execute_keyboard_action(action)
        elif action_type in ['鼠标点击', '鼠标移动', '鼠标滚轮']:
            self.execute_mouse_action(action)
        else:
            self.log(f'未知操作类型: {{action_type}}')

    def run_script(self, operations):
        """运行测试脚本"""
        self.log('开始执行GUIRunner测试脚本')
        self.start_time = time.time()
        
        try:
            for i, operation in enumerate(operations):
                self.log(f'进度: {{i+1}}/{{len(operations)}}')
                self.execute_action(operation)
            
            end_time = time.time()
            duration = end_time - self.start_time
            
            self.log(f'脚本执行完成')
            self.log(f'总操作数: {{self.action_count}}')
            self.log(f'执行时长: {{duration:.2f}} 秒')
            
        except KeyboardInterrupt:
            self.log('用户中断执行')
        except Exception as e:
            self.log(f'执行过程中发生错误: {{e}}')
            raise

def main():
    """主函数"""
    print('=' * 60)
    print('GUIRunner自动化测试脚本')
    print('=' * 60)
    
    # 加载监控数据
    data_file = Path(__file__).parent / 'monitoring_data.json'
    if not data_file.exists():
        print(f'错误: 数据文件不存在 {{data_file}}')
        return
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f'错误: 无法加载数据文件 {{e}}')
        return
    
    operations = data.get('operations', [])
    if not operations:
        print('警告: 没有找到操作记录')
        return
    
    print(f'找到 {len(operations)} 个操作记录')
    print('按回车键开始执行，按Ctrl+C中断...')
    input()
    
    # 创建并运行GUIRunner
    runner = GUIRunner(CONFIG)
    runner.run_script(operations)

if __name__ == '__main__':
    main()

# 使用说明:
# 1. 安装依赖: pip install pyautogui pynput
# 2. 将监控数据文件重命名为 'monitoring_data.json'
# 3. 运行脚本: python gui_runner_script.py
# 4. 按回车开始执行，按Ctrl+C中断

# 注意事项:
# - 请确保在安全的环境中运行，避免意外操作
# - 建议先在测试环境中验证脚本
# - 某些操作可能需要管理员权限
# - 脚本执行时不要移动鼠标或操作键盘