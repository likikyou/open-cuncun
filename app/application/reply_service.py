"""回复生成编排服务。"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Mapping, TypedDict

from ..ai_engine import call_ai_stream, call_ai_summarize
from ..domain.query_intent import is_current_time_query, is_weather_query
from ..domain.reply_text import normalize_reply_text
from ..infrastructure.feishu import send_feishu
from ..infrastructure.feishu.card_streamer import prepare_streaming_card, stream_reply
from ..infrastructure.persistence.sqlite_history_repo import get_recent_history
from ..infrastructure.persistence.sqlite_settings_repo import get_user_setting
from ..logger import logger
from ..prompt_builder import build_prompt
from ..tools_registry import build_current_time_reply


class ReplyResult(TypedDict):
    reply_text: str
    summary: dict | None


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def generate_reply(
    open_id: str,
    user_text: str,
    history=None,
    *,
    deps: Mapping[str, Any] | None = None,
) -> ReplyResult:
    """生成回复并协调投递准备。"""
    get_user_setting_fn = _get_dep(deps, "get_user_setting", get_user_setting)
    build_prompt_fn = _get_dep(deps, "build_prompt", build_prompt)
    get_recent_history_fn = _get_dep(deps, "get_recent_history", get_recent_history)
    call_ai_stream_fn = _get_dep(deps, "call_ai_stream", call_ai_stream)
    call_ai_summarize_fn = _get_dep(deps, "call_ai_summarize", call_ai_summarize)
    prepare_streaming_card_fn = _get_dep(deps, "prepare_streaming_card", prepare_streaming_card)
    stream_reply_fn = _get_dep(deps, "stream_reply", stream_reply)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    normalize_reply_text_fn = _get_dep(deps, "normalize_reply_text", normalize_reply_text)
    logger_obj = _get_dep(deps, "logger", logger)
    time_module = _get_dep(deps, "time", time)
    queue_module = _get_dep(deps, "queue", queue)
    threading_module = _get_dep(deps, "threading", threading)

    t0 = time_module.perf_counter()
    direct_current_time_reply = is_current_time_query(user_text) and not is_weather_query(user_text)
    reply_mode = "normal" if direct_current_time_reply else get_user_setting_fn(
        open_id, "reply_mode", "normal"
    )
    prompt = "" if direct_current_time_reply else build_prompt_fn(user_text)

    if history is None and not direct_current_time_reply:
        history = get_recent_history_fn(open_id, limit=12)
    elif history is None:
        history = []

    if direct_current_time_reply:
        logger_obj.info("⏰ 当前时间问句命中确定性本地回复")
        direct_reply = normalize_reply_text_fn(build_current_time_reply(user_text))
        send_feishu_fn(open_id, "text", {"text": direct_reply})
        summary_info = {"intent": "报当前时间", "emotion": "傲娇", "theme": "日常"}
        logger_obj.info(
            f"⏱️ [性能] generate_reply 总耗时: {(time_module.perf_counter() - t0) * 1000:.0f}ms"
        )
        return {"reply_text": direct_reply, "summary": summary_info}

    card_id_queue = queue_module.Queue(maxsize=1)

    def _prepare_streaming_card_task() -> None:
        card_id = None
        try:
            card_id = prepare_streaming_card_fn(open_id)
        finally:
            card_id_queue.put(card_id)

    threading_module.Thread(target=_prepare_streaming_card_task, daemon=True).start()

    summary_info = None
    ai_iterator = call_ai_stream_fn(prompt, user_text, history, reply_mode=reply_mode, user_id=open_id)

    try:
        first_chunk = next(ai_iterator)
    except StopIteration:
        first_chunk = ""
    except Exception as exc:
        logger_obj.error(f"❌ AI 首包预取异常: {exc}")
        first_chunk = "我有点累了，稍等一下。"
        ai_iterator = iter(())

    t1 = time_module.perf_counter()
    try:
        card_id = card_id_queue.get(timeout=15)
    except queue_module.Empty:
        logger_obj.warning("⚠️ 等待流式卡片初始化超时，改走普通文本流式降级")
        card_id = None
    t2 = time_module.perf_counter()
    logger_obj.info(f"⏱️ [性能] 等待卡片创建: {(t2 - t1) * 1000:.0f}ms")

    raw_reply = stream_reply_fn(open_id, ai_iterator, first_chunk=first_chunk, card_id=card_id)
    clean_reply = normalize_reply_text_fn(raw_reply)
    if summary_info is None:
        summary_info = call_ai_summarize_fn(user_text, clean_reply)

    logger_obj.info(
        f"⏱️ [性能] generate_reply 总耗时: {(time_module.perf_counter() - t0) * 1000:.0f}ms"
    )
    return {"reply_text": clean_reply, "summary": summary_info}
