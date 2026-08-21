import json
from types import SimpleNamespace

from app.application.command_service import _memory_audit_reason
from app.domain.memory_rules import classify_reflection_scope, should_include_memory_in_context
from app.domain.persona_policy import (
    PUBLIC_PERSONA_BOUNDARY_POLICY,
    configure_persona_boundary_policy,
    extend_persona_boundary_policy,
    get_persona_boundary_policy,
)
from app.domain.query_intent import is_persona_private_life_query
from app.infrastructure.persona_policy_loader import load_persona_boundary_policy


class _CaptureLogger:
    def __init__(self) -> None:
        self.records = []

    def warning(self, message, **kwargs) -> None:
        self.records.append((message, kwargs))


def test_public_policy_contains_only_general_boundary_defaults() -> None:
    policy = PUBLIC_PERSONA_BOUNDARY_POLICY

    for marker in ("客户", "行程", "工作", "办公室", "咖啡店"):
        assert marker in policy.assistant_private_claim_markers
    assert policy.memory_audit_markers == policy.assistant_private_claim_markers
    assert policy.assistant_self_markers == ("助手", "角色")


def test_public_policy_separates_assistant_claims_from_user_facts() -> None:
    assert (
        classify_reflection_scope("你在忙什么", "我在开会", "助手正在办公室开会")
        == "assistant_private_claim"
    )
    assert (
        classify_reflection_scope("你在哪里", "我在咖啡店", "助手正在咖啡店")
        == "assistant_private_claim"
    )
    assert not should_include_memory_in_context("", "助手正在咖啡店")
    assert not should_include_memory_in_context("", "我在咖啡店等你")
    assert should_include_memory_in_context("", "用户在咖啡店处理自己的工作")
    assert classify_reflection_scope("我的工作很忙", "知道了") == "user_fact"
    assert classify_reflection_scope("我明天去机场", "知道了", "用户明天去机场") == "user_fact"
    assert classify_reflection_scope("我明天要开会", "知道了", "用户明天要开会") == "user_fact"
    assert classify_reflection_scope("我今晚加班", "知道了", "用户今晚加班") == "user_fact"
    assert is_persona_private_life_query("你在咖啡店吗")


def test_loader_extends_public_policy_and_deduplicates(tmp_path) -> None:
    policy_path = tmp_path / "deployment-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "assistant_private_claim_markers": ["private-work-term", "客户"],
                "persona_private_life_markers": ["private-duty-term"],
                "memory_audit_markers": ["private-work-term"],
                "assistant_self_markers": ["custom-neutral-reference"],
            }
        ),
        encoding="utf-8",
    )

    policy = load_persona_boundary_policy(policy_path)

    assert policy.assistant_private_claim_markers.count("客户") == 1
    assert "private-work-term" in policy.assistant_private_claim_markers
    assert "private-duty-term" in policy.persona_private_life_markers
    assert "private-work-term" in policy.memory_audit_markers
    assert "custom-neutral-reference" in policy.assistant_self_markers


def test_loader_invalid_file_falls_back_without_logging_path_or_marker(tmp_path) -> None:
    policy_path = tmp_path / "private-policy-sentinel.json"
    private_marker = "private-marker-sentinel"
    policy_path.write_text(
        '{"schema_version": 1, "assistant_private_claim_markers": ["' + private_marker + '"]',
        encoding="utf-8",
    )
    logger = _CaptureLogger()

    policy = load_persona_boundary_policy(policy_path, logger_obj=logger)

    logged = json.dumps(logger.records, ensure_ascii=False)
    assert policy is PUBLIC_PERSONA_BOUNDARY_POLICY
    assert logger.records
    assert str(policy_path) not in logged
    assert private_marker not in logged


def test_loader_missing_file_falls_back_safely(tmp_path) -> None:
    logger = _CaptureLogger()

    policy = load_persona_boundary_policy(
        tmp_path / "missing-policy.json",
        logger_obj=logger,
    )

    assert policy is PUBLIC_PERSONA_BOUNDARY_POLICY
    assert logger.records[0][1]["extra"]["error_type"] == "FileNotFoundError"


def test_loader_rejects_non_regular_and_oversized_inputs(tmp_path) -> None:
    logger = _CaptureLogger()

    assert (
        load_persona_boundary_policy(tmp_path, logger_obj=logger) is PUBLIC_PERSONA_BOUNDARY_POLICY
    )

    oversized = tmp_path / "oversized-policy.json"
    oversized.write_bytes(b"{" + b"x" * (64 * 1024))
    assert (
        load_persona_boundary_policy(oversized, logger_obj=logger) is PUBLIC_PERSONA_BOUNDARY_POLICY
    )
    assert all(record[1]["extra"]["error_type"] for record in logger.records)


def test_active_policy_is_shared_by_all_boundary_consumers() -> None:
    original_policy = get_persona_boundary_policy()
    extended_policy = extend_persona_boundary_policy(
        PUBLIC_PERSONA_BOUNDARY_POLICY,
        {
            "assistant_private_claim_markers": ("private-work-term",),
            "persona_private_life_markers": ("private-duty-term",),
            "memory_audit_markers": ("private-work-term",),
            "assistant_self_markers": ("custom-neutral-reference",),
        },
    )
    configure_persona_boundary_policy(extended_policy)
    try:
        assert (
            classify_reflection_scope("", "assistant private-work-term")
            == "assistant_private_claim"
        )
        assert not should_include_memory_in_context(
            "",
            "custom-neutral-reference private-work-term",
        )
        assert is_persona_private_life_query("你在做 private-duty-term 吗")
        assert _memory_audit_reason("assistant private-work-term") == "命中：private-work-term"
    finally:
        configure_persona_boundary_policy(original_policy)


def test_bootstrap_configures_loaded_policy(monkeypatch) -> None:
    import app.bootstrap as bootstrap

    prior_initialized = bootstrap._runtime_initialized
    prior_preloaded = bootstrap._card_images_preloaded
    configured = []
    loaded_policy = PUBLIC_PERSONA_BOUNDARY_POLICY
    config = SimpleNamespace(
        PERSONA_POLICY_PATH="/deployment/private-policy.json",
        validate=lambda: None,
    )
    monkeypatch.setattr(bootstrap, "log_runtime_asset_status", lambda **_kwargs: None)
    bootstrap._runtime_initialized = False
    bootstrap._card_images_preloaded = False
    try:
        bootstrap.initialize_runtime(
            config=config,
            logger_obj=_CaptureLogger(),
            init_db_fn=lambda: None,
            load_persona_policy_fn=lambda path, logger_obj: loaded_policy,
            configure_persona_policy_fn=configured.append,
            preload_card_images_enabled=False,
        )
    finally:
        bootstrap._runtime_initialized = prior_initialized
        bootstrap._card_images_preloaded = prior_preloaded

    assert configured == [loaded_policy]
