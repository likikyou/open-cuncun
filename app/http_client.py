"""
统一的基础设施模块：HTTP 客户端
复用 requests.Session 提高性能，并提供一致的重试策略和超时配置
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_shared_session() -> requests.Session:
    """创建并统一配置的 HTTP Session"""
    session = requests.Session()

    # 飞书接口可能不是application/json，不在此做全局header强制限定
    # 保留最基础的配置

    # 重试策略
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# 全局单例
http_session = create_shared_session()
