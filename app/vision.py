"""
视觉识别模块
使用阿里 DashScope 的 qwen-vl-plus-latest 视觉模型分析图片
免费期至 2026/04/09
"""

from .config import Config
from .http_client import http_session
from .logger import logger


def _get_image_media_type(image_bytes: bytes) -> str:
    """根据图片文件头判断 MIME 类型"""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    elif image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    elif image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    elif image_bytes[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


def analyze_image(image_bytes: bytes) -> str:
    """
    使用阿里 DashScope 的 qwen-vl-plus-latest 视觉模型分析图片
    免费期至 2026/04/09
    """
    ali_key = Config.ALI_API_KEY
    if not ali_key:
        return "暂时无法查看图片内容（未配置阿里 API Key）"

    import base64

    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    media_type = _get_image_media_type(image_bytes)

    # 阿里 DashScope OpenAI 兼容接口
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {ali_key}", "Content-Type": "application/json"}

    payload = {
        "model": "qwen-vl-plus-latest",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "请非常仔细地观察这张图片的每一个细节。"
                            "你需要准确识别出图片中的主要物体、动物或人物。"
                            "描述时请包括：1. 主体是什么（如果是动物请准确说出种类）"
                            "2. 颜色、形状、大小等特征 3. 所处的环境和背景。"
                            "用简洁的中文回答，100字以内。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{base64_image}"},
                    },
                ],
            }
        ],
        "max_tokens": 300,
    }

    try:
        r = http_session.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code == 200:
            res_data = r.json()
            choices = res_data.get("choices")
            if choices and choices[0] and choices[0].get("message"):
                return choices[0]["message"].get("content", "图片内容识别失败")
            return "图片内容识别失败"
        else:
            logger.error(f"阿里视觉模型请求失败: {r.status_code} {r.text[:200]}")
            return "看起来这张图有点神秘，我竟然没看透..."
    except Exception as e:
        logger.error(f"视觉分析异常: {e}")
        return "哎呀，刚才盯着图看太久，眼睛有点花，没看清内容呢。"
