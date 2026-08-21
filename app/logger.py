"""
统一日志模块
"""

import json
import logging
import os
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

from .config import Config


class CustomJSONFormatter(logging.Formatter):
    """
    结构化 JSON 日志格式化器
    自动提取所有 extra 字段，并格式化异常堆栈
    """

    # 忽略的标准日志字段，避免重复记录到 extra 中
    IGNORE_ATTRS = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def __init__(self, service_name: str = Config.LOG_SERVICE_NAME):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "pid": record.process,
            "thread": record.threadName,
        }

        # 1. 自动提取所有 extra 字段（非标准字段）
        for key, value in record.__dict__.items():
            if key not in self.IGNORE_ATTRS:
                # 尝试序列化，如果不可序列化则转为字符串
                try:
                    json.dumps(value)
                    log_record[key] = value
                except (TypeError, OverflowError):
                    log_record[key] = str(value)

        # 2. 处理异常堆栈
        if record.exc_info:
            log_record["exception"] = "".join(traceback.format_exception(*record.exc_info))
        elif record.exc_text:
            log_record["exception"] = record.exc_text
        elif record.stack_info:
            log_record["stack_info"] = record.stack_info

        return json.dumps(log_record, ensure_ascii=False)


def setup_logger() -> logging.Logger:
    """创建并配置全局 logger 实例，支持文件轮转"""
    _logger = logging.getLogger("feishu-companion")
    _logger.setLevel(logging.INFO)

    # 防止重复添加 handler
    if _logger.handlers:
        return _logger

    formatter = CustomJSONFormatter()

    # 控制台输出 (显式指定 stdout，避免 PM2 将 INFO 误判为 Error)
    import sys

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    _logger.addHandler(stream_handler)

    # 文件输出 (持久化 + 轮转)
    # 最大 10MB，保留 5 个备份
    try:
        os.makedirs(os.path.dirname(Config.LOG_FILE), exist_ok=True)
        file_handler = RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)
    except Exception as e:
        # 使用 print 作为最后的兜底，防止日志系统本身崩溃导致无输出
        print(f"⚠️ 无法创建日志文件: {e}")

    return _logger


# 全局唯一的 logger 实例
logger = setup_logger()
