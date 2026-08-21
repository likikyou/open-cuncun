"""回复文本归一化。"""

from __future__ import annotations

import re

_LINE_BREAK_RE = re.compile(r"[ \t]*\n+[ \t]*")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([，。！？；：、）】》」』])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([（【《「『])\s+")
_SPACE_BEFORE_OPEN_RE = re.compile(r"([，。！？；：、…])\s+([（【《「『])")


def normalize_reply_text(text: str) -> str:
    """把模型常见的多段短句压成单段，保留括号动作的画面感。"""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    normalized = _LINE_BREAK_RE.sub(" ", normalized)
    normalized = _MULTI_SPACE_RE.sub(" ", normalized)
    normalized = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", normalized)
    normalized = _SPACE_AFTER_OPEN_RE.sub(r"\1", normalized)
    normalized = _SPACE_BEFORE_OPEN_RE.sub(r"\1\2", normalized)
    return normalized.strip()
