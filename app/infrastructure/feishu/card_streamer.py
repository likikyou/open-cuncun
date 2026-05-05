"""飞书流式投递与文本降级。"""

from __future__ import annotations

import inspect
import queue
import threading
import time
from typing import Any, Mapping

from ...domain.reply_text import normalize_reply_text
from .messenger import (
    create_streaming_card,
    finish_streaming,
    send_card_message,
    send_feishu,
    stream_update_card_text,
)
from ...logger import logger

# CardKit 流式更新 QPS 限制：5 QPS，故每 0.2s 更新一次是安全的。
_UPDATE_INTERVAL = 0.2


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def _call_with_optional_deps(fn, *args, deps: Mapping[str, Any] | None = None, **kwargs):
    """兼容旧签名：仅在目标函数支持时才透传 deps。"""
    if deps is None:
        return fn(*args, **kwargs)

    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        params = ()

    supports_deps = any(
        param.kind == inspect.Parameter.VAR_KEYWORD or param.name == "deps" for param in params
    )
    if supports_deps:
        return fn(*args, deps=deps, **kwargs)
    return fn(*args, **kwargs)


def prepare_streaming_card(open_id: str, *, deps: Mapping[str, Any] | None = None) -> str | None:
    """准备并发送流式卡片，成功时返回 card_id。"""
    create_streaming_card_fn = _get_dep(deps, "create_streaming_card", create_streaming_card)
    send_card_message_fn = _get_dep(deps, "send_card_message", send_card_message)
    logger_obj = _get_dep(deps, "logger", logger)

    try:
        card_id = create_streaming_card_fn()
        if not card_id:
            return None

        message_id = send_card_message_fn(open_id, card_id)
        if message_id:
            return card_id

        logger_obj.warning("⚠️ 流式卡片已创建但发送失败，改走普通文本流式降级")
    except Exception as exc:
        logger_obj.error(f"❌ 飞书流式卡片初始化异常: {exc}")
    return None


def _stream_text_chunks(
    open_id: str,
    ai_iterator,
    initial_text: str = "",
    *,
    deps: Mapping[str, Any] | None = None,
) -> str:
    """降级为普通文本单次发送，避免拆成多条消息。"""
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    normalize_reply_text_fn = _get_dep(deps, "normalize_reply_text", normalize_reply_text)
    logger_obj = _get_dep(deps, "logger", logger)

    accumulated = initial_text

    try:
        for chunk in ai_iterator:
            accumulated += chunk
    except Exception as exc:
        logger_obj.error(f"❌ 降级流式文本发送异常: {exc}")
        accumulated += "\n[系统错误：生成中断]"

    final_text = normalize_reply_text_fn(accumulated)
    if final_text:
        send_feishu_fn(open_id, "text", {"text": final_text})
    return final_text


def _card_updater(
    update_queue: queue.Queue,
    update_result: dict,
    *,
    deps: Mapping[str, Any] | None = None,
) -> None:
    """后台卡片更新线程。"""
    stream_update_card_text_fn = _get_dep(deps, "stream_update_card_text", stream_update_card_text)
    logger_obj = _get_dep(deps, "logger", logger)

    while True:
        task = update_queue.get()
        if task is None:
            break

        card_id, text, seq = task
        display_text = text.strip() or "思考中..."
        try:
            ok = stream_update_card_text_fn(card_id, display_text, seq)
            update_result["last_ok"] = ok
            update_result["last_seq"] = seq
            if ok:
                update_result["success_count"] = update_result.get("success_count", 0) + 1
            else:
                update_result["fail_count"] = update_result.get("fail_count", 0) + 1
        except Exception as exc:
            logger_obj.warning(f"⚠️ 卡片更新异常 seq={seq}: {exc}")
            update_result["last_ok"] = False
            update_result["fail_count"] = update_result.get("fail_count", 0) + 1
        finally:
            update_queue.task_done()


def stream_to_card(
    card_id: str,
    first_chunk: str,
    ai_iterator,
    *,
    deps: Mapping[str, Any] | None = None,
) -> str:
    """将 AI 流式输出推送到飞书卡片，返回完整回复文本。"""
    logger_obj = _get_dep(deps, "logger", logger)
    time_module = _get_dep(deps, "time", time)
    queue_module = _get_dep(deps, "queue", queue)
    threading_module = _get_dep(deps, "threading", threading)
    card_updater_fn = _get_dep(deps, "card_updater", _card_updater)
    normalize_reply_text_fn = _get_dep(deps, "normalize_reply_text", normalize_reply_text)
    stream_update_card_text_fn = _get_dep(deps, "stream_update_card_text", stream_update_card_text)
    finish_streaming_fn = _get_dep(deps, "finish_streaming", finish_streaming)

    t0 = time_module.perf_counter()
    accumulated_text = first_chunk
    last_update_time = time_module.time()
    sequence = 1

    update_queue = queue_module.Queue()
    update_result = {"last_ok": False, "last_seq": 0, "success_count": 0, "fail_count": 0}

    updater_thread = threading_module.Thread(
        target=_call_with_optional_deps,
        args=(card_updater_fn, update_queue, update_result),
        kwargs={"deps": deps},
        daemon=True,
    )
    updater_thread.start()

    try:
        update_queue.put((card_id, normalize_reply_text_fn(accumulated_text), sequence))
        sequence += 1

        for chunk in ai_iterator:
            accumulated_text += chunk
            now = time_module.time()
            if now - last_update_time >= _UPDATE_INTERVAL:
                update_queue.put((card_id, normalize_reply_text_fn(accumulated_text), sequence))
                sequence += 1
                last_update_time = now

        update_queue.put((card_id, normalize_reply_text_fn(accumulated_text), sequence))
        sequence += 1
    except Exception as exc:
        logger_obj.error(f"❌ AI 流式生成异常: {exc}")
        accumulated_text += "\n[系统错误：生成中断]"
        update_queue.put((card_id, normalize_reply_text_fn(accumulated_text), sequence))
        sequence += 1
    finally:
        update_queue.put(None)
        updater_thread.join(timeout=15)

        final_text = normalize_reply_text_fn(accumulated_text)
        if final_text and update_result.get("success_count", 0) == 0:
            logger_obj.warning(
                f"⚠️ 异步更新全部失败({update_result.get('fail_count', 0)}次)，执行同步保底推送 seq={sequence}"
            )
            try:
                ok = stream_update_card_text_fn(card_id, final_text, sequence)
                if ok:
                    logger_obj.info("✅ 同步保底推送成功")
                    sequence += 1
                else:
                    logger_obj.error("❌ 同步保底推送也失败")
            except Exception as exc:
                logger_obj.error(f"❌ 同步保底推送异常: {exc}")

        if update_result.get("fail_count", 0) > 0:
            logger_obj.warning(
                f"⚠️ 卡片更新统计: 成功={update_result.get('success_count', 0)}, 失败={update_result.get('fail_count', 0)}"
            )

        if not finish_streaming_fn(card_id, sequence):
            logger_obj.warning(f"⚠️ 流式关闭失败 card_id={card_id}，卡片可能处于持续流式状态")

    logger_obj.info("💬 流式回复成功")
    logger_obj.info(
        f"⏱️ [性能] stream_to_card 总耗时: {(time_module.perf_counter() - t0) * 1000:.0f}ms"
    )
    return final_text


def stream_reply(
    open_id: str,
    ai_iterator,
    *,
    first_chunk: str = "",
    card_id: str | None = None,
    deps: Mapping[str, Any] | None = None,
) -> str:
    """优先流式卡片投递，失败时降级为普通文本流式。"""
    stream_to_card_fn = _get_dep(deps, "stream_to_card", stream_to_card)
    stream_text_chunks_fn = _get_dep(deps, "stream_text_chunks", _stream_text_chunks)
    logger_obj = _get_dep(deps, "logger", logger)

    if card_id:
        return _call_with_optional_deps(
            stream_to_card_fn,
            card_id,
            first_chunk,
            ai_iterator,
            deps=deps,
        )

    logger_obj.warning("⚠️ 流式卡片创建失败，降级为普通文本单次发送模式")
    return _call_with_optional_deps(
        stream_text_chunks_fn,
        open_id,
        ai_iterator,
        initial_text=first_chunk,
        deps=deps,
    )
