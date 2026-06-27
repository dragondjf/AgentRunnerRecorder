# qwen_vl_service.py 新功能说明

## 概述

本次更新为qwen_vl_service.py文件新增了两个核心功能：
1. **非流式AI分析核心函数** (`ai_analysis`)
2. **批量AI分析接口** (`/generateAll`)

## 新增功能

### 1. ai_analysis 核心函数

**功能描述：** 
非流式AI分析函数，支持图片URL或文件路径输入，返回结构化的分析结果。

**函数签名：**
```python
async def ai_analysis(image_source: str, context: str = "", requirements: str = "") -> dict
```

**参数说明：**
- `image_source`: 图片URL或本地文件路径
- `context`: 上下文信息（可选）
- `requirements`: 需求说明（可选）

**返回值：**
```python
{
    "title": "分析出的标题",
    "description": "详细的功能描述"
}
```

**特性：**
- ✅ 支持URL和文件路径两种输入方式
- ✅ 自动下载远程图片并保存到临时文件
- ✅ 自动推断文件扩展名
- ✅ 完善的错误处理和异常捕获
- ✅ 自动清理临时文件

### 2. /generateAll 批量分析接口

**功能描述：**
批量处理指定project目录下records.json中的所有记录，自动下载图片，进行AI分析，并将结果实时回写回文件。

**请求方式：** `POST /generateAll`

**请求参数：**
```json
{
    "project": "项目名称"
}
```

**处理流程：**
1. 根据project参数确定文件路径：`{project}/records.json` 和 `{project}/my_screenshots/`
2. 读取`{project}/records.json`文件
3. 为每个记录：
   - 查找或下载图片到`{project}/my_screenshots`目录
   - 调用`ai_analysis`进行AI分析
   - **立即更新record对象并持久化到文件**
4. 返回处理结果统计

**记录字段更新：**
- `ai_result`: 原始分析结果
- `title`: 从ai_result中解析的标题
- `remark`: 从ai_result中解析的描述

**新增特性：**
- ✅ 支持project参数，多项目隔离
- ✅ **立即数据持久化**，无需等待所有处理完成
- ✅ 优化内存使用，避免大量记录在内存中累积
- ✅ 增强的错误统计和返回信息

**返回结果：**
```python
{
    "success": true,
    "message": "批量处理完成: 成功 5 个, 失败 0 个",
    "total": 5,
    "success_count": 5,
    "error_count": 0,
    "project": "my_project",
    "records_file": "my_project/records.json",
    "screenshots_dir": "my_project/my_screenshots",
    "results": [
        {
            "index": 0,
            "success": true,
            "title": "页面标题",
            "description": "页面功能描述..."
        }
    ]
}
```

## 文件管理

### 项目文件结构
```
{project}/
├── records.json          # 记录文件
└── my_screenshots/       # 截图存储目录
    ├── image1.jpg
    ├── image2.jpg
    └── ...
```

### 关键特性
- **多项目支持**: 通过project参数隔离不同项目
- **立即持久化**: 每次AI分析完成后立即保存到文件
- **自动目录管理**: 自动创建和清理项目目录
- **智能文件名**: 基于URL自动生成文件名

### records.json 格式要求
```json
[
    {
        "id": 1,
        "image_url": "https://example.com/image.jpg",
        "context": "上下文信息",
        "requirements": "分析需求"
    }
]
```

## 错误处理

### ai_analysis函数
- 网络请求超时处理
- 文件下载错误捕获
- JSON解析异常处理
- 临时文件清理保证

### /generateAll接口
- records.json文件不存在检查
- JSON格式验证
- 单个记录处理失败的隔离处理
- 批量处理结果统计

## API接口列表

| 接口 | 方法 | 功能 | 响应类型 |
|------|------|------|----------|
| `/generate` | POST | 流式AI分析 | text/event-stream |
| `/generateAll` | GET,POST | 批量AI分析（流式输出，支持URL参数） | text/event-stream |

## 使用示例

### 单独调用ai_analysis
```python
import asyncio
from qwen_vl_service import ai_analysis

async def example():
    # 使用URL
    result = await ai_analysis(
        "https://example.com/image.jpg",
        "用户界面截图",
        "请生成简洁标题和功能描述"
    )
    
    # 使用文件路径
    result = await ai_analysis(
        "/path/to/image.jpg",
        "本地图片分析",
        "突出核心功能"
    )
    
    print(f"标题: {result['title']}")
    print(f"描述: {result['description']}")
```

### 批量处理（流式输出）
```bash
# GET请求 - 方便调试（推荐）
curl "http://localhost:5000/generateAll?project=my_project"

# POST请求 - JSON数据
curl -X POST http://localhost:5000/generateAll \
  -H "Content-Type: application/json" \
  -d '{"project": "my_project"}'

# POST请求 - form数据
curl -X POST http://localhost:5000/generateAll \
  -d "project=my_project"
```

### 流式输出格式说明
`/generateAll` 接口使用 Server-Sent Events (SSE) 格式实时输出进度信息：

**消息类型:**
- `start`: 开始处理，包含总数量和项目信息
- `progress`: 进度更新，包含当前处理状态（downloading/analyzing/processing）
- `item_complete`: 单个项目完成，包含成功/失败结果
- `complete`: 全部处理完成，包含统计信息
- `error`: 错误信息

**JavaScript客户端示例:**
```javascript
const eventSource = new EventSource('/generateAll', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({project: 'my_project'})
});

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'start':
            console.log(`开始处理 ${data.total} 个项目`);
            break;
        case 'progress':
            console.log(`进度: ${data.current}/${data.total} - ${data.message}`);
            break;
        case 'item_complete':
            if(data.success) {
                console.log(`✅ 项目 ${data.index + 1} 完成: ${data.title}`);
            } else {
                console.log(`❌ 项目 ${data.index + 1} 失败: ${data.error}`);
            }
            break;
        case 'complete':
            console.log(`🎉 全部完成! 成功: ${data.success_count}, 失败: ${data.error_count}`);
            break;
        case 'error':
            console.log(`🚫 错误: ${data.message}`);
            break;
    }
};
```

## 配置要求

### 环境变量
- `MODEL_NAME`: AI模型名称（默认：qwen-vl-max-latest）
- `OPENAI_API_KEY`: API密钥
- `OPENAI_BASE_URL`: API基础URL

### 依赖包
- `flask`: Web框架
- `requests`: HTTP请求
- `PIL`: 图像处理
- `autogen-agentchat`: AI模型交互
- `autogen-core`: 核心功能
- `autogen-ext`: 扩展功能

## 技术特点

1. **非阻塞异步处理**: 使用asyncio实现高效的异步处理
2. **立即数据持久化**: 每次分析完成立即保存，避免数据丢失
3. **内存优化**: 避免大量记录在内存中累积，单条处理后即保存
4. **多项目支持**: 通过project参数实现项目隔离和管理
5. **智能文件管理**: 自动下载、存储和清理机制
6. **容错机制**: 单个记录失败不影响整体处理
7. **JSON结果解析**: 智能提取结构化结果
8. **SSE流式输出**: Server-Sent Events 实时输出进度信息
9. **多状态跟踪**: 区分 downloading/analyzing/processing 等不同处理状态
10. **前端友好**: 完整的 JavaScript EventSource 客户端支持
11. **灵活请求方式**: 支持GET和POST两种请求方式，方便调试和集成
12. **URL参数支持**: GET请求支持URL参数传递项目名称

## 注意事项

1. 确保`{project}/records.json`文件格式正确
2. 项目目录和`my_screenshots`目录需要写入权限
3. 网络请求可能需要代理配置
4. API密钥需要有效且有足够配额
5. 大量批量处理时注意API调用频率限制
6. project参数支持中英文，但建议使用英文避免路径问题
7. 每个项目的文件相互独立，支持多项目并发处理

## 更新日志

- **2025-11-11**: 
  - **v1.0** - 初始实现
    - ✅ ai_analysis核心函数
    - ✅ /generateAll批量接口
    - ✅ 完整错误处理机制
    - ✅ 文档和测试验证
  
  - **v1.1** - 优化和增强
    - ✅ 支持project参数，实现多项目隔离
    - ✅ **立即数据持久化**，优化内存使用
    - ✅ 增强返回信息，包含项目路径
    - ✅ 优化错误处理和统计逻辑
    - ✅ 更新文档和测试验证

## 近期更新 (2025-11-11)

### 主要改进

#### v1.2 - 流式输出增强
1. **SSE流式输出**: `/generateAll` 接口支持 Server-Sent Events 实时输出进度
2. **多类型消息**: 支持 start/progress/item_complete/complete/error 五种消息类型
3. **实时状态更新**: 实时显示 downloading/analyzing/processing 等处理状态
4. **前端友好**: 提供完整的 JavaScript 客户端示例代码

#### v1.3 - 请求方式优化
1. **GET请求支持**: `/generateAll` 现在同时支持GET和POST请求
2. **URL参数**: GET请求支持通过URL参数传递project名称
3. **调试友好**: 简化测试流程，方便开发和调试

#### v1.1 - 性能优化
1. **立即持久化**: 每次AI分析完成后立即保存到records.json，无需等待所有处理完成
2. **项目支持**: 增加project参数，支持多项目管理和隔离
3. **内存优化**: 移除process_all_records中的results列表收集，直接更新记录并保存
4. **增强返回**: 返回结果包含project、records_file、screenshots_dir等信息