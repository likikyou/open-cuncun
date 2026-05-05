"""飞书 client 与 token 管理。"""

from __future__ import annotations

import time
from threading import Lock
from typing import Optional

import requests

from ...config import Config
from ...logger import logger
from ...http_client import http_session


class FeishuClient:
    """飞书 API 客户端，单例模式管理 Token 和 HTTP Session。"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(FeishuClient, cls).__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._token_cache = {"token": None, "expires_at": 0}
        self._token_lock = Lock()
        self.session = http_session

    def get_token(self) -> Optional[str]:
        current_time = time.time()
        if self._token_cache["token"] and current_time < self._token_cache["expires_at"] - 300:
            return self._token_cache["token"]

        with self._token_lock:
            if self._token_cache["token"] and current_time < self._token_cache["expires_at"] - 300:
                return self._token_cache["token"]

            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            try:
                response = requests.post(
                    url,
                    json={
                        "app_id": Config.FEISHU_APP_ID,
                        "app_secret": Config.FEISHU_APP_SECRET,
                    },
                    timeout=10,
                )
                data = response.json()
                if data.get("code") == 0 and "tenant_access_token" in data:
                    token = data["tenant_access_token"]
                    self._token_cache["token"] = token
                    self._token_cache["expires_at"] = current_time + data.get("expire", 7200)
                    return token
                logger.error(f"❌ Token 获取失败: {data}")
            except Exception as exc:
                logger.error(f"❌ Token 获取异常: {exc}")
            return None

    def request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        token = self.get_token()
        if not token:
            logger.error("❌ 无法获取 Token，跳过请求")
            return None

        headers = kwargs.get("headers", {})
        if "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers

        try:
            response = self.session.request(method, url, **kwargs)
            if response.status_code != 200:
                logger.warning(f"⚠️ API 请求返回 {response.status_code}: {url}")
            return response
        except Exception as exc:
            logger.error(f"❌ API 请求异常 [{method} {url}]: {exc}")
            return None


feishu_client = FeishuClient()


def get_token() -> Optional[str]:
    """兼容旧入口：获取 token。"""
    return feishu_client.get_token()
