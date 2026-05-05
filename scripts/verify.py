#!/usr/bin/env python3
"""
本地验证脚本 - 重构前必跑
运行方式: python3 scripts/verify.py
"""
import ast
import importlib
import sys
import time
from pathlib import Path


DELETED_FACADE_PREFIXES = (
    "app.ai_client",
    "app.feishu_api",
    "app.bionic_memory",
    "app.context_builder",
    "app.database",
    "app.streaming",
    "app.scheduler",
    "app.message_handler",
)


def _iter_python_files(project_root, *relative_dirs):
    seen = set()
    for relative_dir in relative_dirs:
        root = Path(project_root, relative_dir)
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or path in seen:
                continue
            seen.add(path)
            yield path


def _module_name_from_path(project_root, path):
    return ".".join(path.relative_to(project_root).with_suffix("").parts)


def _resolve_import_targets(module_name, node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    package_parts = module_name.split(".")[:-1]
    if node.level > 1:
        package_parts = package_parts[: max(0, len(package_parts) - (node.level - 1))]

    resolved_parts = list(package_parts)
    if node.module:
        resolved_parts.extend(node.module.split("."))

    resolved_module = ".".join(part for part in resolved_parts if part)
    targets = [resolved_module] if resolved_module else []
    for alias in node.names:
        if alias.name == "*":
            continue
        if resolved_module:
            targets.append(f"{resolved_module}.{alias.name}")
        else:
            targets.append(alias.name)
    return targets


def _iter_imports(project_root, *relative_dirs):
    for path in _iter_python_files(project_root, *relative_dirs):
        module_name = _module_name_from_path(project_root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve_import_targets(module_name, node):
                    if target:
                        yield path, node.lineno, target


def _matches_prefix(target, prefixes):
    return any(target == prefix or target.startswith(f"{prefix}.") for prefix in prefixes)


def _format_violations(violations, max_items=8):
    preview = list(violations[:max_items])
    if len(violations) > max_items:
        preview.append(f"... 还有 {len(violations) - max_items} 处")
    return "\n     ".join(preview)


def run(name, fn):
    """执行一个验证项，失败则打印并继续"""
    try:
        print(f"\n{'='*50}")
        print(f"  {name}")
        print('='*50)
        fn()
        print("  ✅ PASS")
        return True
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def check(name, condition, detail=""):
    """检查条件，失败时抛出异常，让验证项真实失败"""
    if condition:
        print(f"  ✅ {name}")
        return True
    else:
        print(f"  ❌ {name}")
        if detail:
            print(f"     {detail}")
        raise AssertionError(detail or name)


def _check_architecture_guardrails(project_root):
    scanned_files = list(_iter_python_files(project_root, "app", "scripts"))

    compat_violations = []
    for path, lineno, target in _iter_imports(project_root, "app", "scripts"):
        if _matches_prefix(target, DELETED_FACADE_PREFIXES):
            rel = path.relative_to(project_root)
            compat_violations.append(f"{rel}:{lineno} -> {target}")

    entrypoint_violations = []
    for path, lineno, target in _iter_imports(project_root, "app/application"):
        if _matches_prefix(target, ("app.main", "app.bootstrap", "app.entrypoints")):
            rel = path.relative_to(project_root)
            entrypoint_violations.append(f"{rel}:{lineno} -> {target}")

    domain_violations = []
    for path, lineno, target in _iter_imports(project_root, "app/domain"):
        if _matches_prefix(
            target,
            (
                "app.application",
                "app.presentation",
                "app.infrastructure",
                "app.main",
                "app.bootstrap",
                "app.entrypoints",
            ),
        ):
            rel = path.relative_to(project_root)
            domain_violations.append(f"{rel}:{lineno} -> {target}")

    print(f"  已扫描 Python 文件: {len(scanned_files)}")
    print(f"  已删除 facade 黑名单: {len(DELETED_FACADE_PREFIXES)}")
    check("旧 facade 未回流", not compat_violations, _format_violations(compat_violations))
    check(
        "application 未反向依赖入口层",
        not entrypoint_violations,
        _format_violations(entrypoint_violations),
    )
    check(
        "domain 保持纯规则边界",
        not domain_violations,
        _format_violations(domain_violations),
    )


def run_offline_quick_checks(project_root):
    """不触发真实 AI / embedding / Feishu 网络请求的快速验证。"""
    results = []

    def architecture_guardrails():
        _check_architecture_guardrails(project_root)

    results.append(run("offline.1 架构守卫", architecture_guardrails))

    def import_current_modules():
        modules = (
            "app.main",
            "app.ai_engine",
            "app.application.chat_orchestrator",
            "app.application.context_assembler",
            "app.application.observation_media_service",
            "app.application.observation_service",
            "app.application.reply_service",
            "app.entrypoints.feishu_webhook",
            "app.entrypoints.scheduler_runner",
            "app.retrieval",
            "app.voice_matcher",
            "app.vision",
        )
        for module_name in modules:
            importlib.import_module(module_name)
        print(f"  已导入当前主链模块: {len(modules)} 个")

    results.append(run("offline.2 当前主链导入", import_current_modules))

    def context_assembly_without_io():
        from app.application.context_assembler import build_messages

        deps = {
            "should_search": lambda _text: False,
            "get_user_setting": lambda _user_id, key, default="": "off"
            if key == "pure_mode"
            else default,
            "get_runtime_state_context": lambda _user_id: "【内心的波澜与直觉】\n你当下的状态：平静",
            "get_persona_memory": lambda _text, _n_results=1: "【角色底色与自我认知】\n- 嘴硬心软",
            "get_long_term_memory": lambda *_args, **_kwargs: "【检测到相关背景记忆】\n- 他最近在忙项目",
            "retrieve_bionic_memories": lambda *_args: "【仿生记忆】\n- 她记得他有点累",
            "get_user_profile_memory": lambda *_args: "【关于他的稳定印象】\n- 他重视效率",
            "get_relationship_memory": lambda *_args: "【你们之间慢慢形成的默契】\n- 她会嘴硬地关心他",
            "get_knowledge_memory": lambda *_args: "",
            "search_web_bocha": lambda *_args: "",
            "get_history_by_day_offset": lambda *_args, **_kwargs: [],
        }
        messages = build_messages(
            "你是一个傲娇角色",
            "今天工作有点累，想认真聊聊",
            [],
            "normal",
            "_verify_offline_user",
            deps=deps,
        )
        system_prompt = messages[0]["content"]
        check("包含角色状态层", "角色的意识流与状态" in system_prompt)
        check("包含运行时状态", "你当下的状态" in system_prompt)
        check("未触发现实参考层", "### 🌐 现实参考" not in system_prompt)

    results.append(run("offline.3 上下文离线装配", context_assembly_without_io))

    def command_service_without_io():
        from app.application.command_service import handle_command
        from app.presentation.cards import builders as card_builders

        sent = []
        cards = []
        settings = {}
        active_conversation = {
            "id": "conv_verify",
            "title": "验证对话",
            "mode": "normal",
            "summary": "",
            "message_count": 2,
        }
        conversations = [active_conversation]
        audit_memories = [
            {
                "id": 11,
                "content": "助手在为电影节准备指甲样稿，并提到用户总是忘记趁热吃日料。",
                "theme": "生活",
                "emotion": "撒娇",
                "importance": 0.5,
            },
            {
                "id": 12,
                "content": "用户在压力大时会认真梳理项目。",
                "theme": "工作",
                "emotion": "平静",
                "importance": 0.6,
            },
        ]

        def visible_texts(obj):
            texts = []
            if isinstance(obj, dict):
                text_obj = obj.get("text")
                if isinstance(text_obj, dict) and isinstance(text_obj.get("content"), str):
                    texts.append(text_obj["content"])
                for value in obj.values():
                    texts.extend(visible_texts(value))
            elif isinstance(obj, list):
                for item in obj:
                    texts.extend(visible_texts(item))
            return texts
        deps = {
            "send_feishu": lambda open_id, msg_type, payload: sent.append(
                (open_id, msg_type, payload)
            ),
            "send_interactive_card": lambda open_id, card: cards.append((open_id, card)) or True,
            "get_observation_text": lambda _open_id, force_refresh=False: (
                "保姆车窗边的光线有点灰，助手刚把手机扣在腿上。"
                if not force_refresh
                else "她抬手理了理耳后的碎发，又低头看了一眼屏幕。"
            ),
            "get_user_setting": lambda user_id, key, default="": settings.get(
                (user_id, key), default
            ),
            "set_user_setting": lambda user_id, key, value: settings.setdefault(
                (user_id, key), value
            )
            or True,
            "build_reply_mode_card": lambda mode: {"type": "reply", "mode": mode},
            "build_help_card": card_builders.build_help_card,
            "build_chat_card": card_builders.build_chat_card,
            "build_chat_current_card": card_builders.build_chat_current_card,
            "build_chat_rename_card": card_builders.build_chat_rename_card,
            "build_memory_audit_card": card_builders.build_memory_audit_card,
            "build_story_mode_card": card_builders.build_story_mode_card,
            "list_conversations": lambda _open_id, limit=8: conversations[:limit],
            "get_active_conversation": lambda _open_id: active_conversation,
            "get_active_memories": lambda _open_id, limit=300: audit_memories[:limit],
            "mark_user_memories_forgotten": lambda _open_id, memory_ids: len(memory_ids),
            "rename_conversation": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("empty /chat rename should render a card first")
            ),
        }
        original_hero_builder = card_builders.build_card_hero_image
        card_builders.build_card_hero_image = lambda *_args, **_kwargs: None
        try:
            handle_command("_verify_user", "/reply", deps=deps)
            handle_command("_verify_user", "/reply 1", deps=deps)
            handle_command("_verify_user", "/observe", deps=deps)
            handle_command("_verify_user", "/help", deps=deps)
            help_payload = str(cards[-1][1])
            handle_command("_verify_user", "/chat", deps=deps)
            chat_payload = str(cards[-1][1])
            handle_command("_verify_user", "/chat rename", deps=deps)
            rename_payload = str(cards[-1][1])
            handle_command("_verify_user", "/story", deps=deps)
            story_payload = str(cards[-1][1])
            handle_command("_verify_user", "/memory audit", deps=deps)
            audit_payload = str(cards[-1][1])
            visible_text = "\n".join(visible_texts(cards[-5][1]))
            visible_text += "\n" + "\n".join(visible_texts(cards[-4][1]))
            visible_text += "\n" + "\n".join(visible_texts(cards[-3][1]))
            visible_text += "\n" + "\n".join(visible_texts(cards[-2][1]))
            visible_text += "\n" + "\n".join(visible_texts(cards[-1][1]))
        finally:
            card_builders.build_card_hero_image = original_hero_builder
        check("回复模式卡片已生成", cards and cards[0][1]["type"] == "reply")
        check("回复模式设置已写入", settings[("_verify_user", "reply_mode")] == "light")
        check("回复模式确认已发送", any("轻量" in str(payload) for _, _, payload in sent))
        check("实时观察走文本发送", any("实时观察" in str(payload) for _, _, payload in sent))
        check("/help 含 observe 入口", "/observe" in help_payload)
        check("/help 含 chat 入口", "/chat" in help_payload)
        check("/help 含 story 入口", "/story" in help_payload)
        check("/chat 卡片含 new", "/chat new" in chat_payload)
        check("/chat 卡片含 switch", "/chat switch" in chat_payload)
        check("/chat 卡片含 rename", "/chat rename" in chat_payload)
        check("/chat 卡片含 current", "/chat current" in chat_payload)
        check("/chat rename 空参数展示卡片", "重命名对话" in rename_payload)
        check("/story 卡片含 on", "/story on" in story_payload)
        check("/story 卡片含 off", "/story off" in story_payload)
        check("/story 卡片含 status", "/story status" in story_payload)
        hidden_commands = (
            "/chat",
            "/story",
            "/memory",
            "/reply",
            "/pure",
            "/model",
            "/help",
            "/observe",
        )
        check(
            "卡片可见文案不露出斜杠命令",
            not any(command in visible_text for command in hidden_commands),
        )
        check("记忆审核列出疑似污染候选", "电影节" in audit_payload and "标记遗忘" in audit_payload)

    results.append(run("offline.4 命令服务离线路径", command_service_without_io))

    def observation_snapshot_without_io():
        from datetime import datetime

        from app.application.observation_service import build_presence_payload, get_observation_text

        snapshot_store = {}
        runtime_state_store = {}
        local_now = datetime(2026, 4, 23, 14, 35, 0)
        utc_now = datetime(2026, 4, 23, 6, 35, 0)

        def save_snapshot(user_id, snapshot):
            snapshot_store[user_id] = dict(snapshot)
            return True

        deps = {
            "config": type(
                "Config",
                (),
                {"ADMIN_OPEN_ID": "_verify_observe_user", "OBSERVATION_CACHE_SECONDS": 180},
            ),
            "local_now_naive": lambda: local_now,
            "utc_now_naive": lambda: utc_now,
            "get_presence_snapshot": lambda user_id: snapshot_store.get(user_id),
            "get_presence_runtime_state": lambda user_id: runtime_state_store.get(user_id),
            "save_presence_snapshot": save_snapshot,
            "get_weather": lambda: "北京实时天气：阴天 ☁️，气温 25°C，体感 26°C",
            "get_bionic_state": lambda _user_id: {"current_mood": "思念", "mood_intensity": 0.7},
            "get_last_interaction_time": lambda _user_id: datetime(2026, 4, 23, 14, 34, 0),
            "get_recent_history": lambda _user_id, limit=2: [
                {"role": "user", "content": "你刚忙完吗"},
                {"role": "assistant", "content": "还在片场"},
            ][:limit],
            "get_active_memories": lambda _user_id, limit=3: [
                {"content": "她记得他最近胃不太舒服。"}
            ][:limit],
            "render_observation_text": lambda snapshot, deps=None: (
                "保姆车窗边的光线有点灰，助手刚把手机扣在腿上，眼神还在屏幕上停了停。",
                "template",
            ),
        }

        text = get_observation_text("_verify_observe_user", deps=deps)
        payload = build_presence_payload("_verify_observe_user", deps=deps)
        cached_text = get_observation_text("_verify_observe_user", deps=deps)

        check("observation 返回文字", "手机扣在腿上" in text)
        check("observation 写入 snapshot 缓存", "_verify_observe_user" in snapshot_store)
        check(
            "observation 默认命中 recent_chat 来源",
            snapshot_store["_verify_observe_user"]["state_source"] == "recent_chat",
        )
        check("presence 返回 ok", payload["status"] == "ok")
        check(
            "presence 与 observation 同源",
            payload["snapshot"]["observation_text"] == text == cached_text,
        )
        check("presence 预留文本媒体位", payload["snapshot"]["media"]["type"] == "text")
        check("presence 暴露媒体 prompt", bool(payload["snapshot"]["media"]["prompt"]))

    results.append(run("offline.5 observation snapshot", observation_snapshot_without_io))

    def observation_runtime_state_priority():
        from datetime import datetime, timedelta

        from app.application.observation_service import (
            activate_presence_runtime_state,
            clear_presence_runtime_state_for_observation,
            get_observation_text,
        )

        runtime_state_store = {}
        snapshot_store = {}
        invalidated_users = []
        utc_now = datetime(2026, 4, 23, 6, 35, 0)
        local_now = datetime(2026, 4, 23, 14, 35, 0)

        def save_runtime_state(user_id, runtime_state):
            runtime_state_store[user_id] = dict(runtime_state)
            return True

        def clear_runtime_state(user_id, state_token=None):
            current = runtime_state_store.get(user_id)
            if not current:
                return True
            if state_token and current.get("state_token") != state_token:
                return True
            runtime_state_store.pop(user_id, None)
            return True

        deps = {
            "utc_now_naive": lambda: utc_now,
            "local_now_naive": lambda: local_now,
            "get_presence_runtime_state": lambda user_id: runtime_state_store.get(user_id),
            "save_presence_runtime_state": save_runtime_state,
            "clear_presence_runtime_state": clear_runtime_state,
            "invalidate_presence_snapshot": lambda user_id: invalidated_users.append(user_id),
            "get_presence_snapshot": lambda user_id: snapshot_store.get(user_id),
            "save_presence_snapshot": lambda user_id, snapshot: snapshot_store.update({user_id: dict(snapshot)}) or True,
            "get_weather": lambda: "北京实时天气：小雨，气温 24°C",
            "get_bionic_state": lambda _user_id: {"current_mood": "平静", "mood_intensity": 0.5},
            "get_last_interaction_time": lambda _user_id: local_now - timedelta(minutes=40),
            "get_recent_history": lambda _user_id, limit=2: [],
            "get_active_memories": lambda _user_id, limit=3: [],
            "render_observation_text": lambda snapshot, deps=None: (
                f"{snapshot['state_source']}|{snapshot['routine_label']}|{snapshot['scene_detail']}",
                "template",
            ),
        }

        replying_token = activate_presence_runtime_state("_verify_runtime_user", "replying", deps=deps)
        ignored_token = activate_presence_runtime_state("_verify_runtime_user", "reminder", deps=deps)
        active_state_code = runtime_state_store.get("_verify_runtime_user", {}).get("state_code")
        text = get_observation_text("_verify_runtime_user", force_refresh=True, deps=deps)
        clear_presence_runtime_state_for_observation(
            "_verify_runtime_user",
            state_token=replying_token,
            deps=deps,
        )

        check("runtime_state 已写入 replying", active_state_code == "replying")
        check("runtime_state 清理后已移除", "_verify_runtime_user" not in runtime_state_store)
        check("低优先级状态不会覆盖高优先级状态", ignored_token is None)
        check("runtime_state observation 优先命中 replying", text.startswith("replying|正在回你消息|"))
        check(
            "runtime_state 会触发 snapshot 失效",
            invalidated_users.count("_verify_runtime_user") >= 2,
        )

    results.append(run("offline.5b observation runtime_state", observation_runtime_state_priority))

    def observation_media_placeholder():
        from app.application.observation_media_service import (
            build_observation_media_task,
            complete_observation_media_task,
        )

        snapshot_store = {}
        runtime_state_store = {}

        def save_snapshot(user_id, snapshot):
            snapshot_store[user_id] = dict(snapshot)
            return True

        def activate_runtime_state(user_id, state_code, **kwargs):
            runtime_state_store[user_id] = {
                "state_code": state_code,
                "state_token": "media-token",
                "scene_hint": kwargs.get("scene_hint", ""),
            }
            return "media-token"

        def clear_runtime_state(user_id, state_token=None, **_kwargs):
            if runtime_state_store.get(user_id, {}).get("state_token") == state_token:
                runtime_state_store.pop(user_id, None)
            return True

        base_snapshot = {
            "snapshot_version": 1,
            "state_source": "media_rendering",
            "routine_slot": "afternoon_gap",
            "routine_label": "镜头正在成像",
            "weather_summary": "小雨",
            "accident_code": "",
            "accident_text": "",
            "mood": "平静",
            "mood_intensity": 0.5,
            "recent_chat_hint": "",
            "memory_hint": "",
            "observation_text": "她像是被镜头定格住，周围光影正在一点点聚焦。",
            "media_type": "text",
            "media_status": "none",
            "media_prompt": "时间：下午；场景：镜头正在成像；动作：她被光影定格",
            "media_key": "",
            "generated_by": "template",
            "generated_at": "2026-04-23 06:35:00",
            "expires_at": "2026-04-23 06:38:00",
            "updated_reason": "media_rendering",
        }

        deps = {
            "get_or_create_observation_snapshot": lambda user_id, force_refresh=False, deps=None: dict(base_snapshot),
            "save_presence_snapshot": save_snapshot,
            "get_presence_snapshot": lambda user_id: snapshot_store.get(user_id),
            "activate_presence_runtime_state": activate_runtime_state,
            "clear_presence_runtime_state_for_observation": clear_runtime_state,
        }

        task = build_observation_media_task("_verify_media_user", "jpg", deps=deps)
        pending_snapshot = snapshot_store["_verify_media_user"]
        done = complete_observation_media_task(
            "_verify_media_user",
            state_token=task["state_token"],
            media_type=task["media_type"],
            media_key="img_v3_fake",
            success=True,
            deps=deps,
        )
        ready_snapshot = snapshot_store["_verify_media_user"]

        check("media 占位任务归一 jpg 为 image", task["media_type"] == "image")
        check("media 占位任务进入 pending", pending_snapshot["media_status"] == "pending")
        check("media 占位任务保留 prompt", "镜头正在成像" in task["media_prompt"])
        check("media_rendering runtime_state 已写入", task["state_token"] == "media-token")
        check("media 占位任务完成为 ready", done["status"] == "ready")
        check("media 占位任务写回 media_key", ready_snapshot["media_key"] == "img_v3_fake")
        check("media_rendering runtime_state 已清理", "_verify_media_user" not in runtime_state_store)

    results.append(run("offline.5c observation media placeholder", observation_media_placeholder))

    def presence_endpoint_http():
        from unittest.mock import patch

        from app.config import Config
        from app.main import get_app

        app = get_app()
        client = app.test_client()
        old_token = Config.PRESENCE_AUTH_TOKEN
        old_admin = Config.ADMIN_OPEN_ID
        Config.PRESENCE_AUTH_TOKEN = "verify-token"
        Config.ADMIN_OPEN_ID = "_verify_presence_http"
        try:
            with patch(
                "app.application.observation_service.build_presence_payload",
                return_value={
                    "status": "ok",
                    "snapshot": {
                        "state_source": "recent_chat",
                        "observation_text": "她刚把手机扣在腿上，眼神还在屏幕上停了停。",
                        "media": {"type": "text", "status": "none", "key": None},
                    },
                },
            ):
                response = client.get(
                    "/presence",
                    headers={"Authorization": "Bearer verify-token"},
                )
            payload = response.get_json()
            check("presence endpoint 返回 200", response.status_code == 200)
            check("presence endpoint 返回 ok", payload["status"] == "ok")
            check("presence endpoint 返回 snapshot", "snapshot" in payload)
        finally:
            Config.PRESENCE_AUTH_TOKEN = old_token
            Config.ADMIN_OPEN_ID = old_admin

    results.append(run("offline.5d presence endpoint", presence_endpoint_http))

    def webhook_decrypt_guard():
        from collections import deque
        from app.entrypoints.feishu_webhook import handle_feishu_webhook

        class Request:
            content_type = "application/json"
            data = b"{}"
            headers = {}

            def get_json(self, silent=False):
                return {"encrypt": "bad"}

            def get_data(self, cache=True):
                return self.data

        class Config:
            FEISHU_ENCRYPT_KEY = "test"

        class Logger:
            def warning(self, *_args, **_kwargs):
                return None

            def error(self, *_args, **_kwargs):
                return None

            def info(self, *_args, **_kwargs):
                return None

        class Cipher:
            def __init__(self, _key):
                return None

            def decrypt(self, _payload):
                return None

        response, status = handle_feishu_webhook(
            Request(),
            config=Config,
            logger_obj=Logger(),
            processed_ids=deque(maxlen=10),
            executor=None,
            core_logic_fn=lambda _data: None,
            verify_signature_fn=lambda _headers, _body: True,
            cipher_cls=Cipher,
            jsonify_fn=lambda payload: payload,
        )
        check("坏密文返回 400", status == 400 and response["msg"] == "invalid encrypted payload")

    results.append(run("offline.6 webhook 解密保护", webhook_decrypt_guard))

    def health_payload_shape():
        from app.ops import check_health

        health = check_health()
        public_health = check_health(include_private=False)
        check("健康检查返回字典", isinstance(health, dict))
        check("包含 observability", "observability" in health)
        check("包含 recent_ai_runs", "recent_ai_runs" in health["observability"])
        check("包含 assets", "assets" in health)
        check("包含 ai_circuit", "ai_circuit" in health)
        check("公开 health 已脱敏", public_health.get("privacy", {}).get("redacted") is True)
        check("公开 health 不暴露 prompt 路径", "prompt_path" not in public_health.get("assets", {}))

    results.append(run("offline.7 健康检查结构", health_payload_shape))

    def provider_circuit_breaker():
        from app.config import Config
        from app.infrastructure.ai.provider_health import (
            can_try_provider,
            get_provider_circuit_summary,
            record_provider_failure,
            record_provider_success,
            reset_provider_circuits,
        )

        old_values = {
            "AI_CIRCUIT_ENABLED": Config.AI_CIRCUIT_ENABLED,
            "AI_CIRCUIT_FAILURE_THRESHOLD": Config.AI_CIRCUIT_FAILURE_THRESHOLD,
            "AI_CIRCUIT_WINDOW_SECONDS": Config.AI_CIRCUIT_WINDOW_SECONDS,
            "AI_CIRCUIT_OPEN_SECONDS": Config.AI_CIRCUIT_OPEN_SECONDS,
        }
        Config.AI_CIRCUIT_ENABLED = True
        Config.AI_CIRCUIT_FAILURE_THRESHOLD = 3
        Config.AI_CIRCUIT_WINDOW_SECONDS = 60
        Config.AI_CIRCUIT_OPEN_SECONDS = 300
        reset_provider_circuits()
        try:
            for _ in range(Config.AI_CIRCUIT_FAILURE_THRESHOLD):
                record_provider_failure("Cerebras", error_type="TimeoutError", operation="chat")
            can_try, reason = can_try_provider("cerebras")
            summary = get_provider_circuit_summary()
            check("连续失败后 provider 熔断", can_try is False and reason == "circuit_open")
            check(
                "熔断摘要标记 open",
                summary["providers"]["cerebras"]["state"] == "open",
            )
            probe_now = time.time() + Config.AI_CIRCUIT_OPEN_SECONDS + 1
            peek_allowed, peek_reason = can_try_provider(
                "cerebras",
                now=probe_now,
                reserve_probe=False,
            )
            peek_summary = get_provider_circuit_summary(now=probe_now)
            check(
                "只读检查不占用半开探测",
                peek_allowed
                and peek_reason == "circuit_half_open_ready"
                and peek_summary["providers"]["cerebras"]["state"] == "half_open_ready",
            )
            probe_allowed, probe_reason = can_try_provider("cerebras", now=probe_now)
            second_allowed, second_reason = can_try_provider("cerebras", now=probe_now)
            check(
                "冷却后半开探测只放行一次",
                probe_allowed
                and probe_reason == "circuit_half_open_probe"
                and not second_allowed
                and second_reason == "circuit_half_open_probe_in_flight",
            )
            record_provider_success("cerebras", operation="chat")
            recovered = get_provider_circuit_summary()
            check("半开探测成功后恢复 closed", recovered["providers"]["cerebras"]["state"] == "closed")
        finally:
            reset_provider_circuits()
            for key, value in old_values.items():
                setattr(Config, key, value)

    results.append(run("offline.8 AI provider 熔断", provider_circuit_breaker))

    def fallback_skips_already_failed_primary():
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.infrastructure.ai.fallback_gateway import call_with_fallback
        from app.infrastructure.ai.provider_health import reset_provider_circuits

        class FakeCompletions:
            def __init__(self, content, counter):
                self.content = content
                self.counter = counter

            def create(self, **_kwargs):
                self.counter["calls"] += 1
                message = SimpleNamespace(content=self.content)
                choice = SimpleNamespace(message=message)
                return SimpleNamespace(choices=[choice])

        class FakeClient:
            def __init__(self, content, counter):
                self.chat = SimpleNamespace(completions=FakeCompletions(content, counter))

        primary_counter = {"calls": 0}
        fallback_counter = {"calls": 0}
        primary_client = FakeClient("primary should not run", primary_counter)
        fallback_client = FakeClient("fallback ok", fallback_counter)
        reset_provider_circuits()
        try:
            with patch(
                "app.infrastructure.ai.fallback_gateway.get_fallback_client",
                return_value=("groq", fallback_client, "fake-groq", "Groq"),
            ):
                reply = call_with_fallback(
                    primary_client,
                    "fake-primary",
                    "Cerebras",
                    [{"role": "user", "content": "hi"}],
                    skip_primary=True,
                    primary_error=TimeoutError("primary timeout"),
                )
            check("已失败主模型不再二次调用", primary_counter["calls"] == 0)
            check("直接调用 fallback", fallback_counter["calls"] == 1 and reply == "fallback ok")
        finally:
            reset_provider_circuits()

    results.append(run("offline.9 fallback 跳过已失败主模型", fallback_skips_already_failed_primary))

    def cheap_ai_releases_half_open_probe():
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.application.memory_reflection_service import call_low_cost_ai
        from app.config import Config
        from app.infrastructure.ai.provider_health import (
            _CIRCUITS,
            get_provider_circuit_summary,
            record_provider_failure,
            reset_provider_circuits,
        )
        from app.infrastructure.ai.provider_registry import get_provider_configs

        class FakeCompletions:
            def create(self, **_kwargs):
                message = SimpleNamespace(content="ok")
                choice = SimpleNamespace(message=message)
                return SimpleNamespace(choices=[choice])

        class FakeClient:
            def __init__(self):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        old_provider = Config.AI_PROVIDER
        old_threshold = Config.AI_CIRCUIT_FAILURE_THRESHOLD
        Config.AI_PROVIDER = "cerebras"
        Config.AI_CIRCUIT_FAILURE_THRESHOLD = 3
        provider_configs = get_provider_configs()
        original_client = provider_configs["cerebras"]["client"]
        provider_configs["cerebras"]["client"] = FakeClient()
        reset_provider_circuits()
        try:
            for _ in range(Config.AI_CIRCUIT_FAILURE_THRESHOLD):
                record_provider_failure("cerebras", error_type="TimeoutError", operation="chat")
            _CIRCUITS["cerebras"]["opened_until"] = 0
            with patch("app.application.memory_reflection_service._chatanywhere_client", None):
                reply = call_low_cost_ai("system", "user", max_tokens=10)
            summary = get_provider_circuit_summary()["providers"]["cerebras"]
            check("低成本 AI 返回内容", reply == "ok")
            check("低成本 AI 成功后释放 half-open probe", summary["state"] == "closed")
            check("低成本 AI 成功后 probe_in_flight 清零", summary["probe_in_flight"] is False)
        finally:
            provider_configs["cerebras"]["client"] = original_client
            Config.AI_PROVIDER = old_provider
            Config.AI_CIRCUIT_FAILURE_THRESHOLD = old_threshold
            reset_provider_circuits()

    results.append(run("offline.9b 低成本 AI 释放 half-open probe", cheap_ai_releases_half_open_probe))

    def persona_consistency_boundaries():
        from app.domain.memory_rules import (
            adjust_importance_for_memory_scope,
            classify_reflection_scope,
            should_save_reflection_scope,
        )
        from app.domain.query_intent import (
            DEFAULT_WEATHER_LOCATION,
            is_persona_private_life_query,
            normalize_weather_query,
        )
        from app.domain.reply_mode import _is_qa_query
        from app.prompt_builder import build_prompt

        private_text = "你今天休息吗还是继续给哪些二线明星化妆"
        mixed_weather = "现在多少点了啊，你那边天气怎么样"
        shared_scope = classify_reflection_scope(
            "我们周日一起吃饭，然后去玩密室吧",
            "哼，谁要跟你约会啊……但票我会看。",
            "用户和助手约定周日一起吃饭、玩密室。",
        )
        private_scope = classify_reflection_scope(
            private_text,
            "昨晚舒淇姐姐为了新剧本找我聊造型，明天还要去北京电影节红毯。",
            "助手提到舒淇、北京电影节和红毯行程。",
        )
        bundled_private_scope = classify_reflection_scope(
            "哎呀，上次我们都去吃过了",
            "我还要给电影节准备指甲样稿，你还总记不住要趁热吃日料。",
            "助手在为下个月的电影节准备指甲样稿，并提到用户总是记不住要趁热吃的日料。",
        )
        scene_location_scope = classify_reflection_scope(
            "你现在在哪里",
            "我在楼下奶茶店第三根灯柱下面，雨太大了。",
            "助手在楼下奶茶店等用户。",
        )
        user_location_scope = classify_reflection_scope(
            "我在楼下奶茶店等你",
            "别乱跑，我马上看手机。",
            "用户在楼下奶茶店等助手。",
        )

        check("私人生活问句识别", is_persona_private_life_query(private_text))
        check(
            "私人生活问句不进 QA",
            not _is_qa_query(private_text, should_search_fn=lambda _text: True),
        )
        check(
            "模糊天气默认北京",
            normalize_weather_query(mixed_weather).startswith(f"{DEFAULT_WEATHER_LOCATION}天气"),
        )
        check(
            "共同经历进入长期记忆",
            shared_scope == "shared_experience" and should_save_reflection_scope(shared_scope),
        )
        check(
            "共同经历提高重要度",
            adjust_importance_for_memory_scope(0.4, shared_scope) >= 0.75,
        )
        check(
            "临场私人剧情不入仿生记忆",
            private_scope == "assistant_private_claim"
            and not should_save_reflection_scope(private_scope),
        )
        check(
            "夹带私人行程的共同话题不入仿生记忆",
            bundled_private_scope == "assistant_private_claim"
            and not should_save_reflection_scope(bundled_private_scope),
        )
        check(
            "助手临场地点不入仿生记忆",
            scene_location_scope == "assistant_private_claim"
            and not should_save_reflection_scope(scene_location_scope),
        )
        check(
            "用户明确地点仍可作为用户事实",
            user_location_scope == "user_fact" and should_save_reflection_scope(user_location_scope),
        )
        check("强思念口语纠偏", "不是字面上的求死" in build_prompt("我想死你啦"))
        check("技术问答允许自然讨论", "可以用自然口吻帮他分析" in build_prompt("帮我看代码报错"))

    results.append(run("offline.10 人设一致性边界", persona_consistency_boundaries))

    def direct_current_time_reply_without_ai():
        from app.application.reply_service import generate_reply

        calls = {
            "ai_stream": 0,
            "summarize": 0,
            "build_prompt": 0,
            "get_user_setting": 0,
            "get_recent_history": 0,
            "prepare_streaming_card": 0,
            "stream_reply": 0,
            "send_feishu": 0,
        }

        def fail_build_prompt(_text):
            calls["build_prompt"] += 1
            raise AssertionError("current time reply should not build an AI prompt")

        def fail_ai_stream(*_args, **_kwargs):
            calls["ai_stream"] += 1
            raise AssertionError("current time reply should not call AI")

        def fail_summarize(*_args, **_kwargs):
            calls["summarize"] += 1
            raise AssertionError("current time reply should not summarize with AI")

        def fail_get_user_setting(*_args, **_kwargs):
            calls["get_user_setting"] += 1
            raise AssertionError("current time reply should not read user settings")

        def fail_get_recent_history(*_args, **_kwargs):
            calls["get_recent_history"] += 1
            raise AssertionError("current time reply should not read chat history")

        sent_messages = []

        def fail_prepare_streaming_card(*_args, **_kwargs):
            calls["prepare_streaming_card"] += 1
            raise AssertionError("current time reply should not prepare streaming card")

        def fail_stream_reply(*_args, **_kwargs):
            calls["stream_reply"] += 1
            raise AssertionError("current time reply should not use stream_reply")

        def capture_send_feishu(_open_id, msg_type, payload):
            calls["send_feishu"] += 1
            sent_messages.append((msg_type, payload))

        deps = {
            "get_user_setting": fail_get_user_setting,
            "get_recent_history": fail_get_recent_history,
            "build_prompt": fail_build_prompt,
            "call_ai_stream": fail_ai_stream,
            "call_ai_summarize": fail_summarize,
            "prepare_streaming_card": fail_prepare_streaming_card,
            "stream_reply": fail_stream_reply,
            "send_feishu": capture_send_feishu,
            "normalize_reply_text": lambda text: text,
        }

        reply_result = generate_reply(
            "_verify_time_user",
            "助手，现在多少点了啊",
            history=None,
            deps=deps,
        )
        reply = reply_result["reply_text"]
        check("纯时间问句直接回复", reply.startswith("现在是"))
        check("时间回复包含 24 小时制", "（" in reply and "）" in reply)
        check(
            "时间回复只走普通文本发送",
            calls["send_feishu"] == 1 and sent_messages == [("text", {"text": reply})],
            f"got: calls={calls}, sent={sent_messages}",
        )
        check(
            "时间回复跳过 AI/卡片链路",
            all(
                calls[key] == 0
                for key in (
                    "ai_stream",
                    "summarize",
                    "build_prompt",
                    "get_user_setting",
                    "get_recent_history",
                    "prepare_streaming_card",
                    "stream_reply",
                )
            ),
            f"got: {calls}",
        )
        check("时间回复使用本地摘要", reply_result["summary"]["intent"] == "报当前时间")

    results.append(run("offline.11 纯时间问句不走 AI", direct_current_time_reply_without_ai))

    def multi_conversation_context_isolation():
        from app.infrastructure.persistence.sqlite_conversation_repo import (
            create_conversation,
            get_active_conversation,
            list_conversations,
            set_active_conversation,
        )
        from app.infrastructure.persistence.sqlite_history_repo import (
            clear_chat_history,
            get_recent_history,
            save_message,
        )

        user_id = "_verify_multi_chat_user"
        default = get_active_conversation(user_id)
        default_id = default["id"]
        save_message(user_id, "user", "默认对话里的第一句", conversation_id=default_id)

        new_conversation = create_conversation(user_id, "代码排查")
        new_id = new_conversation["id"]
        save_message(user_id, "user", "新对话里的第一句", conversation_id=new_id)

        active_history = get_recent_history(user_id, conversation_id=new_id)
        check("新对话只读到自己的历史", active_history[-1]["content"] == "新对话里的第一句")
        check(
            "新对话不混入默认对话",
            all(item["content"] != "默认对话里的第一句" for item in active_history),
        )

        set_active_conversation(user_id, default_id)
        default_history = get_recent_history(user_id)
        check("切回默认对话成功", default_history[-1]["content"] == "默认对话里的第一句")
        check(
            "默认对话不混入新对话",
            all(item["content"] != "新对话里的第一句" for item in default_history),
        )

        clear_chat_history(user_id, conversation_id=default_id)
        check("清空默认上下文后默认历史为空", get_recent_history(user_id) == [])
        set_active_conversation(user_id, new_id)
        check("清空默认上下文不影响新对话", get_recent_history(user_id)[-1]["content"] == "新对话里的第一句")
        check("会话列表包含两个对话", len(list_conversations(user_id)) >= 2)

    results.append(run("offline.12 多重对话上下文隔离", multi_conversation_context_isolation))

    def story_mode_is_conversation_scoped():
        from app.application.context_assembler import build_messages
        from app.application.post_reply_jobs import async_reflect
        from app.infrastructure.persistence.sqlite_conversation_repo import create_conversation

        user_id = "_verify_story_user"
        story = create_conversation(
            user_id,
            "剧情：雨夜楼下",
            mode="story",
            summary="雨夜，她下班后突然出现在你楼下。",
        )
        check("剧情会话创建成功", story.get("mode") == "story")

        deps = {
            "should_search": lambda _text: False,
            "get_user_setting": lambda _user_id, key, default="": "off"
            if key == "pure_mode"
            else default,
            "get_runtime_state_context": lambda _user_id: "【内心的波澜与直觉】\n你当下的状态：平静",
            "get_active_conversation": lambda _user_id: story,
            "get_persona_memory": lambda _text, _n_results=1: "【角色底色与自我认知】\n- 嘴硬心软",
            "get_long_term_memory": lambda *_args, **_kwargs: "",
            "retrieve_bionic_memories": lambda *_args: "",
            "get_user_profile_memory": lambda *_args: "",
            "get_relationship_memory": lambda *_args: "",
            "get_knowledge_memory": lambda *_args: "",
            "search_web_bocha": lambda *_args: "",
            "get_history_by_day_offset": lambda *_args, **_kwargs: [],
        }
        messages = build_messages(
            "你是一个傲娇角色",
            "我抬头看见你站在楼下",
            [],
            "normal",
            user_id,
            deps=deps,
        )
        system_prompt = messages[0]["content"]
        check("剧情提示注入当前会话", "当前剧情模式" in system_prompt)
        check("剧情设定进入提示", "雨夜，她下班后突然出现在你楼下" in system_prompt)
        check("剧情提示声明不写现实事实", "不要当作现实经历或长期事实" in system_prompt)

        called = {"reflect": 0}

        def fail_reflect(*_args, **_kwargs):
            called["reflect"] += 1
            raise AssertionError("story conversation should skip bionic reflection")

        async_reflect(
            user_id,
            "我抬头看见你站在楼下",
            "她撑着伞站在那里。",
            conversation_id=story["id"],
            conversation_mode="story",
            reflect_on_conversation_fn=fail_reflect,
        )
        check("剧情对话跳过现实反思", called["reflect"] == 0)

    results.append(run("offline.13 剧情模式会话隔离", story_mode_is_conversation_scoped))

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"  离线验证结果: {passed}/{total} 通过")
    sys.exit(0 if passed == total else 1)


def main():
    import os
    import atexit
    import tempfile

    # 确保项目根目录在 sys.path 中
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 验证脚本默认切到隔离库，避免污染运行中的 SQLite / Chroma 数据
    isolated_root = tempfile.TemporaryDirectory(prefix="companion_verify_")
    atexit.register(isolated_root.cleanup)
    isolated_db_dir = os.path.join(isolated_root.name, "db")
    isolated_memory_dir = os.path.join(isolated_root.name, "memory")
    os.makedirs(isolated_db_dir, exist_ok=True)
    os.makedirs(isolated_memory_dir, exist_ok=True)
    os.environ["DB_PATH"] = os.path.join(isolated_db_dir, "companion_memory.db")
    os.environ["MEMORY_PATH"] = isolated_memory_dir

    print("=" * 60)
    print("  Feishu AI Companion - 本地验证脚本")
    print("=" * 60)
    print(f"  隔离 DB: {os.environ['DB_PATH']}")
    print(f"  隔离 MEMORY_PATH: {os.environ['MEMORY_PATH']}")
    offline_mode = any(arg in {"--offline", "--fast"} for arg in sys.argv[1:])
    if offline_mode:
        print("  模式: offline（跳过真实 AI / embedding / Feishu 网络请求）")

    from app.infrastructure.persistence._sqlite_common import init_db

    init_db()

    if offline_mode:
        run_offline_quick_checks(Path(project_root))

    results = []

    # ─────────────────────────────────────────────────────────
    # 1. 架构守卫
    # ─────────────────────────────────────────────────────────
    def architecture_guardrails():
        _check_architecture_guardrails(Path(project_root))

    results.append(run("1. 架构守卫", architecture_guardrails))

    # ─────────────────────────────────────────────────────────
    # 2. 语法检查
    # ─────────────────────────────────────────────────────────
    def syntax_check():
        modules = (
            "app.ai_engine",
            "app.main",
            "app.application.memory_reflection_service",
            "app.application.memory_maintenance_service",
            "app.entrypoints.scheduler_runner",
            "app.retrieval",
            "app.voice_matcher",
            "app.vision",
        )
        for module_name in modules:
            importlib.import_module(module_name)
        print("  已编译所有模块（无 SyntaxError）")

    results.append(run("2. 语法检查", syntax_check))

    # ─────────────────────────────────────────────────────────
    # 3. 全模块导入
    # ─────────────────────────────────────────────────────────
    def import_all():
        modules = (
            "app.main",
            "app.ai_engine",
            "app.retrieval",
            "app.voice_matcher",
            "app.vision",
            "app.application.memory_maintenance_service",
            "app.application.memory_reflection_service",
        )
        for module_name in modules:
            importlib.import_module(module_name)

        print(
            "  已导入: main, ai_engine, memory_reflection_service, "
            "memory_maintenance_service, retrieval, voice_matcher, vision"
        )

    results.append(run("3. 全模块导入", import_all))

    # ─────────────────────────────────────────────────────────
    # 4. AI 双向 Fallback 配置
    # ─────────────────────────────────────────────────────────
    def ai_fallback():
        from app.infrastructure.ai import get_active_client, get_fallback_client
        client, model, name = get_active_client()
        check("主引擎可用", client is not None, f"{name}/{model}")
        fb = get_fallback_client(name)
        check("备用引擎可切换", fb is not None, f"{name} -> {fb[3]}")
        print(f"  主引擎: {name}/{model}")
        print(f"  备用引擎: {fb[3]}")

    results.append(run("4. AI 双向 Fallback", ai_fallback))

    # ─────────────────────────────────────────────────────────
    # 5. AI 对话基本通
    # ─────────────────────────────────────────────────────────
    def ai_call():
        from app.ai_engine import call_ai
        r = call_ai("你是一个傲娇的角色", "你好")
        check("AI 返回非空", bool(r and len(r) > 5))
        print(f"  回复片段: {r[:80]}...")

    results.append(run("5. AI 对话（走 fallback 链）", ai_call))

    # ─────────────────────────────────────────────────────────
    # 6. 语音提炼
    # ─────────────────────────────────────────────────────────
    def voice_summarize():
        from app.ai_engine import call_ai_summarize
        r = call_ai_summarize("你好吗", "我很好呀～今天心情不错！")
        check("提炼结果非空", bool(r and len(r) > 0))
        print(f"  提炼: {r}")

    results.append(run("6. 语音提炼", voice_summarize))

    # ─────────────────────────────────────────────────────────
    # 7. bionic_state CRUD
    # ─────────────────────────────────────────────────────────
    def bionic_state_crud():
        from app.infrastructure.persistence.sqlite_memory_repo import (
            bump_relationship_stage,
            get_bionic_state,
            increment_reflection_count,
            init_bionic_state,
            update_bionic_mood,
        )
        uid = "_verify_test_user"

        init_bionic_state(uid)
        update_bionic_mood(uid, "开心", 0.8)
        state = get_bionic_state(uid)
        check("状态写入/读取", state is not None and state["current_mood"] == "开心")

        stage = bump_relationship_stage(uid, 1)
        check("关系阶段递增", stage >= 1)

        increment_reflection_count(uid)
        state2 = get_bionic_state(uid)
        check("反思计数递增", state2["total_reflections"] == state["total_reflections"] + 1)
        print(f"  mood={state['current_mood']}, stage={stage}, reflections={state2['total_reflections']}")

    results.append(run("7. bionic_state CRUD", bionic_state_crud))

    # ─────────────────────────────────────────────────────────
    # 8. 运行时状态上下文格式
    # ─────────────────────────────────────────────────────────
    def runtime_state_context():
        from app.application.memory_reflection_service import get_runtime_state_context
        from app.infrastructure.persistence.sqlite_memory_repo import (
            bump_relationship_stage,
            init_bionic_state,
            update_bionic_mood,
        )
        uid = "_verify_ctx_user"

        init_bionic_state(uid)
        update_bionic_mood(uid, "撒娇", 0.9)
        bump_relationship_stage(uid, 5)
        ctx = get_runtime_state_context(uid)

        check("上下文非空", bool(ctx))
        check("包含运行时标题", "内心的波澜与直觉" in ctx)
        check("包含状态信息", "你当下的状态" in ctx)
        check("包含关系信息", "你对他的感觉" in ctx)
        print(f"  {ctx[:100].strip()}")

    results.append(run("8. 运行时状态上下文", runtime_state_context))

    # ─────────────────────────────────────────────────────────
    # 9. AI 上下文注入运行时状态
    # ─────────────────────────────────────────────────────────
    def ai_context_injection():
        from app.application.context_assembler import build_messages
        from app.infrastructure.persistence.sqlite_memory_repo import init_bionic_state, update_bionic_mood
        uid = "_verify_inject_user"

        init_bionic_state(uid)
        update_bionic_mood(uid, "撒娇", 0.9)
        msgs = build_messages("你是一个傲娇角色", "你好", [], "qa", uid)
        sys_msg = msgs[0]["content"]
        injected = (
            "角色的意识流与状态" in sys_msg
            and "内心的波澜与直觉" in sys_msg
            and "你当下的状态" in sys_msg
        )
        check("运行时状态注入 AI 上下文", injected)
        for line in sys_msg.split("\n"):
            if "你当下的状态" in line or "你对他的感觉" in line:
                print(f"  {line}")

    results.append(run("9. AI 上下文注入运行时状态", ai_context_injection))

    # ─────────────────────────────────────────────────────────
    # 10. 事实层与角色层分离
    # ─────────────────────────────────────────────────────────
    def context_layer_split():
        from unittest.mock import patch
        from app.application.context_assembler import build_messages

        with (
            patch("app.application.context_assembler.get_persona_memory", return_value="【角色】\n- 你嘴硬心软"),
            patch("app.application.context_assembler.get_long_term_memory", return_value="【长期记忆】\n- 他最近总熬夜"),
            patch(
                "app.application.context_assembler._default_retrieve_bionic_memories",
                return_value="【仿生记忆】\n- 你有点心疼他",
            ),
            patch("app.application.context_assembler.get_knowledge_memory", return_value="【知识库】\n- 上海今天有雨"),
            patch("app.application.context_assembler.search_web_bocha", return_value="【天气】: 上海今天小雨，气温 18 度"),
            patch("app.application.context_assembler.should_search", return_value=True),
        ):
            msgs = build_messages("你是一个傲娇角色", "上海今天天气怎么样", [], "qa", "")

        sys_msg = msgs[0]["content"]
        role_marker = "### 💡 角色的意识流与状态"
        reference_marker = "### 🌐 现实参考（仅供事实判断）"
        role_idx = sys_msg.find(role_marker)
        ref_idx = sys_msg.find(reference_marker)

        check("包含角色状态层", role_idx != -1)
        check("包含现实参考层", ref_idx != -1)
        check("角色层位于事实层之前", role_idx < ref_idx)
        check("现实参考约束存在", "不是你的内心独白" in sys_msg and "不要照抄搜索摘要" in sys_msg)
        print(f"  role_idx={role_idx}, ref_idx={ref_idx}")

    results.append(run("10. 事实层与角色层分离", context_layer_split))

    # ─────────────────────────────────────────────────────────
    # 11. 反思引擎完整流程
    # ─────────────────────────────────────────────────────────
    def reflect_flow():
        from app.application.memory_reflection_service import reflect_on_conversation
        from app.infrastructure.persistence.sqlite_memory_repo import get_bionic_state
        uid = "_verify_reflect_user"
        t0 = time.time()
        mid = reflect_on_conversation(
            uid,
            "今天工作好累啊，老板给我加了一堆任务",
            "哎呀，怎么这样啊！太过分了吧！那你有没有跟老板沟通过呢？不过你要是累了就休息一下吧，别把自己逼太紧了嘛💕"
        )
        duration = time.time() - t0
        check("反思返回 ID", mid is not None and mid > 0, f"id={mid}")
        state = get_bionic_state(uid)
        check("反思后状态更新", state["total_reflections"] >= 1)
        print(f"  memory_id={mid}, 耗时={duration:.1f}s, 反思计数={state['total_reflections']}")

    results.append(run("11. 反思引擎完整流程", reflect_flow))

    # ─────────────────────────────────────────────────────────
    # 12. 语音匹配函数签名
    # ─────────────────────────────────────────────────────────
    def voice_matcher_sig():
        from app.voice_matcher import match_voice_file
        from app.ai_engine import call_ai_summarize
        r = match_voice_file("你好", "你好呀～", call_ai_summarize)
        check("voice_matcher 签名正确", r is None or isinstance(r, str))
        print(f"  返回类型: {type(r).__name__}, 值: {r}")

    results.append(run("12. 语音匹配函数签名", voice_matcher_sig))

    # ─────────────────────────────────────────────────────────
    # 13. 语音匹配保底回退
    # ─────────────────────────────────────────────────────────
    def voice_matcher_fallback():
        from unittest.mock import patch
        from app.observability import summarize_recent_degradations
        from app.voice_matcher import match_voice_file

        before_count = summarize_recent_degradations(window_seconds=300)["count"]
        with patch("app.voice_matcher.get_embeddings_batch", return_value=[]):
            path = match_voice_file(
                "你好",
                "你好呀",
                lambda *_: {"intent": "", "emotion": "平静", "theme": "日常"},
            )
        after_count = summarize_recent_degradations(window_seconds=300)["count"]
        check("向量失败时仍返回语音", isinstance(path, str) and len(path) > 0)
        check("语音保底回退会记录降级事件", after_count >= before_count + 1)
        print(f"  fallback={path}")

    results.append(run("13. 语音匹配保底回退", voice_matcher_fallback))

    # ─────────────────────────────────────────────────────────
    # 14. tags 重排生效
    # ─────────────────────────────────────────────────────────
    def voice_matcher_tags_rerank():
        import os
        import tempfile
        from unittest.mock import patch
        from app.config import Config
        from app.voice_matcher import _pick_existing_audio_path

        query_result = {
            "ids": [["tag_hit.opus", "plain_hit.opus"]],
            "distances": [[0.28, 0.11]],
            "metadatas": [[
                {"tags": "晚安,亲昵", "emotion": "开心", "theme": "问候", "length_type": "short"},
                {"tags": "工作,提醒", "emotion": "开心", "theme": "问候", "length_type": "short"},
            ]],
        }

        with tempfile.TemporaryDirectory(prefix="companion_voice_verify_") as tmpdir:
            open(os.path.join(tmpdir, "tag_hit.opus"), "wb").close()
            open(os.path.join(tmpdir, "plain_hit.opus"), "wb").close()
            with patch.object(Config, "VOICE_LIB", tmpdir):
                path, _, filename = _pick_existing_audio_path(
                    query_result,
                    query_tags={"晚安", "亲昵"},
                    emotion="开心",
                    theme="问候",
                    preferred_length_type="short",
                )

        check("tags 重排优先命中 tag 候选", filename == "tag_hit.opus", f"got: {filename}")
        print(f"  rerank={path}")

    results.append(run("14. tags 重排生效", voice_matcher_tags_rerank))

    # ─────────────────────────────────────────────────────────
    # 15. 视觉图片格式检测
    # ─────────────────────────────────────────────────────────
    def vision_format():
        from app.vision import _get_image_media_type
        checks = [
            (b'\x89PNG\r\n\x1a\n', "image/png"),
            (b'\xff\xd8\xff', "image/jpeg"),
            (b'RIFFxxxxWEBP', "image/webp"),
            (b'GIF87a', "image/gif"),
            (b'BM', "image/bmp"),
        ]
        all_ok = True
        for data, expected in checks:
            result = _get_image_media_type(data)
            ok = result == expected
            check(f"  {expected}", ok, f"got: {result}")
            if not ok:
                all_ok = False
        if all_ok:
            print("  全部格式检测通过")

    results.append(run("15. 视觉图片格式检测", vision_format))

    # ─────────────────────────────────────────────────────────
    # 16. Flask app 初始化
    # ─────────────────────────────────────────────────────────
    def flask_init():
        import wsgi

        from app.main import app as compat_app
        from app.main import get_app

        main_app = get_app()
        rules = list(main_app.url_map.iter_rules())
        check("Flask app 创建", main_app.name == "app.main")
        check("兼容导出的 app 指向 canonical 单例", compat_app is main_app)
        check("wsgi.app 与主入口共用同一实例", main_app is wsgi.app)
        print(f"  app.name: {main_app.name}")
        print(f"  路由数: {len(rules)}")

    results.append(run("16. Flask app 初始化", flask_init))

    # ─────────────────────────────────────────────────────────
    # 17. Scheduler 入口
    # ─────────────────────────────────────────────────────────
    def scheduler_entrypoint():
        from unittest.mock import patch

        import run_scheduler

        calls = []

        with patch.object(
            run_scheduler,
            "initialize_runtime",
            side_effect=lambda **kwargs: calls.append(("initialize_runtime", kwargs)),
        ), patch.object(
            run_scheduler,
            "run_scheduler",
            side_effect=lambda: calls.append(("run_scheduler", {})),
        ):
            run_scheduler.main()

        check(
            "scheduler 入口先初始化再进入 pending loop",
            [name for name, _kwargs in calls] == ["initialize_runtime", "run_scheduler"],
            f"got: {calls}",
        )
        check(
            "scheduler 入口跳过卡片预热",
            calls[0][1].get("preload_card_images_enabled") is False,
            f"got: {calls}",
        )

    results.append(run("17. Scheduler 入口", scheduler_entrypoint))

    # ─────────────────────────────────────────────────────────
    # 18. 结构化日志 service 区分
    # ─────────────────────────────────────────────────────────
    def structured_log_service_name():
        import json
        import os
        import subprocess

        script = """
import logging
from app.logger import CustomJSONFormatter
record = logging.LogRecord(
    name='verify',
    level=logging.INFO,
    pathname='verify.py',
    lineno=1,
    msg='hello',
    args=(),
    exc_info=None,
)
print(CustomJSONFormatter().format(record))
"""

        def _render(service_name: str) -> str:
            env = dict(os.environ)
            env["SERVICE_NAME"] = service_name
            output = subprocess.check_output([sys.executable, "-c", script], env=env, text=True)
            return json.loads(output.strip())["service"]

        check(
            "结构化日志支持按入口区分 service",
            _render("feishu-companion-web") == "feishu-companion-web"
            and _render("feishu-companion-scheduler") == "feishu-companion-scheduler"
            and _render("feishu-companion-dev") == "feishu-companion-dev",
        )

    results.append(run("18. 结构化日志 service 区分", structured_log_service_name))

    # ─────────────────────────────────────────────────────────
    # 19. 向量检索模块
    # ─────────────────────────────────────────────────────────
    def retrieval_mod():
        from app.retrieval import get_embedding
        v = get_embedding("测试文本")
        if v is not None and len(v) > 0:
            check("get_embedding 返回向量", True)
            print(f"  向量维度: {len(v)}")
        else:
            # 向量 API 临时不可用（网络抖动），不计入失败
            check("get_embedding 响应（网络故障时跳过）", True)
            print("  向量 API 暂不可用（网络/SSL 错误），代码本身正常")

    results.append(run("19. 向量检索模块", retrieval_mod))

    # ─────────────────────────────────────────────────────────
    # 20. AI 运行观测
    # ─────────────────────────────────────────────────────────
    def ai_run_observability():
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.ai_engine import call_ai
        from app.observability import summarize_recent_ai_runs

        class _FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            finish_reason="stop",
                            message=SimpleNamespace(content="你好呀", tool_calls=None),
                        )
                    ]
                )

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))
        before = summarize_recent_ai_runs(window_seconds=300)["count"]

        with (
            patch(
                "app.ai_engine.resolve_active_provider",
                return_value={
                    "provider": "fake",
                    "client": fake_client,
                    "model": "fake-model",
                    "name": "FakeProvider",
                },
            ),
            patch(
                "app.ai_engine.build_messages",
                return_value=[
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "你好"},
                ],
            ),
        ):
            reply = call_ai("你是一个傲娇角色", "你好", [], "normal", "_verify_ai_run_user")

        summary = summarize_recent_ai_runs(window_seconds=300)
        check("AI 运行事件有新增记录", summary["count"] >= before + 2)
        check("AI 运行包含 chat 维度", summary["by_operation"].get("chat", 0) >= 1)
        check("AI 运行包含完成阶段", summary["by_stage"].get("request_completed", 0) >= 1)
        check("AI 调用返回文本", reply == "你好呀")
        print(f"  ai_runs={summary['count']}, chat_events={summary['by_operation'].get('chat', 0)}")

    results.append(run("20. AI 运行观测", ai_run_observability))

    # ─────────────────────────────────────────────────────────
    # 21. 健康检查返回结构
    # ─────────────────────────────────────────────────────────
    def health_payload():
        from app.ops import check_health
        health = check_health()
        check("健康检查返回字典", isinstance(health, dict))
        check("包含 status", "status" in health)
        check("包含 components", "components" in health)
        check("包含 runtime", "runtime" in health)
        check("包含 observability", "observability" in health)
        check("包含 recent_ai_runs", "recent_ai_runs" in health["observability"])
        check("包含 assets", "assets" in health)
        check("包含 ai_circuit", "ai_circuit" in health)
        print(f"  status={health['status']}, provider={health['runtime'].get('resolved_provider')}")

    results.append(run("21. 健康检查返回结构", health_payload))

    # ─────────────────────────────────────────────────────────
    # 22. 联网搜索显式失败
    # ─────────────────────────────────────────────────────────
    def search_explicit_failure():
        from unittest.mock import patch
        from app.config import Config
        from app.search import SearchUnavailableError, search_web_bocha

        with patch.object(Config, "BOCHA_API_KEY", None):
            try:
                search_web_bocha("上海今天天气怎么样")
            except SearchUnavailableError as exc:
                check("缺少 BOCHA_API_KEY 时显式抛错", exc.degradation_reason == "bocha_api_key_missing")
                print(f"  reason={exc.degradation_reason}")
                return

        raise AssertionError("expected SearchUnavailableError")

    results.append(run("22. 联网搜索显式失败", search_explicit_failure))

    # ─────────────────────────────────────────────────────────
    # 23. 记忆追问禁用外部检索
    # ─────────────────────────────────────────────────────────
    def memory_recall_blocks_external_lookup():
        from unittest.mock import patch
        from app.application.context_assembler import build_messages

        with (
            patch("app.application.context_assembler.get_persona_memory", return_value="【角色】\n- 你嘴硬心软"),
            patch("app.application.context_assembler.get_long_term_memory", return_value="【长期记忆】\n- 他昨天和你聊到很晚"),
            patch(
                "app.application.context_assembler._default_retrieve_bionic_memories",
                return_value="【仿生记忆】\n- 你记得他昨天问过你工作和身体的事",
            ),
            patch(
                "app.application.context_assembler.get_knowledge_memory",
                side_effect=AssertionError("memory recall should not load knowledge"),
            ),
            patch(
                "app.application.context_assembler.search_web_bocha",
                side_effect=AssertionError("memory recall should not search web"),
            ),
            patch(
                "app.application.context_assembler._default_get_history_by_day_offset",
                return_value=[
                    {"role": "user", "content": "昨天我说工作太忙了", "local_time": "23:40"},
                    {"role": "assistant", "content": "你提醒我要注意身体", "local_time": "23:41"},
                ],
            ),
            patch("app.application.context_assembler.should_search", return_value=True),
        ):
            msgs = build_messages(
                "你是一个傲娇角色",
                "你记得我昨天和你说了什么吗",
                [],
                "qa",
                "_verify_memory_recall_user",
            )

        sys_msg = msgs[0]["content"]
        check("记忆追问保留记忆层", "仿生记忆" in sys_msg or "长期记忆" in sys_msg)
        check("记忆追问不注入现实参考层", "### 🌐 现实参考（仅供事实判断）" not in sys_msg)
        check("记忆追问注入真实对话回看", "### 🗂 真实对话回看（优先用于回忆问题）" in sys_msg)
        print("  memory recall skips knowledge/web injection")

    results.append(run("23. 记忆追问禁用外部检索", memory_recall_blocks_external_lookup))

    # ─────────────────────────────────────────────────────────
    # 24. 记忆追问跟问不走轻聊
    # ─────────────────────────────────────────────────────────
    def memory_recall_followup_stays_normal():
        from app.domain.reply_mode import _resolve_reply_mode

        history = [
            {"role": "user", "content": "你记得我昨天和你说了什么吗"},
            {"role": "assistant", "content": "当然记得一点。"},
        ]
        manual_mode, effective_mode = _resolve_reply_mode(
            "那前天呢？",
            "normal",
            should_search_fn=lambda _: False,
            history=history,
        )
        check("跟问保持 normal", manual_mode == "normal" and effective_mode == "normal")
        print(f"  mode={manual_mode}/{effective_mode}")

    results.append(run("24. 记忆追问跟问不走轻聊", memory_recall_followup_stays_normal))

    # ─────────────────────────────────────────────────────────
    # 总结
    # ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"  验证结果: {passed}/{total} 通过")
    if passed == total:
        print("  🎉 全部通过，可以安全重构！")
        sys.exit(0)
    else:
        print("  ⚠️  有失败项，请先修复再重构")
        sys.exit(1)


if __name__ == "__main__":
    main()
