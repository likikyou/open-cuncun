#!/bin/bash
# Feishu AI Companion 本地验证入口
# 运行方式: bash scripts/verify.sh
set -euo pipefail

cd "$(dirname "$0")/.."
python3 scripts/verify.py
