"""兼容入口：保留 Flask app、路由和 start_app 导出。"""

from __future__ import annotations

import hmac
from collections import deque
from threading import Lock

from flask import Flask, jsonify, request

from .bootstrap import VERSION, start_app as _start_app
from .config import Config
from .application.chat_orchestrator import core_logic, executor
from .entrypoints.feishu_webhook import handle_feishu_webhook as _handle_feishu_webhook
from .logger import logger
from .ops import check_health
from .security import verify_signature, AESCipher

_APP_LOCK = Lock()
_APP_INSTANCE: Flask | None = None

def _extract_bearer_token(auth_header: str) -> str:
    prefix = "bearer "
    if auth_header.lower().startswith(prefix):
        return auth_header[len(prefix) :].strip()
    return ""


def _is_query_flag_enabled(raw_value: str | None) -> bool:
    return (raw_value or "").strip().lower() in {"1", "true", "yes", "on", "refresh"}


def create_app() -> Flask:
    """创建 Flask app；生产由 WSGI 入口托管，开发模式由 run.py 直接启动。"""
    app = Flask(__name__)
    processed_ids = deque(maxlen=1000)

    def _is_health_detail_authorized() -> bool:
        """只有配置了 HEALTH_AUTH_TOKEN 且请求带正确 header 时返回完整 health。"""
        expected_token = getattr(Config, "HEALTH_AUTH_TOKEN", None)
        if not expected_token:
            return False

        supplied_token = request.headers.get("X-Health-Token", "").strip()
        if not supplied_token:
            supplied_token = _extract_bearer_token(request.headers.get("Authorization", ""))
        return bool(supplied_token) and hmac.compare_digest(supplied_token, expected_token)

    def _is_presence_authorized() -> bool:
        """只有配置了 PRESENCE_AUTH_TOKEN 且 header 正确时才返回观察快照。"""
        expected_token = getattr(Config, "PRESENCE_AUTH_TOKEN", None)
        if not expected_token:
            return False

        supplied_token = request.headers.get("X-Presence-Token", "").strip()
        if not supplied_token:
            supplied_token = _extract_bearer_token(request.headers.get("Authorization", ""))
        return bool(supplied_token) and hmac.compare_digest(supplied_token, expected_token)

    @app.route("/", methods=["POST"])
    def feishu_handler():
        """兼容旧入口：转发到 entrypoints.feishu_webhook。"""
        return _handle_feishu_webhook(
            request,
            config=Config,
            logger_obj=logger,
            processed_ids=processed_ids,
            executor=executor,
            core_logic_fn=core_logic,
            verify_signature_fn=verify_signature,
            cipher_cls=AESCipher,
            jsonify_fn=jsonify,
        )

    # 终端：执行 curl http://localhost:8081/health 你会得到一个 JSON 格式的全身检查报告：
    @app.route("/health", methods=["GET"])
    def health_check_endpoint():
        """健康检查接口。"""
        status = check_health(include_private=_is_health_detail_authorized())
        code = 200 if status["status"] == "healthy" else 503
        return jsonify(status), code

    @app.route("/presence", methods=["GET"])
    def presence_endpoint():
        """实时观察只读接口。"""
        expected_token = getattr(Config, "PRESENCE_AUTH_TOKEN", None)
        if not expected_token:
            return (
                jsonify(
                    {
                        "status": "disabled",
                        "message": "Configure PRESENCE_AUTH_TOKEN to enable /presence.",
                    }
                ),
                503,
            )

        if not _is_presence_authorized():
            return jsonify({"status": "forbidden", "message": "invalid presence token"}), 403

        from .application.observation_service import build_presence_payload

        payload = build_presence_payload(
            request.args.get("user_id"),
            force_refresh=_is_query_flag_enabled(request.args.get("refresh")),
        )
        code = 200 if payload.get("status") == "ok" else 400
        return jsonify(payload), code

    app.extensions["processed_ids"] = processed_ids
    return app


def get_app() -> Flask:
    """返回当前进程内的 canonical Flask app 单例。"""
    global _APP_INSTANCE

    if _APP_INSTANCE is not None:
        return _APP_INSTANCE

    with _APP_LOCK:
        if _APP_INSTANCE is None:
            _APP_INSTANCE = create_app()
    return _APP_INSTANCE


def __getattr__(name: str):
    """兼容旧导入：from app.main import app。"""
    if name == "app":
        return get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def start_app():
    """兼容旧入口：转发到 bootstrap.start_app。"""
    return _start_app(get_app, config=Config, logger_obj=logger, version=VERSION)
