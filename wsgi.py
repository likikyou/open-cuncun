"""Gunicorn WSGI 入口。"""

import os

os.environ.setdefault("SERVICE_NAME", "feishu-companion-web")

from app.bootstrap import initialize_runtime

initialize_runtime(preload_card_images_enabled=True)

from app.main import get_app

app = get_app()
