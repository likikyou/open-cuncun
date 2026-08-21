import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_release_audit_passes_for_repository_index() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/oss_release_audit.py", "--quiet"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_release_path_policy_blocks_runtime_and_credentials() -> None:
    from scripts.oss_release_audit import _is_sensitive_path

    assert _is_sensitive_path(".env.local") == "sensitive_filename"
    assert _is_sensitive_path("data/db/runtime.sqlite3") == "runtime_artifact"
    assert _is_sensitive_path(".oss-release-blocklist") == "sensitive_filename"
    assert _is_sensitive_path("assets/demo.mp3") == "unapproved_binary"
    assert _is_sensitive_path("docs/images/chat-demo.jpg") == "unapproved_binary"
    assert _is_sensitive_path("docs/images/morning-weather-reminder.jpg") == "unapproved_binary"


def test_secret_patterns_detect_token_shapes_without_literal_fixture() -> None:
    from scripts.oss_release_audit import SECRET_PATTERNS

    synthetic = "ghp_" + ("A" * 36)
    assert any(pattern.search(synthetic) for _rule, pattern in SECRET_PATTERNS)


def test_external_blocklist_is_loaded_and_detected(monkeypatch, tmp_path) -> None:
    from scripts import oss_release_audit

    blocklist = tmp_path / "release-blocklist.txt"
    blocklist.write_text(
        "# deployment-only markers stay outside the repository\nprivate-host.example\n",
        encoding="utf-8",
    )
    markers = oss_release_audit.load_blocked_markers(str(blocklist))
    monkeypatch.setattr(oss_release_audit, "tracked_paths", lambda: ["sample.txt"])
    monkeypatch.setattr(
        oss_release_audit,
        "_blob",
        lambda _path: b"endpoint=private-host.example",
    )

    findings = oss_release_audit.audit_index(markers)

    assert markers == ("private-host.example",)
    assert findings == [
        oss_release_audit.Finding(
            path="sample.txt",
            line=1,
            rule="private_deployment_marker",
        )
    ]
