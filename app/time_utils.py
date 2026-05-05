"""
时间辅助工具

约定：
- SQLite 中的 CURRENT_TIMESTAMP 视为 naive UTC 字符串
- 本地业务时间统一从 UTC 显式转换，避免混用
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

SQLITE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def local_tz():
    """返回当前进程可见的本地时区。"""
    return datetime.now().astimezone().tzinfo or timezone.utc


def utc_now_naive() -> datetime:
    """返回与 SQLite CURRENT_TIMESTAMP 语义一致的 naive UTC 时间。"""
    return datetime.utcnow()


def local_now_naive() -> datetime:
    """返回本地时区的 naive 当前时间，用于本地业务逻辑。"""
    return datetime.now(local_tz()).replace(tzinfo=None)


def parse_sqlite_utc(timestamp: str) -> datetime:
    """解析 SQLite CURRENT_TIMESTAMP 风格的 naive UTC 字符串。"""
    return datetime.strptime(timestamp, SQLITE_TIMESTAMP_FORMAT)


def sqlite_utc_to_local_naive(timestamp: str) -> datetime:
    """将 SQLite 的 naive UTC 字符串转换为本地时区的 naive datetime。"""
    utc_dt = parse_sqlite_utc(timestamp).replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(local_tz()).replace(tzinfo=None)


def get_local_day_utc_bounds(
    now_local: Optional[datetime] = None,
) -> Tuple[str, str]:
    """
    计算“本地今天”在 UTC 存储中的左右边界，返回 SQLite 可直接比较的字符串。
    结果可用于：timestamp >= start_utc AND timestamp < end_utc
    """
    tz = local_tz()
    current_local = now_local or datetime.now(tz)
    if current_local.tzinfo is None:
        current_local = current_local.replace(tzinfo=tz)
    else:
        current_local = current_local.astimezone(tz)

    local_day_start = current_local.replace(hour=0, minute=0, second=0, microsecond=0)
    next_local_day_start = local_day_start + timedelta(days=1)

    start_utc = local_day_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = next_local_day_start.astimezone(timezone.utc).replace(tzinfo=None)
    return (
        start_utc.strftime(SQLITE_TIMESTAMP_FORMAT),
        end_utc.strftime(SQLITE_TIMESTAMP_FORMAT),
    )


def get_relative_local_day_utc_bounds(
    day_offset: int,
    now_local: Optional[datetime] = None,
) -> Tuple[str, str]:
    """
    计算“本地相对日期”在 UTC 存储中的左右边界。
    day_offset=0 表示今天，1 表示昨天，2 表示前天。
    """
    normalized_offset = max(0, int(day_offset))
    tz = local_tz()
    current_local = now_local or datetime.now(tz)
    if current_local.tzinfo is None:
        current_local = current_local.replace(tzinfo=tz)
    else:
        current_local = current_local.astimezone(tz)

    local_day_start = current_local.replace(hour=0, minute=0, second=0, microsecond=0)
    target_local_day_start = local_day_start - timedelta(days=normalized_offset)
    next_local_day_start = target_local_day_start + timedelta(days=1)

    start_utc = target_local_day_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = next_local_day_start.astimezone(timezone.utc).replace(tzinfo=None)
    return (
        start_utc.strftime(SQLITE_TIMESTAMP_FORMAT),
        end_utc.strftime(SQLITE_TIMESTAMP_FORMAT),
    )
