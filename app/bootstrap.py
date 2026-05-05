"""应用启动引导。"""

from __future__ import annotations

import logging as py_logging
import os
import threading

from .config import Config
from .entrypoints.scheduler_runner import run_scheduler
from .infrastructure.persistence._sqlite_common import init_db
from .logger import logger
from .presentation.cards.assets import preload_card_images

VERSION = "5.7.1"
_runtime_lock = threading.Lock()
_runtime_initialized = False
_card_images_preloaded = False
_scheduler_thread_started = False


def log_runtime_asset_status(*, config=Config, logger_obj=logger) -> None:
    """启动时输出关键运行时资产状态，减少路径漂移导致的隐性故障。"""
    from .retrieval import audio_collection

    card_image_dir = os.path.join(config.PROJECT_ROOT, "assets", "card_images")
    prompt_ok = os.path.isfile(config.PROMPT_PATH) and os.access(config.PROMPT_PATH, os.R_OK)
    voice_file_count = 0
    if os.path.isdir(config.VOICE_LIB):
        try:
            voice_file_count = sum(
                1
                for name in os.listdir(config.VOICE_LIB)
                if name.lower().endswith((".opus", ".mp3", ".wav", ".m4a"))
            )
        except OSError:
            voice_file_count = 0
    voice_lib_ok = voice_file_count > 0

    card_image_file_count = 0
    if os.path.isdir(card_image_dir):
        try:
            card_image_file_count = sum(
                1
                for name in os.listdir(card_image_dir)
                if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            )
        except OSError:
            card_image_file_count = 0
    card_image_ok = card_image_file_count > 0

    audio_collection_ok = audio_collection is not None
    audio_collection_count = None
    if audio_collection_ok:
        try:
            audio_collection_count = audio_collection.count()
        except Exception as exc:
            audio_collection_ok = False
            logger_obj.warning(f"⚠️ 启动时读取 companion_audio 数量失败: {exc}")

    logger_obj.info(
        "🧭 运行时资产检查",
        extra={
            "prompt_path": config.PROMPT_PATH,
            "prompt_ok": prompt_ok,
            "voice_lib": config.VOICE_LIB,
            "voice_lib_ok": voice_lib_ok,
            "voice_file_count": voice_file_count,
            "card_image_dir": card_image_dir,
            "card_image_ok": card_image_ok,
            "card_image_file_count": card_image_file_count,
            "memory_path": config.MEMORY_PATH,
            "audio_collection_ok": audio_collection_ok,
            "audio_collection_count": audio_collection_count,
        },
    )

    if not prompt_ok:
        logger_obj.warning(f"⚠️ 提示词模板不可读: {config.PROMPT_PATH}")
    if not voice_lib_ok:
        logger_obj.warning(f"⚠️ 语音目录不可用或为空: {config.VOICE_LIB}")
    if not card_image_ok:
        logger_obj.warning(f"⚠️ 卡片主图目录不可用或为空: {card_image_dir}")
    if not audio_collection_ok:
        logger_obj.warning(f"⚠️ companion_audio 集合不可用，当前 MEMORY_PATH={config.MEMORY_PATH}")


def initialize_runtime(
    *,
    config=Config,
    logger_obj=logger,
    init_db_fn=init_db,
    preload_card_images_fn=preload_card_images,
    preload_card_images_enabled: bool = True,
) -> None:
    """执行当前进程的运行时初始化。"""
    global _runtime_initialized, _card_images_preloaded

    with _runtime_lock:
        if not _runtime_initialized:
            config.validate()
            init_db_fn()
            py_logging.getLogger("werkzeug").setLevel(py_logging.ERROR)
            _runtime_initialized = True

        if preload_card_images_enabled and not _card_images_preloaded:
            preload_card_images_fn()
            _card_images_preloaded = True

    log_runtime_asset_status(config=config, logger_obj=logger_obj)


def start_scheduler_thread(*, run_scheduler_fn=run_scheduler, logger_obj=logger) -> None:
    """仅供开发模式使用：在 Web 进程内启动 scheduler 线程。"""
    global _scheduler_thread_started

    with _runtime_lock:
        if _scheduler_thread_started:
            return
        threading.Thread(target=run_scheduler_fn, daemon=True, name="feishu-companion-scheduler").start()
        _scheduler_thread_started = True

    logger_obj.info("🧵 开发模式已启动进程内 scheduler 线程")


def start_app(
    app_or_factory,
    *,
    config=Config,
    logger_obj=logger,
    init_db_fn=init_db,
    preload_card_images_fn=preload_card_images,
    run_scheduler_fn=run_scheduler,
    version: str = VERSION,
) -> None:
    """开发模式入口：初始化、创建 app、启动进程内 scheduler，并运行 Flask 内建服务器。"""
    initialize_runtime(
        config=config,
        logger_obj=logger_obj,
        init_db_fn=init_db_fn,
        preload_card_images_fn=preload_card_images_fn,
        preload_card_images_enabled=True,
    )
    start_scheduler_thread(run_scheduler_fn=run_scheduler_fn, logger_obj=logger_obj)
    app = app_or_factory if hasattr(app_or_factory, "run") else app_or_factory()

    host = config.SERVER_HOST
    port = config.SERVER_PORT
    debug_mode = config.DEBUG_MODE
    logger_obj.info(f"🚀 Feishu AI Companion V{version} 启动成功: {host}:{port} debug={debug_mode}")
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False, threaded=True)
