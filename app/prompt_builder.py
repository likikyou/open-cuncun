"""
提示词构建模块
负责动态加载和热更新系统提示词
"""

import os
import re
from datetime import datetime, timedelta, timezone
from .config import Config
from .logger import logger

_prompt_cache = None
_prompt_mtime = 0.0
_AFFECTIONATE_MISS_YOU_RE = re.compile(
    r"(想死你(?:了|啦)?|想你想死(?:了|啦)?|想你想到疯(?:了|啦)?|想你想到爆)"
)
_REAL_RISK_MARKERS = (
    "不想活",
    "活不下去",
    "想自杀",
    "想去死",
    "轻生",
    "自残",
    "结束生命",
)


def _needs_affectionate_miss_you_hint(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    if any(marker in text for marker in _REAL_RISK_MARKERS):
        return False
    return bool(_AFFECTIONATE_MISS_YOU_RE.search(text))


def build_prompt(user_text: str) -> str:
    """构建带实时时间戳的提示词（基于文件 mtime 缓存，修改文件后自动重新加载，无需重启服务）"""
    global _prompt_cache, _prompt_mtime
    try:
        current_mtime = os.path.getmtime(Config.PROMPT_PATH)
        if _prompt_cache is None or current_mtime != _prompt_mtime:
            with open(Config.PROMPT_PATH, "r", encoding="utf-8") as f:
                _prompt_cache = f.read().strip()
            _prompt_mtime = current_mtime
            logger.info("🔄 提示词模板已重新加载")
    except Exception as error:
        logger.warning(
            "读取提示词失败，使用缓存或公共默认提示词",
            extra={"error_type": type(error).__name__},
        )
        if _prompt_cache is None:
            _prompt_cache = "I am your AI companion assistant."

    # 强制获取北京时间（解决部分服务器系统时间未同步的问题）
    beijing_now = datetime.now(timezone(timedelta(hours=8)))
    now_str = beijing_now.strftime("%Y-%m-%d %H:%M:%S")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][beijing_now.weekday()]

    # 【核心身份认同层】
    # 这一层通过最高权重确保角色在感知当前时间的同时，强化角色的自我认知。
    instruction = (
        f"【当前北京时间：{now_str} {weekday}】\n"
        "【内心的声音：当下的谈话应基于你的角色设定。"
        "你可以根据聊天的氛围自由调整表达的细腻程度。】"
    )
    if _needs_affectionate_miss_you_hint(user_text):
        instruction += (
            '\n【语义提醒：这句里的"想死你了/想你想死了"属于中文口语，表达的是强烈思念、'
            "通常不是字面上的求死或负面威胁。请结合当前角色设定和对话关系回应，"
            "不要自行追加未配置的关系或语气设定。】"
        )
    return f"{instruction}\n\n{_prompt_cache}"
