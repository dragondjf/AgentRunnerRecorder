import os
import sys
import requests
import tempfile
from urllib.parse import urlparse
import uuid
import numpy as np
import base64
from loguru import logger

def crop_image(path, coord):
    """
    根据给定的坐标和尺寸裁剪图片，并保存到指定路径。
    
    :param input_image_path: 输入图片路径
    :param coord: (x, y, width, height)
    """
    from PIL import Image
    # 打开输入的图像文件
    image = Image.open(path)
    # 裁剪图像
    x = coord[0]
    y = coord[1]
    width = coord[2]
    height = coord[3]
    box = (x, y, x + width, y + height)
    cropped_image = image.crop(box)
    # 保存裁剪后的图像
    filename = os.path.basename(path)
    items = filename.split('.')
    name = items[0]
    ext = items[1]

    name = f'{name}_{x}_{y}_{width}_{height}'
    coord_path = os.path.join(os.path.dirname(path), f'{name}.crop.{ext}')
    cropped_image.save(coord_path)
    return coord_path, cropped_image

def image_to_base64(image_path):
    """将图像文件转换为base64编码的字符串"""
    try:
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
            base64_encoded = base64.b64encode(image_data).decode('utf-8')
            
            # 根据文件扩展名确定MIME类型
            ext = os.path.splitext(image_path)[1].lower()
            if ext in ['.jpg', '.jpeg']:
                mime_type = 'image/jpeg'
            elif ext == '.png':
                mime_type = 'image/png'
            elif ext == '.gif':
                mime_type = 'image/gif'
            else:
                mime_type = 'image/jpeg'  # 默认
            
            return f"data:{mime_type};base64,{base64_encoded}"
    except Exception as e:
        logger.info(f"图像转换为base64失败: {e}")
        return None

def generate_ocr_annotation_image(img_path, results):
    """
    生成OCR标注图像（可选功能，用于可视化OCR结果）
    
    :param image_path: 原图像路径
    :param ocr_result: OCR识别结果
    :return: 标注图像的base64编码
    """
    from PIL import Image, ImageDraw
    # 加载原始图片
    image = Image.open(img_path)
    draw = ImageDraw.Draw(image)

    # 定义高亮样式
    highlight_color = (255, 0, 0)  # 红色边框
    border_width = 1

    # 遍历OCR结果绘制矩形
    for item in results['ocrResult']:
        # 跳过没有坐标信息的结果（如 RapidOCR 回退的纯文本条目）
        if not isinstance(item, dict) or 'location' not in item:
            continue
        loc = item['location']
        left = loc.get('left') or 0
        top = loc.get('top') or 0
        right = loc.get('right')
        bottom = loc.get('bottom')
        # 坐标不完整时跳过
        if right is None or bottom is None:
            continue
        # 绘制矩形（自动适配图片坐标系统）
        draw.rectangle(
            [(left, top), (right, bottom)],
            outline=highlight_color,
            width=border_width
        )

    # 保存临时标注图像
    temp_dir = tempfile.gettempdir()
    filename = f"ocr_annotation_{uuid.uuid4().hex[:8]}.png"
    annotation_path = os.path.join(temp_dir, filename)
    image.save(annotation_path)
    
    # 转换为base64
    base64_image = image_to_base64(annotation_path)
    
    # 清理临时文件
    os.remove(annotation_path)
    
    return base64_image

def gui_ocr(path, coord=None, debug=True, output='json', engine="wechat", **kwargs):
    if os.path.exists(path):
        _path = path
    else:
        raise FileNotFoundError(f"{path}")

    if coord:
        _path, _cropped_image = crop_image(_path, coord=coord)
        # 如果定义了try_log_screen函数，可以调用它进行调试
        # try_log_screen(np.array(_cropped_image, dtype=np.uint8)[..., :3])
        path = _path

    if sys.platform == "win32":
        try:
            from wechat_ocr import ocr
            taskid, result = ocr(_path, debug)
            # logger.info(f"提取文字[{path}]成功")
            if output == 'json':
                return result
            elif output == 'list':
                texts = [item['text'] for item in result['ocrResult']]
                return texts
            else:
                texts = [item['text'] for item in result['ocrResult']]
                return '\n'.join(texts)
        except Exception as e:
            logger.info(f"wechat_ocr 不存在，尝试rapidocr_openvino")


    from rapidocr_openvino import RapidOCR
    class RapidOcr:
        def __init__(self) -> None:
            self.rapid_ocr = RapidOCR()

        def run_ocr(self, path: str):
            """
            运行 RapidOCR 识别。

            :return: 标准结构 {'ocrResult': [{text, confidence, location}, ...]}
                     与微信 OCR 输出结构对齐；识别失败时 ocrResult 为空列表。
            """
            result, elapse = self.rapid_ocr(path)
            items = []
            if result is not None:
                # RapidOCR 返回格式: [[box, text, confidence], ...]
                # box 为 4 个角点坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                for res in result:
                    try:
                        box, text, confidence = res[0], res[1], res[2]
                        xs = [p[0] for p in box]
                        ys = [p[1] for p in box]
                        location = {
                            'left': int(min(xs)),
                            'top': int(min(ys)),
                            'right': int(max(xs)),
                            'bottom': int(max(ys)),
                        }
                        items.append({
                            'text': str(text).replace('\n', ''),
                            'confidence': float(confidence),
                            'location': location,
                        })
                    except Exception as inner_e:
                        logger.info(f"解析RapidOCR单条结果失败: {inner_e}")
            logger.info(items)
            return {'ocrResult': items}

    _ocr_json = RapidOcr().run_ocr(_path)
    if output == 'json':
        return _ocr_json
    elif output == 'list':
        return [item['text'] for item in _ocr_json['ocrResult']]
    else:
        return '\n'.join(item['text'] for item in _ocr_json['ocrResult'])


def gui_web_ocr(image_url, coord=None, debug=True, output='json', engine="wechat", **kwargs):
    """
    支持传入网络图像地址，下载图像后调用gui_ocr进行识别
    
    :param image_url: 网络图像地址
    :param coord: 裁剪坐标 (x, y, width, height)
    :param debug: 是否开启调试模式
    :param output: 输出格式 'text'、'json'、'list'
    :param engine: OCR引擎
    :return: 识别结果和base64编码图像的字典
    """
    # 验证URL格式
    from urllib.parse import unquote
    image_url = unquote(image_url)
    parsed_url = urlparse(image_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError(f"无效的URL格式: {image_url}")
    
    # 下载图像
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # 获取文件扩展名
        content_type = response.headers.get('content-type', '')
        if 'jpeg' in content_type or 'jpg' in content_type:
            ext = 'jpg'
        elif 'png' in content_type:
            ext = 'png'
        elif 'gif' in content_type:
            ext = 'gif'
        else:
            # 从URL中获取扩展名，或默认使用png
            path = parsed_url.path
            if '.' in path:
                ext = path.split('.')[-1].lower()
                if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                    ext = 'png'
            else:
                ext = 'png'
        
        # 创建临时文件
        temp_dir = tempfile.gettempdir()
        filename = f"web_ocr_{uuid.uuid4().hex[:8]}.{ext}"
        local_image_path = os.path.join(temp_dir, filename)
        
        # 保存图像到本地
        with open(local_image_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"图像已下载到: {local_image_path}")
        
        # 调用gui_ocr进行识别
        ocr_result = gui_ocr(local_image_path, coord=coord, debug=debug, output=output, engine=engine, **kwargs)

        # 统一OCR结果为标准结构：{ocrResult: [{text, confidence, location}, ...]}
        # 当回退到 RapidOCR 时，gui_ocr 返回的是纯文本字符串，需要转换为标准结构
        normalized_ocr = None
        if isinstance(ocr_result, dict) and 'ocrResult' in ocr_result:
            normalized_ocr = ocr_result
        elif isinstance(ocr_result, list):
            # 兼容返回 list 的情况
            items = []
            for t in ocr_result:
                if isinstance(t, dict):
                    items.append(t)
                else:
                    items.append({'text': str(t)})
            normalized_ocr = {'ocrResult': items}
        elif isinstance(ocr_result, str):
            # RapidOCR 回退：纯文本字符串，转换为单个条目
            normalized_ocr = {'ocrResult': [{'text': ocr_result}]}
        else:
            # 兜底：空结果
            normalized_ocr = {'ocrResult': []}

        # 生成OCR标注图像（如果可能）
        ocr_annotation_base64 = None
        if normalized_ocr['ocrResult']:
            try:
                ocr_annotation_base64 = generate_ocr_annotation_image(local_image_path, normalized_ocr)
            except Exception as e:
                logger.info(f"生成OCR标注图像失败: {e}")
                ocr_annotation_base64 = None
        
        # 清理临时文件
        os.remove(local_image_path)
        logger.info(normalized_ocr)
        # 返回结果
        texts = [item.get('text', '') for item in normalized_ocr['ocrResult']]
        ocr_text = '\n'.join(texts)
        result = {
            'ocr_result': normalized_ocr,
            'ocr_annotation_base64': ocr_annotation_base64,
            'ocr_text': ocr_text
        }
        return result
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"下载图像失败: {e}")
    except Exception as e:
        # 确保清理临时文件
        if 'local_image_path' in locals() and os.path.exists(local_image_path):
            os.remove(local_image_path)
        raise Exception(f"OCR处理失败: {e}")


if __name__ == '__main__':
    text = gui_ocr("./test.png")
    result = gui_web_ocr("http%3A%2F%2F127.0.0.1%3A52001%2Fmy_screenshots%2Fstep_1_20251113T154154830Z.png")
    logger.info(result['ocr_text'])