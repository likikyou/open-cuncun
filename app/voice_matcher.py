"""
语音匹配模块
基于 AI 意图提炼 + 向量检索的语音库匹配
"""

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from .config import Config
from .logger import logger
from .observability import record_degradation
from .retrieval import get_embeddings_batch, audio_collection


@dataclass(frozen=True)
class VoiceMatchResult:
    path: str | None
    degraded: bool = False
    reason: str | None = None
    used_fallback: bool = False
    match_source: str | None = None
    matched_filename: str | None = None


def _build_query_attempts(emotion: str | None, theme: str | None) -> list[tuple[str, dict | None]]:
    attempts: list[tuple[str, dict | None]] = []
    emotion_value = (emotion or "").strip()
    theme_value = (theme or "").strip()
    allow_emotion = bool(emotion_value and emotion_value != "平静")
    allow_theme = bool(theme_value and theme_value != "日常")

    if allow_emotion and allow_theme:
        attempts.append(
            (
                "emotion+theme",
                {"$and": [{"emotion": emotion_value}, {"theme": theme_value}]},
            )
        )
    if allow_emotion:
        attempts.append(("emotion", {"emotion": emotion_value}))
    elif allow_theme:
        attempts.append(("theme", {"theme": theme_value}))

    attempts.append(("global", None))
    return attempts


@lru_cache(maxsize=1)
def _load_audio_tag_lexicon() -> tuple[str, ...]:
    tagged_map_path = os.path.join(Config.PROJECT_ROOT, "assets", "voice", "audio_map_tagged.json")
    try:
        with open(tagged_map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        record_degradation(
            "voice_matcher",
            "tag_lexicon_load_failed",
            severity="warning",
            path=tagged_map_path,
            error_type=e.__class__.__name__,
        )
        logger.warning(f"⚠️ 读取语音标签词表失败: {e}")
        return ()

    tags = {str(tag).strip() for item in data for tag in item.get("tags", []) if str(tag).strip()}
    # 先匹配长 tag，避免“关心”先吃掉“默默关心”这类更具体的提示。
    return tuple(sorted(tags, key=len, reverse=True))


def _extract_query_tag_hints(*texts: str) -> set[str]:
    merged = " ".join((text or "").strip() for text in texts if text).strip()
    if not merged:
        return set()
    return {tag for tag in _load_audio_tag_lexicon() if tag in merged}


def _parse_tags(meta: dict | None) -> set[str]:
    if not isinstance(meta, dict):
        return set()
    raw_tags = meta.get("tags", "")
    if not raw_tags:
        return set()
    return {part.strip() for part in str(raw_tags).split(",") if part.strip()}


def _infer_length_type(text: str) -> str:
    length = len((text or "").strip())
    if length <= 16:
        return "short"
    if length <= 48:
        return "medium"
    return "long"


def _pick_existing_audio_path(
    query_result: dict,
    query_tags: set[str] | None = None,
    emotion: str | None = None,
    theme: str | None = None,
    preferred_length_type: str | None = None,
) -> tuple[str | None, float | None, str | None]:
    ids = query_result.get("ids", [[]]) or [[]]
    distances = query_result.get("distances", [[]]) or [[]]
    metadatas = query_result.get("metadatas", [[]]) or [[]]
    candidates = ids[0] if ids else []
    distance_list = distances[0] if distances else []
    metadata_list = metadatas[0] if metadatas else []
    normalized_query_tags = set(query_tags or ())
    expected_emotion = (emotion or "").strip()
    expected_theme = (theme or "").strip()

    ranked_candidates: list[tuple[float, int, int, int, str, float | None, str]] = []

    for idx, matched_filename in enumerate(candidates):
        if not matched_filename:
            continue
        audio_path = os.path.join(Config.VOICE_LIB, matched_filename)
        if not os.path.exists(audio_path):
            logger.warning(f"⚠️ 命中语音文件不存在，跳过: {audio_path}")
            continue
        distance = distance_list[idx] if idx < len(distance_list) else None
        meta = (
            metadata_list[idx]
            if idx < len(metadata_list) and isinstance(metadata_list[idx], dict)
            else {}
        )
        candidate_tags = _parse_tags(meta)
        tag_overlap = len(candidate_tags & normalized_query_tags)
        emotion_match = int(bool(expected_emotion and meta.get("emotion") == expected_emotion))
        theme_match = int(bool(expected_theme and meta.get("theme") == expected_theme))
        length_match = int(
            bool(preferred_length_type and meta.get("length_type") == preferred_length_type)
        )
        semantic_score = max(0.0, 1.5 - float(distance if distance is not None else 1.5))
        score = (
            semantic_score * 3.0
            + tag_overlap * 1.2
            + emotion_match * 0.4
            + theme_match * 0.4
            + length_match * 0.2
        )
        ranked_candidates.append(
            (
                score,
                tag_overlap,
                emotion_match + theme_match,
                length_match,
                audio_path,
                distance,
                matched_filename,
            )
        )

    if ranked_candidates:
        ranked_candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                item[3],
                -(item[5] if item[5] is not None else 99.0),
            ),
            reverse=True,
        )
        best_score, best_tag_overlap, _, _, audio_path, distance, matched_filename = (
            ranked_candidates[0]
        )
        logger.info(
            f"🏷️ 语音候选重排完成: query_tags={sorted(normalized_query_tags)}, "
            f"best_tag_overlap={best_tag_overlap}, best_score={best_score:.3f}, file={matched_filename}"
        )
        return audio_path, distance, matched_filename

    return None, None, None


def _list_available_voice_files() -> list[str]:
    if not os.path.isdir(Config.VOICE_LIB):
        return []
    try:
        return sorted(
            name
            for name in os.listdir(Config.VOICE_LIB)
            if name.lower().endswith((".opus", ".mp3", ".wav", ".m4a"))
        )
    except OSError as e:
        record_degradation(
            "voice_matcher",
            "voice_lib_scan_failed",
            severity="warning",
            voice_lib=Config.VOICE_LIB,
            error_type=e.__class__.__name__,
        )
        logger.warning(f"⚠️ 读取语音目录失败: {e}")
        return []


def _deterministic_fallback_audio(*seed_parts: str) -> str | None:
    voice_files = _list_available_voice_files()
    if not voice_files:
        return None

    seed = "|".join((part or "").strip() for part in seed_parts)
    if not seed:
        seed = "companion_voice_fallback"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(voice_files)
    fallback_name = voice_files[index]
    return os.path.join(Config.VOICE_LIB, fallback_name)


def _build_voice_result(
    path: str | None,
    *,
    degraded: bool = False,
    reason: str | None = None,
    used_fallback: bool = False,
    match_source: str | None = None,
    matched_filename: str | None = None,
) -> VoiceMatchResult:
    return VoiceMatchResult(
        path=path,
        degraded=degraded,
        reason=reason,
        used_fallback=used_fallback,
        match_source=match_source,
        matched_filename=matched_filename,
    )


def _record_voice_degradation(reason: str, *, severity: str = "warning", **details) -> None:
    compact_details = {
        key: value for key, value in details.items() if value is not None and value != ""
    }
    record_degradation("voice_matcher", reason, severity=severity, **compact_details)


def match_voice_file_with_diagnostics(
    user_text: str,
    assistant_reply: str,
    call_ai_summarize_fn,
    pre_extracted_summary: str = None,
    emotion: str = None,
    theme: str = None,
) -> VoiceMatchResult:
    """
    语音库语义匹配（多维灵魂匹配版）：
    1. 前置步骤已在主 prompt 提取出 `emotion` 和 `theme` 以及核心台词
    2. 基于核心台词提取向量
    3. 去 ChromaDB `companion_audio` 先走更严格的 emotion+theme / emotion / theme 过滤
    4. 如果严格过滤没有可用文件，再降级到全局搜索
    """
    # 1. 提炼核心短句及多维元数据
    core_intent = pre_extracted_summary
    if not core_intent:
        summary_res = call_ai_summarize_fn(user_text, assistant_reply)
        if isinstance(summary_res, dict):
            core_intent = summary_res.get("intent", "")
            emotion = summary_res.get("emotion", "平静")
            theme = summary_res.get("theme", "日常")
        elif isinstance(summary_res, str):
            core_intent = summary_res
    if not core_intent:
        # 摘要失败时退回到回复原文，优先保证“有语音”。
        core_intent = (assistant_reply or user_text or "").strip()[:80]
    query_tags = _extract_query_tag_hints(
        core_intent, assistant_reply or "", user_text or "", emotion or "", theme or ""
    )
    preferred_length_type = _infer_length_type(assistant_reply or core_intent or user_text or "")

    fallback_path = _deterministic_fallback_audio(
        core_intent,
        emotion or "",
        theme or "",
        assistant_reply or "",
        user_text or "",
    )

    if audio_collection is None:
        if fallback_path:
            _record_voice_degradation(
                "audio_collection_unavailable",
                severity="warning",
                fallback_audio=os.path.basename(fallback_path),
            )
            logger.warning(
                f"⚠️ audio_collection 未初始化，使用保底语音: {os.path.basename(fallback_path)}"
            )
            return _build_voice_result(
                fallback_path,
                degraded=True,
                reason="audio_collection_unavailable",
                used_fallback=True,
                match_source="deterministic_fallback",
                matched_filename=os.path.basename(fallback_path),
            )
        _record_voice_degradation(
            "audio_collection_unavailable_no_fallback_audio",
            severity="error",
            voice_lib=Config.VOICE_LIB,
        )
        logger.warning("⚠️ audio_collection 未初始化，且保底语音目录不可用")
        return _build_voice_result(
            None,
            degraded=True,
            reason="audio_collection_unavailable_no_fallback_audio",
        )

    if not core_intent:
        if fallback_path:
            _record_voice_degradation(
                "intent_missing_used_fallback_audio",
                severity="info",
                fallback_audio=os.path.basename(fallback_path),
            )
            logger.warning(f"⚠️ 无法提炼语音意图，使用保底语音: {os.path.basename(fallback_path)}")
            return _build_voice_result(
                fallback_path,
                degraded=True,
                reason="intent_missing_used_fallback_audio",
                used_fallback=True,
                match_source="deterministic_fallback",
                matched_filename=os.path.basename(fallback_path),
            )
        _record_voice_degradation(
            "intent_missing_no_fallback_audio",
            severity="warning",
        )
        return _build_voice_result(
            None,
            degraded=True,
            reason="intent_missing_no_fallback_audio",
        )

    try:
        vectors = get_embeddings_batch([core_intent])
        if not vectors:
            if fallback_path:
                _record_voice_degradation(
                    "embedding_unavailable",
                    severity="warning",
                    fallback_audio=os.path.basename(fallback_path),
                )
                logger.warning(f"⚠️ 向量获取失败，回退保底语音: {os.path.basename(fallback_path)}")
                return _build_voice_result(
                    fallback_path,
                    degraded=True,
                    reason="embedding_unavailable",
                    used_fallback=True,
                    match_source="deterministic_fallback",
                    matched_filename=os.path.basename(fallback_path),
                )
            _record_voice_degradation(
                "embedding_unavailable_no_fallback_audio",
                severity="error",
            )
            logger.warning("❌ 向量获取失败，且无可用保底语音")
            return _build_voice_result(
                None,
                degraded=True,
                reason="embedding_unavailable_no_fallback_audio",
            )

        vec = vectors[0]

        for attempt_name, where_filter in _build_query_attempts(emotion, theme):
            kwargs = {"query_embeddings": [vec], "n_results": 8}
            if where_filter:
                kwargs["where"] = where_filter

            res = audio_collection.query(**kwargs)
            docs = res.get("documents", [[]]) or [[]]
            if not docs or not docs[0]:
                logger.info(f"⚠️ 语音匹配 {attempt_name} 未命中，继续降级")
                continue

            audio_path, distance, matched_filename = _pick_existing_audio_path(
                res,
                query_tags=query_tags,
                emotion=emotion,
                theme=theme,
                preferred_length_type=preferred_length_type,
            )
            if audio_path:
                distance_display = f"{distance:.4f}" if distance is not None else "unknown"
                logger.info(
                    f"✨ 语音匹配命中! [提炼={core_intent}, Emotion={emotion}, Theme={theme}, Tags={sorted(query_tags)}, Attempt={attempt_name}] "
                    f"-> {matched_filename} (距离: {distance_display})"
                )
                return _build_voice_result(
                    audio_path,
                    degraded=False,
                    reason=None,
                    used_fallback=False,
                    match_source=attempt_name,
                    matched_filename=matched_filename,
                )

        if fallback_path:
            _record_voice_degradation(
                "semantic_no_hit_used_fallback_audio",
                severity="info",
                fallback_audio=os.path.basename(fallback_path),
            )
            logger.warning(f"⚠️ 语音匹配未命中，回退保底语音: {os.path.basename(fallback_path)}")
            return _build_voice_result(
                fallback_path,
                degraded=True,
                reason="semantic_no_hit_used_fallback_audio",
                used_fallback=True,
                match_source="deterministic_fallback",
                matched_filename=os.path.basename(fallback_path),
            )
        _record_voice_degradation(
            "semantic_no_hit_no_fallback_audio",
            severity="info",
        )
        logger.warning("❌ 语音匹配未达标，且无可用保底语音")

    except Exception as e:
        logger.error(f"语音匹配过程发生异常: {e}", exc_info=True)
        if fallback_path:
            _record_voice_degradation(
                "query_exception_used_fallback_audio",
                severity="warning",
                fallback_audio=os.path.basename(fallback_path),
                error_type=e.__class__.__name__,
            )
            logger.warning(f"⚠️ 语音匹配异常，回退保底语音: {os.path.basename(fallback_path)}")
            return _build_voice_result(
                fallback_path,
                degraded=True,
                reason="query_exception_used_fallback_audio",
                used_fallback=True,
                match_source="deterministic_fallback",
                matched_filename=os.path.basename(fallback_path),
            )
        _record_voice_degradation(
            "query_exception_no_fallback_audio",
            severity="error",
            error_type=e.__class__.__name__,
        )
        return _build_voice_result(
            None,
            degraded=True,
            reason="query_exception_no_fallback_audio",
        )

    return _build_voice_result(
        None,
        degraded=True,
        reason="semantic_no_hit_no_fallback_audio",
    )


def match_voice_file(
    user_text: str,
    assistant_reply: str,
    call_ai_summarize_fn,
    pre_extracted_summary: str = None,
    emotion: str = None,
    theme: str = None,
) -> str | None:
    result = match_voice_file_with_diagnostics(
        user_text,
        assistant_reply,
        call_ai_summarize_fn,
        pre_extracted_summary,
        emotion,
        theme,
    )
    return result.path
