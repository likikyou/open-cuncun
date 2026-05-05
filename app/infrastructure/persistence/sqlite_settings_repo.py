"""用户设置仓储。"""

from __future__ import annotations

from typing import Any

from ...logger import logger
from ._sqlite_common import get_db_cursor


def get_user_setting(user_id: str, key: str, default: Any = None) -> Any:
    """获取用户设置。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = ?",
                (user_id, key),
            )
            row = cursor.fetchone()
            return row["setting_value"] if row else default
    except Exception as exc:
        logger.error(f"❌ 获取用户设置失败: {exc}")
        return default


def set_user_setting(user_id: str, key: str, value: Any) -> bool:
    """设置用户配置。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO user_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                (user_id, key, str(value)),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 设置用户设置失败: {exc}")
        return False
