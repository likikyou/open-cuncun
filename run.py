#!/usr/bin/env python3
"""
Feishu AI Companion - 开发模式启动入口
用法: python run.py
"""
import os

os.environ.setdefault("SERVICE_NAME", "feishu-companion-dev")

from app.main import start_app

if __name__ == "__main__":
    start_app()
