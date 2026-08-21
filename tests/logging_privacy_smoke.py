import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.application.context_assembler import _log_context_observability
from app.config import Config, _get_bool_env
from app.logging_privacy import sensitive_text_fields
from app.presentation.parsers.feishu_event_parser import parse_message


class CaptureLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _record(self, level: str, message: str, **kwargs) -> None:
        self.records.append((level, message, kwargs))

    def info(self, message: str, **kwargs) -> None:
        self._record("info", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._record("warning", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._record("error", message, **kwargs)


def _serialized_records(logger: CaptureLogger) -> str:
    return json.dumps(logger.records, ensure_ascii=False, default=str)


def _voice_query_result(filename: str) -> dict:
    return {
        "ids": [[filename]],
        "documents": [["voice candidate"]],
        "distances": [[0.2]],
        "metadatas": [[{"tags": "", "length_type": "short"}]],
    }


def test_sensitive_text_fields_redacts_by_default() -> None:
    secret = "只有用户和助手知道的正文"

    fields = sensitive_text_fields("message", secret)

    assert fields["message_chars"] == len(secret)
    assert len(fields["message_sha256"]) == 16
    assert secret not in json.dumps(fields, ensure_ascii=False)
    assert "message_preview" not in fields


def test_log_content_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LOG_CONTENT_ENABLED", raising=False)

    assert _get_bool_env("LOG_CONTENT_ENABLED", False) is False


def test_sensitive_text_fields_allows_explicit_preview() -> None:
    secret = "显式开启后可用于受控排障"

    fields = sensitive_text_fields("message", secret, include_content=True)

    assert fields["message_preview"] == secret


def test_sensitive_text_preview_is_limited_to_120_characters() -> None:
    fields = sensitive_text_fields("message", "x" * 200, include_content=True)

    assert fields["message_preview"] == "x" * 120


def test_feishu_text_log_does_not_persist_message_by_default(monkeypatch) -> None:
    secret = "飞书私聊正文 sentinel-42"
    capture = CaptureLogger()
    monkeypatch.setattr(Config, "LOG_CONTENT_ENABLED", False, raising=False)
    event = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_test"}},
            "message": {
                "message_type": "text",
                "message_id": "om_test",
                "content": json.dumps({"text": secret}, ensure_ascii=False),
            },
        },
    }

    open_id, user_text = parse_message(event, logger_obj=capture)

    assert open_id == "ou_test"
    assert user_text == secret
    logged = _serialized_records(capture)
    assert secret not in logged
    assert "user_text_chars" in logged
    assert "user_text_sha256" in logged


def test_context_log_does_not_persist_user_or_memory_text_by_default(monkeypatch) -> None:
    user_secret = "用户正文 sentinel-user"
    memory_secret = "长期记忆 sentinel-memory"
    capture = CaptureLogger()
    monkeypatch.setattr(Config, "LOG_CONTENT_ENABLED", False, raising=False)

    _log_context_observability(
        logger=capture,
        user_id="ou_test",
        user_text=user_secret,
        manual_mode="normal",
        effective_mode="normal",
        need_retrieval=True,
        need_knowledge=False,
        need_web=False,
        pure_mode_enabled=False,
        context_blocks={"long_term": memory_secret, "persona": ""},
        context_degradations={},
    )

    logged = _serialized_records(capture)
    assert user_secret not in logged
    assert memory_secret not in logged
    assert "context_chars" in logged
    assert "context_previews" not in logged


def test_tool_argument_log_is_redacted_by_default(monkeypatch) -> None:
    import app.tools_registry as tools_registry

    secret = "工具参数 sentinel-tool"
    capture = CaptureLogger()
    monkeypatch.setattr(Config, "LOG_CONTENT_ENABLED", False, raising=False)
    monkeypatch.setattr(tools_registry, "logger", capture)

    tools_registry.execute_tool("unknown_tool", json.dumps({"query": secret}, ensure_ascii=False))

    logged = _serialized_records(capture)
    assert secret not in logged
    assert "tool_arguments_chars" in logged


def test_search_log_is_redacted_by_default(monkeypatch) -> None:
    import app.search as search

    secret = "搜索词 sentinel-search"
    normalized = search.normalize_search_query(secret)
    capture = CaptureLogger()
    monkeypatch.setattr(Config, "LOG_CONTENT_ENABLED", False, raising=False)
    monkeypatch.setattr(Config, "BOCHA_API_KEY", "test-key")
    monkeypatch.setattr(search, "logger", capture)
    search._search_cache[normalized] = "cached result"
    try:
        assert search.search_web_bocha(secret) == "cached result"
    finally:
        search._search_cache.pop(normalized, None)

    logged = _serialized_records(capture)
    assert secret not in logged
    assert "query_chars" in logged


def test_invalid_webhook_body_log_is_redacted_by_default() -> None:
    from collections import deque

    from app.entrypoints.feishu_webhook import handle_feishu_webhook

    secret = "malformed webhook sentinel-body"
    capture = CaptureLogger()

    class Request:
        content_type = "application/json"
        data = secret.encode("utf-8")
        headers = {}

        def get_json(self, silent=False):
            raise ValueError("invalid json")

        def get_data(self, cache=True):
            return self.data

    class TestConfig:
        LOG_CONTENT_ENABLED = False

    response, status = handle_feishu_webhook(
        Request(),
        config=TestConfig,
        logger_obj=capture,
        processed_ids=deque(maxlen=10),
        executor=None,
        core_logic_fn=lambda _data: None,
        verify_signature_fn=lambda _headers, _body: True,
        cipher_cls=None,
        jsonify_fn=lambda payload: payload,
    )

    assert status == 400
    assert response["msg"] == "invalid json"
    logged = _serialized_records(capture)
    assert secret not in logged
    assert "body_chars" in logged
    assert "body_sha256" in logged


def test_reflection_invalid_metadata_does_not_enter_logs(monkeypatch) -> None:
    import app.application.memory_reflection_service as reflection

    secret = "sentinel-private-theme"
    capture = CaptureLogger()
    saved: dict = {}

    monkeypatch.setattr(reflection, "logger", capture)
    monkeypatch.setattr(reflection, "init_bionic_state", lambda _user_id: None)
    monkeypatch.setattr(
        reflection,
        "_call_ai_cheap",
        lambda *_args, **_kwargs: json.dumps(
            {
                "content": "一条普通的记忆摘要",
                "theme": secret,
                "emotion": secret,
                "importance": secret,
            },
            ensure_ascii=False,
        ),
    )

    def save_memory(**kwargs):
        saved.update(kwargs)
        return 1

    monkeypatch.setattr(reflection, "save_bionic_memory", save_memory)
    monkeypatch.setattr(reflection, "bio_collection", None)
    monkeypatch.setattr(reflection, "_update_runtime_state", lambda *_args: None)

    assert reflection._do_reflect("user-1", "用户说明了一个普通情况", "助手作出普通回应") == 1
    assert saved["theme"] != secret
    assert saved["emotion"] != secret
    assert secret not in _serialized_records(capture)


def test_health_log_fields_never_include_private_paths_or_event_details() -> None:
    from app.ops import _health_log_fields

    private_path = "/srv/private/persona/prompt.txt"
    private_detail = "private recent degradation detail"
    fields = _health_log_fields(
        {
            "status": "degraded",
            "components": {"ai_engine": True},
            "assets": {
                "prompt_path": private_path,
                "prompt_ok": True,
                "voice_file_count": 3,
            },
            "observability": {
                "recent_degradations": {"count": 1, "recent": [private_detail]},
                "recent_ai_runs": {"count": 2, "recent": [private_detail]},
            },
        }
    )

    serialized = json.dumps(fields, ensure_ascii=False)
    assert private_path not in serialized
    assert private_detail not in serialized
    assert fields["assets"] == {"prompt_ok": True, "voice_file_count": 3}
    assert fields["recent_degradation_count"] == 1
    assert fields["recent_ai_run_count"] == 2


def test_voice_match_logs_redact_intent_tags_and_filename_by_default(monkeypatch, tmp_path) -> None:
    import app.voice_matcher as voice_matcher

    core_secret = "voice-core-intent-sentinel"
    tag_secret = "voice-query-tag-sentinel"
    emotion_secret = "voice-emotion-sentinel"
    theme_secret = "voice-theme-sentinel"
    filename = "private-voice-filename-sentinel.wav"
    (tmp_path / filename).write_bytes(b"voice")
    capture = CaptureLogger()

    class Collection:
        def query(self, **_kwargs):
            return _voice_query_result(filename)

    monkeypatch.setattr(Config, "LOG_CONTENT_ENABLED", False, raising=False)
    monkeypatch.setattr(Config, "VOICE_LIB", str(tmp_path))
    monkeypatch.setattr(voice_matcher, "logger", capture)
    monkeypatch.setattr(voice_matcher, "audio_collection", Collection())
    monkeypatch.setattr(voice_matcher, "get_embeddings_batch", lambda _texts: [[0.1]])
    monkeypatch.setattr(voice_matcher, "_extract_query_tag_hints", lambda *_texts: {tag_secret})
    monkeypatch.setattr(voice_matcher, "_deterministic_fallback_audio", lambda *_parts: None)

    result = voice_matcher.match_voice_file_with_diagnostics(
        "user text",
        "assistant reply",
        lambda *_args: "unused",
        pre_extracted_summary=core_secret,
        emotion=emotion_secret,
        theme=theme_secret,
    )

    assert result.path == str(tmp_path / filename)
    logged = _serialized_records(capture)
    for secret in (core_secret, tag_secret, emotion_secret, theme_secret, filename, str(tmp_path)):
        assert secret not in logged
    assert "core_intent_sha256" in logged
    assert "query_tags_sha256" in logged
    assert "voice_file_sha256" in logged


def test_voice_match_debug_previews_are_limited_and_never_include_full_paths(
    monkeypatch, tmp_path
) -> None:
    import app.voice_matcher as voice_matcher

    core_secret = "core-" + "x" * 180
    tag_secret = "tag-" + "y" * 180
    filename = "private-" + "z" * 140 + ".wav"
    (tmp_path / filename).write_bytes(b"voice")
    capture = CaptureLogger()

    class Collection:
        def query(self, **_kwargs):
            return _voice_query_result(filename)

    monkeypatch.setattr(Config, "LOG_CONTENT_ENABLED", True, raising=False)
    monkeypatch.setattr(Config, "VOICE_LIB", str(tmp_path))
    monkeypatch.setattr(voice_matcher, "logger", capture)
    monkeypatch.setattr(voice_matcher, "audio_collection", Collection())
    monkeypatch.setattr(voice_matcher, "get_embeddings_batch", lambda _texts: [[0.1]])
    monkeypatch.setattr(voice_matcher, "_extract_query_tag_hints", lambda *_texts: {tag_secret})
    monkeypatch.setattr(voice_matcher, "_deterministic_fallback_audio", lambda *_parts: None)

    voice_matcher.match_voice_file_with_diagnostics(
        "user text",
        "assistant reply",
        lambda *_args: "unused",
        pre_extracted_summary=core_secret,
    )

    extras = [record[2].get("extra", {}) for record in capture.records]
    match_fields = next(fields for fields in extras if "core_intent_preview" in fields)
    assert match_fields["core_intent_preview"] == core_secret[:120]
    assert match_fields["query_tags_preview"] == tag_secret[:120]
    assert match_fields["voice_file_preview"] == filename[:120]
    assert all(len(value) <= 120 for key, value in match_fields.items() if key.endswith("_preview"))
    assert str(tmp_path) not in _serialized_records(capture)


def test_runtime_asset_logs_do_not_expose_paths_or_exception_messages(
    monkeypatch, tmp_path
) -> None:
    import app.bootstrap as bootstrap
    import app.retrieval as retrieval

    path_secret = str(tmp_path / "private-runtime-root")
    error_secret = f"cannot inspect collection under {path_secret}"
    capture = CaptureLogger()

    class TestConfig:
        PROJECT_ROOT = path_secret
        PROMPT_PATH = f"{path_secret}/prompt/private.txt"
        VOICE_LIB = f"{path_secret}/voices"
        MEMORY_PATH = f"{path_secret}/memory"

    class FailingCollection:
        def count(self):
            raise RuntimeError(error_secret)

    monkeypatch.setattr(retrieval, "audio_collection", FailingCollection())

    bootstrap.log_runtime_asset_status(config=TestConfig, logger_obj=capture)

    logged = _serialized_records(capture)
    assert path_secret not in logged
    assert error_secret not in logged
    assert "RuntimeError" in logged
    assert "prompt_ok" in logged
    assert "memory_path_ok" in logged


def test_sqlite_init_logs_do_not_expose_db_path(monkeypatch, tmp_path) -> None:
    import contextlib

    import app.infrastructure.persistence._sqlite_common as sqlite_common

    db_path = str(tmp_path / "private-db-sentinel.sqlite3")
    capture = CaptureLogger()

    class Cursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchall(self):
            return []

    monkeypatch.setattr(Config, "DB_PATH", db_path)
    monkeypatch.setattr(sqlite_common, "logger", capture)
    monkeypatch.setattr(sqlite_common.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sqlite_common,
        "get_db_cursor",
        lambda **_kwargs: contextlib.nullcontext(Cursor()),
    )

    sqlite_common.init_db()

    logged = _serialized_records(capture)
    assert db_path not in logged
    assert "记忆库已就绪" in logged


def test_sqlite_init_exception_logs_only_error_type(monkeypatch, tmp_path) -> None:
    import app.infrastructure.persistence._sqlite_common as sqlite_common

    db_path = str(tmp_path / "private-db-error-sentinel.sqlite3")
    error_secret = f"failed to create {db_path}"
    capture = CaptureLogger()

    def raise_private_error(*_args, **_kwargs):
        raise RuntimeError(error_secret)

    monkeypatch.setattr(Config, "DB_PATH", db_path)
    monkeypatch.setattr(sqlite_common, "logger", capture)
    monkeypatch.setattr(sqlite_common.os, "makedirs", raise_private_error)

    sqlite_common.init_db()

    logged = _serialized_records(capture)
    assert db_path not in logged
    assert error_secret not in logged
    assert "RuntimeError" in logged


def test_retrieval_exception_logs_only_error_type(monkeypatch) -> None:
    import app.retrieval as retrieval

    error_secret = "private-vector-query-error-sentinel"
    capture = CaptureLogger()

    class FailingCollection:
        def query(self, **_kwargs):
            raise RuntimeError(error_secret)

    monkeypatch.setattr(retrieval, "logger", capture)
    monkeypatch.setattr(retrieval, "get_embedding", lambda _text: [0.1])

    assert retrieval._query_collection_documents(FailingCollection(), "private query") == []
    logged = _serialized_records(capture)
    assert error_secret not in logged
    assert "RuntimeError" in logged


def test_feishu_media_logs_hide_local_paths_and_resource_keys(monkeypatch) -> None:
    from app.infrastructure.feishu import media_store, messenger

    path_secret = "/srv/private/voices/private-voice.opus"
    key_secret = "img_private_resource_key"
    capture = CaptureLogger()

    monkeypatch.setattr(media_store, "logger", capture)
    monkeypatch.setattr(media_store.os.path, "exists", lambda _path: False)
    assert media_store.upload_audio_v2(path_secret) is None

    monkeypatch.setattr(messenger, "logger", capture)
    monkeypatch.setattr(messenger, "send_feishu", lambda *_args, **_kwargs: True)
    assert messenger.send_image("user-1", key_secret)

    logged = _serialized_records(capture)
    assert path_secret not in logged
    assert key_secret not in logged


def test_feishu_error_logs_hide_response_bodies_urls_and_exceptions(monkeypatch) -> None:
    from app.infrastructure.feishu import client, messenger

    response_secret = "private response body sentinel"
    url_secret = "https://open.feishu.cn/private/resource-id-sentinel"
    error_secret = "request failed for private resource-id-sentinel"
    capture = CaptureLogger()

    class FailedResponse:
        status_code = 500
        text = response_secret

    monkeypatch.setattr(messenger, "logger", capture)
    monkeypatch.setattr(
        messenger.feishu_client,
        "request",
        lambda *_args, **_kwargs: FailedResponse(),
    )
    assert not messenger.send_interactive_card("user-1", {"elements": []})

    monkeypatch.setattr(client, "logger", capture)
    monkeypatch.setattr(
        client.feishu_client,
        "request",
        client.FeishuClient.request.__get__(client.feishu_client, client.FeishuClient),
    )
    monkeypatch.setattr(client.feishu_client, "get_token", lambda: "test-token")

    def raise_private_error(*_args, **_kwargs):
        raise RuntimeError(error_secret)

    monkeypatch.setattr(client.feishu_client.session, "request", raise_private_error)
    assert client.feishu_client.request("GET", url_secret) is None

    logged = _serialized_records(capture)
    for secret in (response_secret, url_secret, error_secret):
        assert secret not in logged
    assert "RuntimeError" in logged
