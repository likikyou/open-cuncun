import sqlite3
from datetime import datetime
from typing import Any, Dict
import os
import time

import psutil

from .ai_engine import is_ready
from .config import Config
from .infrastructure.ai import get_active_client, get_provider_circuit_summary
from .infrastructure.feishu import feishu_client
from .logger import logger
from .observability import summarize_recent_ai_runs, summarize_recent_degradations


def _count_files(path_value: str, suffixes: tuple[str, ...]) -> int:
    if not os.path.isdir(path_value):
        return 0
    try:
        return sum(1 for name in os.listdir(path_value) if name.lower().endswith(suffixes))
    except OSError:
        return 0


def _get_runtime_asset_status() -> Dict[str, Any]:
    from .retrieval import audio_collection

    card_image_dir = os.path.join(Config.PROJECT_ROOT, "assets", "card_images")
    voice_file_count = _count_files(Config.VOICE_LIB, (".opus", ".mp3", ".wav", ".m4a"))
    card_image_file_count = _count_files(card_image_dir, (".png", ".jpg", ".jpeg", ".webp"))

    audio_collection_ok = audio_collection is not None
    audio_collection_count = None
    if audio_collection_ok:
        try:
            audio_collection_count = audio_collection.count()
        except Exception:
            audio_collection_ok = False

    return {
        "prompt_path": Config.PROMPT_PATH,
        "prompt_ok": os.path.isfile(Config.PROMPT_PATH) and os.access(Config.PROMPT_PATH, os.R_OK),
        "voice_lib": Config.VOICE_LIB,
        "voice_lib_ok": voice_file_count > 0,
        "voice_file_count": voice_file_count,
        "card_image_dir": card_image_dir,
        "card_image_ok": card_image_file_count > 0,
        "card_image_file_count": card_image_file_count,
        "memory_path": Config.MEMORY_PATH,
        "memory_path_exists": os.path.isdir(Config.MEMORY_PATH),
        "audio_collection_ok": audio_collection_ok,
        "audio_collection_count": audio_collection_count,
    }


def _redact_recent_events(summary: Dict[str, Any]) -> Dict[str, Any]:
    """保留聚合统计，移除近期事件中的私密 details。"""
    redacted = dict(summary)
    redacted_events = []
    for event in summary.get("recent", []) or []:
        redacted_events.append(
            {
                key: value
                for key, value in event.items()
                if key
                in {
                    "timestamp",
                    "component",
                    "reason",
                    "severity",
                    "stage",
                    "operation",
                    "provider",
                    "model",
                    "stream",
                }
            }
        )
    redacted["recent"] = redacted_events
    return redacted


def _redact_assets(assets: Dict[str, Any]) -> Dict[str, Any]:
    """公开 health 只暴露资产是否可用和数量，不暴露服务器路径。"""
    public_keys = {
        "prompt_ok",
        "voice_lib_ok",
        "voice_file_count",
        "card_image_ok",
        "card_image_file_count",
        "memory_path_exists",
        "audio_collection_ok",
        "audio_collection_count",
    }
    return {key: assets.get(key) for key in public_keys if key in assets}


def _redact_health_payload(health_data: Dict[str, Any]) -> Dict[str, Any]:
    """构建可公开暴露的健康检查摘要。"""
    public_payload = dict(health_data)
    observability = health_data.get("observability", {}) or {}
    public_payload["observability"] = {
        "recent_degradations": _redact_recent_events(
            observability.get("recent_degradations", {}) or {}
        ),
        "recent_ai_runs": _redact_recent_events(observability.get("recent_ai_runs", {}) or {}),
    }
    public_payload["assets"] = _redact_assets(health_data.get("assets", {}) or {})
    public_payload["privacy"] = {
        "redacted": True,
        "detail_auth": "Set HEALTH_AUTH_TOKEN and send Authorization: Bearer <token> for full payload.",
    }
    return public_payload


def check_health(*, include_private: bool = True) -> Dict[str, Any]:
    """
    执行全面的系统健康检查
    :return: 包含组件状态、系统资源（内存/磁盘）的健康报告
    """
    try:
        # 获取内存使用情况
        mem = psutil.virtual_memory()
        mem_usage = mem.percent

        # 获取磁盘使用情况
        disk = psutil.disk_usage("/")
        disk_usage = disk.percent

        # AI 引擎状态（通过 is_ready 解耦，不直接导入模块级变量）
        ai_status = is_ready()
        client, model, provider_name = get_active_client(reserve_probe=False)
        circuit_summary = get_provider_circuit_summary()
        assets = _get_runtime_asset_status()
        degradation_summary = summarize_recent_degradations(window_seconds=300)
        ai_run_summary = summarize_recent_ai_runs(window_seconds=300)

        # 飞书 Token 状态（仅检查缓存，不触发 HTTP 请求）
        token_cache = feishu_client._token_cache
        feishu_ok = (
            token_cache["token"] is not None and time.time() < token_cache["expires_at"] - 300
        )

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "ai_engine": ai_status["ai_engine"],
                "voice_db": ai_status["voice_db"],
                "feishu_api": feishu_ok,
            },
            "runtime": {
                "resolved_provider": provider_name if client else None,
                "resolved_model": model if client else None,
            },
            "ai_circuit": circuit_summary,
            "observability": {
                "recent_degradations": degradation_summary,
                "recent_ai_runs": ai_run_summary,
            },
            "assets": assets,
            "system": {"memory_usage": f"{mem_usage}%", "disk_usage": f"{disk_usage}%"},
        }
        recent_warning_count = degradation_summary["by_severity"].get("warning", 0)
        recent_error_count = degradation_summary["by_severity"].get("error", 0)

        # AI / 提示词属于硬依赖；语音、卡片、飞书 token cache 更适合作为 degraded 信号。
        log_message = "执行健康检查: 正常"
        log_method = logger.info
        if not ai_status["ai_engine"] or not assets["prompt_ok"]:
            health_data["status"] = "unhealthy"
            log_message = "系统健康检查发现严重异常"
            log_method = logger.warning
        elif (
            not health_data["components"]["feishu_api"]
            or not health_data["components"]["voice_db"]
            or not assets["voice_lib_ok"]
            or not assets["card_image_ok"]
            or not assets["memory_path_exists"]
            or not assets["audio_collection_ok"]
            or recent_error_count > 0
            or recent_warning_count >= 3
        ):
            health_data["status"] = "degraded"
            log_message = "系统健康检查发现降级信号"
            log_method = logger.warning

        response_data = health_data if include_private else _redact_health_payload(health_data)
        log_method(log_message, extra={"health_data": response_data})
        return response_data
    except Exception as e:
        logger.error(f"健康检查执行失败: {e}")
        return {"status": "error", "message": str(e)}


def backup_database_task() -> None:
    """
    数据库自动备份
    使用 SQLite VACUUM INTO 进行原子备份，避免并发写入时的不一致性。
    自动清理 7 天前的过期备份。
    """
    try:
        os.makedirs(Config.BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        backup_filename = f"backup_{timestamp}_companion_memory.db"
        backup_path = os.path.join(Config.BACKUP_DIR, backup_filename)

        # 使用 VACUUM INTO 进行原子备份（不受 WAL 并发写入影响）
        conn = sqlite3.connect(Config.DB_PATH, timeout=10)
        try:
            conn.execute(f"VACUUM INTO '{backup_path}'")
            logger.info(f"💾 数据库原子备份成功: {backup_filename}")
        finally:
            conn.close()

        # 清理旧备份 (保留 7 天)
        _clean_old_backups(retention_days=7)

    except Exception as e:
        logger.error(f"❌ 数据库备份失败: {e}", exc_info=True)
        try:
            from .application.post_reply_jobs import send_error_alert

            send_error_alert(f"Scheduler job failed: backup_database\n{e.__class__.__name__}: {e}")
        except Exception as alert_exc:
            logger.error(f"❌ 数据库备份告警发送失败: {alert_exc}", exc_info=True)


def _clean_old_backups(retention_days: int = 7) -> None:
    """清理指定天数之前的备份文件"""
    retention_time = time.time() - (retention_days * 86400)
    removed_count = 0

    for f in os.listdir(Config.BACKUP_DIR):
        fp = os.path.join(Config.BACKUP_DIR, f)
        # 只清理 backup_ 开头的文件，防止误删
        if os.path.isfile(fp) and f.startswith("backup_"):
            if os.path.getmtime(fp) < retention_time:
                try:
                    os.remove(fp)
                    removed_count += 1
                    logger.info(f"🧹 清理过期备份: {f}")
                except Exception as e:
                    logger.warning(f"无法删除过期备份 {f}: {e}")

    if removed_count > 0:
        logger.info(f"✅ 已清理 {removed_count} 个过期备份文件")
