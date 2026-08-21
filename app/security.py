"""
安全模块
飞书签名校验 & AES 加密/解密
"""

import hashlib
import base64
import json
import time
from typing import Dict, Union
from Crypto.Cipher import AES
from .config import Config
from .logger import logger


def verify_signature(request_headers: Dict[str, str], request_body: bytes) -> bool:
    """
    🛡️ 飞书签名校验 (V2.0 算法)
    算法文档: https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-guide#52563345

    计算公式: sha256(timestamp + nonce + encrypt_key + body)
    """
    encrypt_key = Config.FEISHU_ENCRYPT_KEY
    # 如果没有配置 key，则跳过校验（开发模式）
    if not encrypt_key:
        return True

    timestamp = request_headers.get("X-Lark-Request-Timestamp")
    nonce = request_headers.get("X-Lark-Request-Nonce")
    signature = request_headers.get("X-Lark-Signature")

    if not all([timestamp, nonce, signature]):
        logger.warning("签名校验失败: 缺少必要 Header")
        return False

    # 1. 防重放攻击：仅对数值时间戳启用 5 分钟窗口校验。
    # 某些飞书卡片回调链路会带上格式化时间字符串，此时仍需继续按原始值参与签名计算。
    try:
        req_time = float(timestamp)
        if abs(time.time() - req_time) > 300:
            logger.warning(f"签名校验失败: 请求已过期 (timestamp={timestamp})")
            return False
    except (TypeError, ValueError):
        logger.info(f"签名校验: 检测到非数字时间戳，跳过过期校验 (timestamp={timestamp})")

    try:
        # 2. 构造签名内容：timestamp + nonce + encrypt_key + body_str
        # 注意：飞书要求 body 必须是原始的 bytes 对应的字符串
        content = timestamp + nonce + encrypt_key + request_body.decode("utf-8")

        # 3. 计算 SHA256
        local_sig = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if local_sig == signature:
            return True
        else:
            logger.warning(f"签名不匹配! 远程:{signature[:8]}... 本地:{local_sig[:8]}...")
            return False
    except Exception as e:
        logger.error(f"签名校验异常: {e}")
        return False


class AESCipher:
    """飞书消息 AES 解密器"""

    def __init__(self, key: str):
        # 飞书加密 Key 需要先进行 sha256 摘要
        self.key = hashlib.sha256(key.encode("utf-8")).digest()

    def decrypt(self, encrypt_text: str) -> Union[Dict, str, None]:
        """
        解密飞书推送的加密消息
        :param encrypt_text: base64 编码的密文
        :return: 解密后的 JSON 对象或字符串
        """
        try:
            encrypt_bytes = base64.b64decode(encrypt_text)
            iv = encrypt_bytes[:16]
            cipher = AES.new(self.key, AES.MODE_CBC, iv)
            decrypted_bytes = cipher.decrypt(encrypt_bytes[16:])

            # 移除 PKCS7 填充
            padding_len = decrypted_bytes[-1]
            # 校验 padding 是否合法
            if padding_len < 1 or padding_len > 16:
                raise ValueError("Invalid padding length")

            decrypted_content = decrypted_bytes[:-padding_len].decode("utf-8")
            return json.loads(decrypted_content)
        except Exception as e:
            logger.error(f"AES 解密失败: {e}")
            return None
