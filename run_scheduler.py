#!/usr/bin/env python3
"""Feishu AI Companion - 独立 scheduler 入口。"""

import os

os.environ.setdefault("SERVICE_NAME", "feishu-companion-scheduler")

from app.bootstrap import initialize_runtime
from app.entrypoints.scheduler_runner import run_scheduler


def main() -> None:
    initialize_runtime(preload_card_images_enabled=False)
    run_scheduler()


if __name__ == "__main__":
    main()
