"""SQLite 共享连接与建表逻辑。"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from typing import Generator

from ...config import Config
from ...logger import logger


def get_db_connection() -> sqlite3.Connection:
    """创建数据库连接，启用 WAL 模式并设置超时。"""
    conn = sqlite3.connect(Config.DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextlib.contextmanager
def get_db_cursor(commit: bool = False) -> Generator[sqlite3.Cursor, None, None]:
    """数据库游标上下文管理器。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        yield cursor
        if commit:
            conn.commit()
    except Exception as exc:
        if conn and commit:
            conn.rollback()
        raise exc
    finally:
        if conn:
            conn.close()


def init_db() -> None:
    """初始化数据库，自动创建表结构和索引。"""
    try:
        os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)

        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT DEFAULT '',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    role TEXT CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    tokens_used INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute("PRAGMA table_info(chat_history)")
            chat_history_columns = {row["name"] for row in cursor.fetchall()}
            if "conversation_id" not in chat_history_columns:
                cursor.execute("ALTER TABLE chat_history ADD COLUMN conversation_id TEXT DEFAULT ''")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    mode TEXT DEFAULT 'normal',
                    summary TEXT DEFAULT '',
                    archived_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                UPDATE chat_history
                SET conversation_id = 'default:' || user_id
                WHERE conversation_id IS NULL OR conversation_id = ''
                """
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO conversations (id, user_id, title, mode)
                SELECT DISTINCT 'default:' || user_id, user_id, '日常聊天', 'normal'
                FROM chat_history
                WHERE user_id IS NOT NULL AND user_id != ''
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id TEXT NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT NOT NULL,
                    PRIMARY KEY (user_id, setting_key)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bionic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    memory_type TEXT CHECK(memory_type IN ('reflection', 'consolidation')) DEFAULT 'reflection',
                    content TEXT NOT NULL,
                    theme TEXT DEFAULT '',
                    emotion TEXT DEFAULT '',
                    importance REAL DEFAULT 0.5,
                    strength REAL DEFAULT 1.0,
                    recall_count INTEGER DEFAULT 0,
                    last_recalled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT CHECK(status IN ('active', 'consolidated', 'forgotten')) DEFAULT 'active'
                )
                """
            )

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON chat_history(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON chat_history(timestamp)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_user_conversation ON chat_history(user_id, conversation_id, id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, archived_at, updated_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bionic_user_status ON bionic_memories(user_id, status)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bionic_theme ON bionic_memories(theme)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bionic_strength ON bionic_memories(strength)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bionic_state (
                    user_id TEXT PRIMARY KEY,
                    current_mood TEXT DEFAULT '平静',
                    mood_intensity REAL DEFAULT 0.5,
                    relationship_stage INTEGER DEFAULT 1,
                    last_mood_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_interaction_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_reflections INTEGER DEFAULT 0
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS presence_snapshot (
                    user_id TEXT PRIMARY KEY,
                    snapshot_version INTEGER DEFAULT 1,
                    state_source TEXT DEFAULT 'routine',
                    routine_slot TEXT DEFAULT '',
                    routine_label TEXT DEFAULT '',
                    weather_summary TEXT DEFAULT '',
                    accident_code TEXT DEFAULT '',
                    accident_text TEXT DEFAULT '',
                    mood TEXT DEFAULT '平静',
                    mood_intensity REAL DEFAULT 0.5,
                    recent_chat_hint TEXT DEFAULT '',
                    memory_hint TEXT DEFAULT '',
                    observation_text TEXT DEFAULT '',
                    media_type TEXT DEFAULT 'text',
                    media_status TEXT DEFAULT 'none',
                    media_prompt TEXT DEFAULT '',
                    media_key TEXT DEFAULT '',
                    generated_by TEXT DEFAULT 'ai',
                    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_reason TEXT DEFAULT ''
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS presence_runtime_state (
                    user_id TEXT PRIMARY KEY,
                    state_code TEXT DEFAULT '',
                    state_label TEXT DEFAULT '',
                    state_priority INTEGER DEFAULT 0,
                    scene_hint TEXT DEFAULT '',
                    state_token TEXT DEFAULT '',
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profile_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    vector_id TEXT UNIQUE,
                    fact TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    stability TEXT CHECK(stability IN ('high', 'medium', 'low')) DEFAULT 'medium',
                    confidence REAL DEFAULT 0.7,
                    source TEXT DEFAULT '',
                    source_turn_ids TEXT DEFAULT '',
                    status TEXT CHECK(status IN ('active', 'superseded')) DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, fact)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    vector_id TEXT UNIQUE,
                    insight TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    stability TEXT CHECK(stability IN ('high', 'medium', 'low')) DEFAULT 'medium',
                    confidence REAL DEFAULT 0.7,
                    source TEXT DEFAULT '',
                    source_turn_ids TEXT DEFAULT '',
                    status TEXT CHECK(status IN ('active', 'superseded')) DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, insight)
                )
                """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_profile_user_status ON user_profile_facts(user_id, status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_profile_category ON user_profile_facts(category)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationship_user_status ON relationship_insights(user_id, status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationship_category ON relationship_insights(category)"
            )

        logger.info(f"✅ 记忆库已就绪 (WAL模式): {Config.DB_PATH}")
    except Exception as exc:
        import logging

        err_logger = logging.getLogger("feishu-companion")
        err_logger.error(f"❌ 数据库初始化失败: {exc}")
