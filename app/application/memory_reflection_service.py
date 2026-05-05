"""仿生记忆反思与检索应用服务。"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from typing import Optional

from ..config import Config
from ..infrastructure.persistence.sqlite_memory_repo import (
    boost_memory_recall,
    bump_relationship_stage,
    get_active_memories,
    get_bionic_state,
    increment_reflection_count,
    init_bionic_state,
    save_bionic_memory,
    update_bionic_mood,
)
from ..domain.memory_rules import (
    adjust_importance_for_memory_scope,
    clamp_importance,
    classify_reflection_scope,
    describe_relationship_stage,
    describe_runtime_mood,
    get_mood_intensity,
    get_relationship_stage_delta,
    should_include_memory_in_context,
    should_save_reflection_scope,
)
from ..infrastructure.ai import get_active_client
from ..infrastructure.ai.provider_health import record_provider_failure, record_provider_success
from ..logger import logger
from ..retrieval import bio_collection, get_embedding

_reflection_locks = defaultdict(threading.Lock)
_locks_lock = threading.Lock()


def _get_user_lock(user_id: str) -> threading.Lock:
    """获取指定用户的反思锁，同一用户串行化。"""
    with _locks_lock:
        return _reflection_locks[user_id]


_chatanywhere_client = None
try:
    from openai import OpenAI as _OpenAI

    if Config.CHATANYWHERE_API_KEY:
        _chatanywhere_client = _OpenAI(
            api_key=Config.CHATANYWHERE_API_KEY,
            base_url="https://api.chatanywhere.tech/v1",
        )
except Exception as exc:
    logger.debug(f"ChatAnywhere 客户端初始化跳过: {exc}")

_THEME_KEYWORDS = {
    "工作": ("工作", "老板", "同事", "开会", "加班", "任务", "项目", "上班"),
    "健康": ("生病", "医院", "头疼", "牙", "刷牙", "睡觉", "失眠", "胃", "身体"),
    "生活": ("吃饭", "睡觉", "回家", "出门", "天气", "下雨", "今天", "明天"),
    "情绪": ("难过", "伤心", "委屈", "烦", "焦虑", "生气", "崩溃"),
    "恋爱": ("喜欢", "想你", "爱你", "抱抱", "亲亲", "撒娇", "想见你"),
    "成长": ("学习", "进步", "坚持", "努力", "计划", "目标"),
    "回忆": ("以前", "之前", "那次", "记得", "回忆"),
}
_EMOTION_KEYWORDS = {
    "开心": ("开心", "高兴", "不错", "幸福", "轻松", "满足"),
    "感动": ("感动", "谢谢", "暖心", "治愈"),
    "焦虑": ("焦虑", "担心", "害怕", "紧张", "不安"),
    "难过": ("难过", "伤心", "委屈", "失落", "心疼"),
    "愤怒": ("生气", "气死", "愤怒", "烦死", "过分"),
    "撒娇": ("撒娇", "抱抱", "亲亲", "陪我", "哄我"),
    "思念": ("想你", "想见", "挂念", "思念"),
}
_HIGH_IMPORTANCE_KEYWORDS = {
    "辞职",
    "分手",
    "生病",
    "住院",
    "吵架",
    "结婚",
    "搬家",
    "考试",
    "面试",
    "崩溃",
}


def _guess_theme(text: str) -> str:
    text = text or ""
    for theme, keywords in _THEME_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return theme
    return "其他"


def _guess_emotion(text: str) -> str:
    text = text or ""
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return emotion
    return "平静"


def _estimate_importance(user_text: str, assistant_reply: str, emotion: str) -> float:
    combined = f"{user_text}\n{assistant_reply}"
    importance = 0.4
    if len((user_text or "").strip()) >= 40:
        importance += 0.1
    if emotion in {"难过", "愤怒", "焦虑", "感动", "思念"}:
        importance += 0.1
    if any(keyword in combined for keyword in _HIGH_IMPORTANCE_KEYWORDS):
        importance += 0.2
    return clamp_importance(importance)


def _build_reflection_fallback(user_text: str, assistant_reply: str) -> tuple[str, str, str, float]:
    preview = " ".join((user_text or "").strip().split())
    if len(preview) > 80:
        preview = preview[:80].rstrip() + "..."

    combined = f"{user_text}\n{assistant_reply}"
    theme = _guess_theme(combined)
    emotion = _guess_emotion(combined)
    importance = _estimate_importance(user_text, assistant_reply, emotion)
    content = f"他提到“{preview}”，她接住了他的情绪并继续陪着他。"
    return content, theme, emotion, importance


def _call_ai_cheap(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
    """
    优先用 ChatAnywhere 做低成本推理，失败降级到主引擎。
    用于反思和整合等后台任务。
    """
    if _chatanywhere_client:
        try:
            response = _chatanywhere_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content:
                return content.strip()
        except Exception as exc:
            logger.warning(f"⚠️ ChatAnywhere 调用失败 (仿生记忆): {exc}")

    client, model, provider_name = get_active_client()
    if not client:
        return ""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        record_provider_success(provider_name, operation="background_cheap", stream=False)
        return content.strip() if content else ""
    except Exception as exc:
        record_provider_failure(
            provider_name,
            error_type=exc.__class__.__name__,
            operation="background_cheap",
            stream=False,
        )
        logger.error(f"❌ 仿生记忆 AI 调用失败 [{provider_name}]: {exc}")
        return ""


def call_low_cost_ai(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
    """显式导出的低成本 LLM 调用入口。"""
    return _call_ai_cheap(system_prompt, user_prompt, max_tokens=max_tokens)


def reflect_on_conversation(user_id: str, user_text: str, assistant_reply: str) -> Optional[int]:
    """把一轮对话提炼成一条记忆碎片。"""
    if not user_text or not assistant_reply:
        return None
    if len(user_text) < 5 and len(assistant_reply) < 20:
        return None

    user_lock = _get_user_lock(user_id)
    with user_lock:
        return _do_reflect(user_id, user_text, assistant_reply)


def _do_reflect(user_id: str, user_text: str, assistant_reply: str) -> Optional[int]:
    """实际执行反思逻辑。"""
    init_bionic_state(user_id)

    system_prompt = (
        "你是一个记忆编码器。你需要将一段对话提炼为一条简洁的记忆碎片。\n"
        "只把用户明确表达的事实、情绪、共同经历、共同约定或关系变化写入记忆。"
        "如果助手回复里出现明星客户、出行安排、地点、直播间等临场剧情，"
        "但用户没有明确把它作为双方真实约定或共同经历确认，不要把这些当成事实。\n"
        "请严格按照以下 JSON 格式输出，不要包含任何其他文字：\n"
        "{\n"
        '  "content": "用一两句话概括这段对话的核心事实或情感（第三人称视角）",\n'
        '  "theme": "主题标签（从以下选择：恋爱、工作、健康、生活、情绪、成长、回忆、其他）",\n'
        '  "emotion": "情感标签（从以下选择：开心、感动、焦虑、难过、愤怒、平静、撒娇、思念）",\n'
        '  "importance": 0.1到1.0之间的数字（0.1=闲聊寒暄，0.5=日常话题，0.8=重要事件，1.0=人生里程碑）, \n'
        '  "scope": "从 shared_experience/user_fact/relationship_moment/assistant_private_claim/ephemeral 中选择。一起吃饭、一起玩、约会、见面、共同纪念优先 shared_experience；只来自助手回复的私人行程/明星客户优先 assistant_private_claim。"\n'
        "}"
    )
    user_prompt = f"【用户说】\n{user_text[:500]}\n\n【助手回复】\n{assistant_reply[:500]}"

    start_time = time.time()
    raw = _call_ai_cheap(system_prompt, user_prompt, max_tokens=200)
    fallback_content, fallback_theme, fallback_emotion, fallback_importance = (
        _build_reflection_fallback(
            user_text,
            assistant_reply,
        )
    )
    if not raw:
        logger.warning("⚠️ 反思引擎：AI 返回为空，改用本地兜底编码")
        content = fallback_content
        theme = fallback_theme
        emotion = fallback_emotion
        importance = fallback_importance
    else:
        try:
            json_str = raw
            if "```" in raw:
                import re

                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
                if match:
                    json_str = match.group(1)

            data = json.loads(json_str)
            content = data.get("content", "") or fallback_content
            theme = data.get("theme", fallback_theme) or fallback_theme
            emotion = data.get("emotion", fallback_emotion) or fallback_emotion
            importance = clamp_importance(float(data.get("importance", fallback_importance)))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning(f"⚠️ 反思引擎 JSON 解析失败: {exc}，改用本地兜底编码")
            content = fallback_content
            theme = fallback_theme
            emotion = fallback_emotion
            importance = fallback_importance

    if not content:
        return None

    memory_scope = classify_reflection_scope(user_text, assistant_reply, content)
    importance = adjust_importance_for_memory_scope(importance, memory_scope)
    if not should_save_reflection_scope(memory_scope):
        logger.info(
            "🧠 反思引擎跳过临场私人剧情",
            extra={"memory_scope": memory_scope, "content_preview": content[:120]},
        )
        return None

    memory_id = save_bionic_memory(
        user_id=user_id,
        content=content,
        theme=theme,
        emotion=emotion,
        importance=importance,
        memory_type="reflection",
    )

    if memory_id and bio_collection is not None:
        try:
            vector = get_embedding(content)
            if vector:
                bio_collection.add(
                    ids=[f"bionic_{memory_id}"],
                    embeddings=[vector],
                    documents=[content],
                    metadatas=[
                        {
                            "memory_id": memory_id,
                            "user_id": user_id,
                            "theme": theme,
                            "emotion": emotion,
                            "importance": importance,
                            "source": "bionic_reflection",
                        }
                    ],
                )
        except Exception as exc:
            logger.warning(f"⚠️ 仿生记忆向量化失败（不影响文本记忆）: {exc}")

    _update_runtime_state(user_id, emotion, importance)

    duration = time.time() - start_time
    logger.info(
        f"🧠 反思引擎完成 | 主题={theme} 情感={emotion} "
        f"重要度={importance:.1f} 耗时={duration:.1f}s"
    )
    return memory_id


def _update_runtime_state(user_id: str, emotion: str, importance: float) -> None:
    """更新运行时情绪、关系阶段和反思计数。"""
    update_bionic_mood(user_id, emotion, get_mood_intensity(emotion, importance))

    delta = get_relationship_stage_delta(emotion, importance)
    if delta != 0:
        bump_relationship_stage(user_id, delta=delta)

    increment_reflection_count(user_id)


def retrieve_bionic_memories(user_id: str, query_text: str, n_results: int = 3) -> str:
    """检索仿生记忆，并触发回忆加固。"""
    matched_memory_ids = set()
    results_text = []

    if bio_collection is not None:
        try:
            vector = get_embedding(query_text)
            if vector:
                result = bio_collection.query(
                    query_embeddings=[vector],
                    n_results=n_results * 3,
                    where={"user_id": user_id},
                )
                if result["documents"] and result["documents"][0]:
                    filtered_docs = []
                    filtered_metas = []
                    filtered_distances = []
                    for idx, doc in enumerate(result["documents"][0]):
                        meta = (
                            result["metadatas"][0][idx]
                            if (result.get("metadatas") and result["metadatas"][0])
                            else {}
                        )
                        source = meta.get("source", "") if meta else ""
                        if source in ["bionic_reflection", "bionic_consolidation"]:
                            filtered_docs.append(doc)
                            filtered_metas.append(meta)
                            filtered_distances.append(
                                result["distances"][0][idx] if result.get("distances") else 0
                            )
                    result = {
                        "documents": [filtered_docs[:n_results]],
                        "metadatas": [filtered_metas[:n_results]],
                        "distances": [filtered_distances[:n_results]],
                    }
                if result["documents"] and result["documents"][0]:
                    for idx, doc in enumerate(result["documents"][0]):
                        meta = result["metadatas"][0][idx] if result["metadatas"] else {}
                        distance = result["distances"][0][idx] if result["distances"] else 0
                        if distance < 1.2:
                            if not should_include_memory_in_context(query_text, doc):
                                continue
                            memory_id = meta.get("memory_id")
                            emotion = meta.get("emotion", "")
                            emotion_tag = f"[{emotion}]" if emotion else ""
                            results_text.append(f"- {emotion_tag} {doc}")
                            if memory_id:
                                matched_memory_ids.add(memory_id)
        except Exception as exc:
            logger.warning(f"⚠️ 仿生记忆向量检索失败: {exc}")

    if len(results_text) < n_results:
        db_memories = get_active_memories(user_id, limit=n_results)
        for memory in db_memories:
            if memory["id"] not in matched_memory_ids and len(results_text) < n_results:
                if not should_include_memory_in_context(query_text, memory["content"]):
                    continue
                emotion_tag = f"[{memory['emotion']}]" if memory.get("emotion") else ""
                results_text.append(f"- {emotion_tag} {memory['content']}")
                matched_memory_ids.add(memory["id"])

    for memory_id in matched_memory_ids:
        boost_memory_recall(memory_id)

    if results_text:
        return "\n【一瞬间闪过的画面与印象】\n" + "\n".join(results_text) + "\n"
    return ""


def get_runtime_state_context(user_id: str) -> str:
    """获取运行时状态的格式化文本。"""
    state = get_bionic_state(user_id)
    if not state:
        return ""

    mood = state.get("current_mood", "平静")
    intensity = state.get("mood_intensity", 0.5)
    stage = state.get("relationship_stage", 1)

    parts = [
        f"你当下的状态：{describe_runtime_mood(mood, intensity)}",
        f"你对他的感觉：{describe_relationship_stage(stage)}",
    ]
    return "\n【内心的波澜与直觉】\n" + "\n".join(parts) + "\n"
