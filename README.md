# AgentRunner Recorder

轻量级桌面录屏工具，专为测试用例生成场景设计。同步录制屏幕视频、键盘鼠标操作事件，并在每次事件触发时自动截取屏幕快照。

![Python 3.7+](https://img.shields.io/badge/Python-3.7%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

## 功能特性

- **屏幕录制** — 基于 mss + OpenCV，支持多显示器、可调帧率（10/15/20/25/30 fps）
- **事件采集** — 记录键盘按键、鼠标点击、滚轮、移动等操作，输出结构化 JSONL 日志
- **自动截图** — 每次输入事件触发时自动截取屏幕快照，按序号命名
- **暂停/继续** — 录制过程中可随时暂停和恢复，视频和事件日志无缝衔接
- **全局热键** — `Ctrl+Shift+F5` 停止录制，`Ctrl+Shift+F9` 暂停/继续
- **一键导出** — 将录制项目打包为 ZIP 压缩包，方便传输和归档
- **暗色主题** — 深色 GUI 界面，透明背景 PNG 图标，折叠式设置/日志面板

## 快速开始

### 安装依赖

```bash
pip install pillow opencv-python numpy mss pynput
```

> `pynput` 为可选依赖，缺省时全局热键不可用，其余功能正常。

### 启动

```bash
python recorder_app.py
```

## 使用方法

1. **开始录制** — 点击红色录制按钮或通过 GUI 启动
2. **暂停/继续** — 点击暂停/恢复按钮切换，或按 `Ctrl+Shift+F9`
3. **停止录制** — 点击停止按钮或按 `Ctrl+Shift+F5`
4. **打开目录** — 在资源管理器中查看录制输出
5. **导出 ZIP** — 将录制项目打包为 ZIP 文件

### 录制输出结构

```
{output_dir}/
└── recording_20240101_120000/
    └── inputs/
        ├── recording_20240101_120000.mp4          # 屏幕录像
        ├── input_log_recording_20240101_120000.txt # 事件日志 (JSONL)
        └── screenshots/
            ├── 0001.png
            ├── 0002.png
            └── ...
```

### 事件日志格式（JSONL）

每行一条 JSON 记录，示例：

```json
{"type": "mouse_click", "button": "left", "x": 960, "y": 540, "timestamp": 1704067200.123, "screenshot": "screenshots/0001.png", "window": "Chrome - Google"}
```

## 项目结构

```
├── recorder_app.py          # GUI 主程序（tkinter）
├── recorder/
│   ├── __init__.py          # 懒加载导出
│   ├── core.py              # RecordingSession 录制会话编排
│   ├── screen_capture.py    # mss + OpenCV 屏幕录制
│   ├── event_listener.py    # pynput 键盘/鼠标事件监听
│   ├── window_tracker.py    # 活动窗口标题检测
│   └── manager.py           # 线程安全状态管理
├── images/
│   ├── app_icon.ico         # 窗口图标（多尺寸 ICO）
│   ├── app_icon.png         # 窗口图标（64x64）
│   └── icons_64/            # 功能图标（64x64, 透明背景）
│       ├── record.png       #   录制（红色实心圆）
│       ├── stop.png         #   停止
│       ├── pause.png        #   暂停（双竖线）
│       ├── resume.png       #   继续（播放三角）
│       ├── settings.png     #   设置
│       ├── log.png          #   日志
│       ├── folder.png       #   目录
│       └── export.png       #   导出
└── README.md
```

## 依赖要求

| 依赖 | 版本 | 用途 | 必需 |
|------|------|------|------|
| Python | >= 3.7 | 运行环境 | 是 |
| Pillow | >= 1.1.3 | 图标加载 / 图像处理 | 是 |
| OpenCV | >= 4.x | 屏幕录制视频编码 | 是 |
| NumPy | >= 1.16 | 屏幕帧数据处理 | 是 |
| mss | >= 0.5 | 跨平台屏幕捕获 | 是 |
| pynput | >= 1.7 | 全局热键监听 | 否 |

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Shift+F5` | 停止录制 |
| `Ctrl+Shift+F9` | 暂停 / 继续录制 |

## License

MIT
