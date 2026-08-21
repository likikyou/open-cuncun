"""Helpers for privacy-safe structured log metadata."""

from __future__ import annotations

import hashlib
from typing import Any


def sensitive_text_fields(
    field_name: str,
    value: Any,
    *,
    include_content: bool = False,
    preview_limit: int = 120,
) -> dict[str, Any]:
    """Describe sensitive text without logging its content by default."""
    text = "" if value is None else str(value)
    fields: dict[str, Any] = {
        f"{field_name}_chars": len(text),
    }
    if text:
        fields[f"{field_name}_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    if include_content and text:
        fields[f"{field_name}_preview"] = text[: max(1, preview_limit)]
    return fields
