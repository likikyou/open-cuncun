"""飞书 Webhook 请求处理入口。"""

from __future__ import annotations

import json
import time

from ..logging_privacy import sensitive_text_fields


def _body_text(raw_body: bytes | str) -> str:
    if isinstance(raw_body, bytes):
        return raw_body.decode("utf-8", errors="replace")
    return str(raw_body)


def handle_feishu_webhook(
    request_obj,
    *,
    config,
    logger_obj,
    processed_ids,
    executor,
    core_logic_fn,
    verify_signature_fn,
    cipher_cls,
    jsonify_fn,
):
    """处理飞书回调请求并返回 Flask 响应。"""
    start_ts = time.perf_counter()
    try:
        data = request_obj.get_json(silent=False)
    except Exception:
        logger_obj.warning(
            "❌ Webhook JSON 解析失败",
            extra={
                "content_type": request_obj.content_type,
                **sensitive_text_fields(
                    "body",
                    _body_text(request_obj.get_data(cache=True)),
                    include_content=getattr(config, "LOG_CONTENT_ENABLED", False),
                ),
            },
            exc_info=True,
        )
        return jsonify_fn({"code": 400, "msg": "invalid json"}), 400

    if not isinstance(data, dict) or not data:
        logger_obj.warning(
            "❌ Webhook 请求体为空或不是 JSON 对象",
            extra={
                "content_type": request_obj.content_type,
                **sensitive_text_fields(
                    "body",
                    _body_text(request_obj.get_data(cache=True)),
                    include_content=getattr(config, "LOG_CONTENT_ENABLED", False),
                ),
            },
        )
        return jsonify_fn({"code": 400, "msg": "empty json body"}), 400

    if "encrypt" in data:
        try:
            cipher = cipher_cls(config.FEISHU_ENCRYPT_KEY)
            decrypted_data = cipher.decrypt(data["encrypt"])
            data = json.loads(decrypted_data) if isinstance(decrypted_data, str) else decrypted_data
        except Exception as exc:
            logger_obj.error(
                "❌ 消息解密失败",
                extra={"error_type": exc.__class__.__name__},
            )
            return jsonify_fn({"code": 500}), 500
        if not isinstance(data, dict) or not data:
            logger_obj.error(
                "❌ 消息解密后不是有效 JSON 对象",
                extra={"decrypted_type": type(data).__name__},
            )
            return jsonify_fn({"code": 400, "msg": "invalid encrypted payload"}), 400

    if data.get("type") == "url_verification" or "challenge" in data:
        challenge = data.get("challenge")
        logger_obj.info("✅ 成功响应 Challenge")
        return jsonify_fn({"challenge": challenge})

    if not verify_signature_fn(request_obj.headers, request_obj.data):
        sig = request_obj.headers.get("X-Lark-Signature")
        logger_obj.warning(
            "🚫 签名校验失败",
            extra=sensitive_text_fields("signature", sig),
        )
        return jsonify_fn({"code": 403, "msg": "invalid signature"}), 403

    header = data.get("header", {})
    event_id = header.get("event_id")
    event_type = header.get("event_type") or data.get("type") or ""

    if event_id and event_id in processed_ids:
        if event_type == "card.action.trigger":
            elapsed_ms = round((time.perf_counter() - start_ts) * 1000, 1)
            logger_obj.info(f"🃏 重复卡片回调已快速确认: {elapsed_ms}ms")
        return jsonify_fn({})

    if event_id:
        processed_ids.append(event_id)
        if "event" in data:
            executor.submit(core_logic_fn, data)

    if event_type == "card.action.trigger":
        elapsed_ms = round((time.perf_counter() - start_ts) * 1000, 1)
        logger_obj.info(f"🃏 卡片回调已快速确认: {elapsed_ms}ms")

    return jsonify_fn({})
