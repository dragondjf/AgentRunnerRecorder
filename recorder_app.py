"""
Simple Screen Recorder — 简易录屏工具
======================================
暗色主题 · PNG图标 · 折叠面板

按钮栏布局（从左到右）：
  空闲态：  [record] [timer]                    [settings] [log] [folder] [export]
  录制态：  [stop]   [timer]  [pause]            [settings] [log] [folder] [export]
  暂停态：  [stop]   [timer]  [resume]           [settings] [log] [folder] [export]

快捷键（录制中）：
  Ctrl+Shift+F5  停止录制
  Ctrl+Shift+F9  暂停/继续
"""

import os
import sys

# Ensure project root is on the path for `recorder.*` imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recorder.app import ScreenRecorderApp


def main():
    ScreenRecorderApp().run()


if __name__ == "__main__":
    main()
