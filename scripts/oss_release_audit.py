#!/usr/bin/env python3
"""Offline guardrail for files that are about to enter the public repository.

The audit intentionally reports rule names and locations, never matched values.
It is deterministic, uses only the standard library, and scans the Git index so
ignored local secrets are not opened.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_TRACKED_FILE_BYTES = 1_000_000

ALLOWED_BINARY_PATHS: set[str] = set()
BINARY_SUFFIXES = {
    ".7z",
    ".avi",
    ".bmp",
    ".db",
    ".gif",
    ".gz",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".opus",
    ".pdf",
    ".pickle",
    ".png",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".wav",
    ".webm",
    ".webp",
    ".zip",
}
SENSITIVE_BASENAMES = {
    ".env",
    ".oss-release-blocklist",
    "client_secrets.json",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "token.json",
}
SENSITIVE_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}
RUNTIME_PARTS = {
    "artifacts",
    "backups",
    "db",
    "db_local",
    "logs",
    "voice",
    "voice_local",
}

SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("github_fine_grained_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)

ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    \b(?:api[_-]?key|app[_-]?secret|client[_-]?secret|encrypt[_-]?key|
       access[_-]?token|auth[_-]?token|password)\b
    \s*[:=]\s*
    ["']?([^\s"'#},]{8,})
    """
)
PLACEHOLDER_PREFIXES = (
    "$",
    "<",
    "{{",
    "dummy",
    "example",
    "fake",
    "placeholder",
    "replace",
    "test",
    "your",
)


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str


def _run_git(*args: str) -> bytes:
    return subprocess.check_output(
        ["git", *args],
        stderr=subprocess.DEVNULL,
    )


def tracked_paths() -> list[str]:
    raw = _run_git("ls-files", "-z", "--cached")
    return sorted(
        item.decode("utf-8", errors="surrogateescape") for item in raw.split(b"\0") if item
    )


def _blob(path: str) -> bytes:
    return _run_git("show", f":{path}")


def _is_sensitive_path(path: str) -> str | None:
    item = PurePosixPath(path)
    basename = item.name.lower()
    suffix = item.suffix.lower()

    if basename.startswith(".env") and basename != ".env.example":
        return "sensitive_filename"
    if basename in SENSITIVE_BASENAMES or suffix in SENSITIVE_SUFFIXES:
        return "sensitive_filename"
    if any(part.lower() in RUNTIME_PARTS for part in item.parts[:-1]):
        return "runtime_artifact"
    if suffix in BINARY_SUFFIXES and path not in ALLOWED_BINARY_PATHS:
        return "unapproved_binary"
    return None


def load_blocked_markers(blocklist_file: str | None) -> tuple[str, ...]:
    """Load deployment-specific markers from an untracked, external file."""
    if not blocklist_file:
        return ()
    markers = []
    for line in Path(blocklist_file).read_text(encoding="utf-8").splitlines():
        marker = line.strip()
        if marker and not marker.startswith("#"):
            markers.append(marker)
    return tuple(markers)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        any(normalized.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)
        or normalized.endswith("_here")
        or normalized in {"none", "null", "changeme"}
    )


def audit_index(blocked_markers: tuple[str, ...] = ()) -> list[Finding]:
    findings: set[Finding] = set()

    for path in tracked_paths():
        path_rule = _is_sensitive_path(path)
        if path_rule:
            findings.add(Finding(path=path, line=0, rule=path_rule))
            continue

        try:
            content = _blob(path)
        except subprocess.CalledProcessError:
            findings.add(Finding(path=path, line=0, rule="unreadable_index_entry"))
            continue

        allowlisted_binary = path in ALLOWED_BINARY_PATHS
        if len(content) > MAX_TRACKED_FILE_BYTES and not allowlisted_binary:
            findings.add(Finding(path=path, line=0, rule="large_tracked_file"))
            continue
        if b"\0" in content[:8192] and not allowlisted_binary:
            findings.add(Finding(path=path, line=0, rule="unapproved_binary"))
            continue

        text = content.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in blocked_markers):
                findings.add(Finding(path=path, line=line_number, rule="private_deployment_marker"))

            for rule, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.add(Finding(path=path, line=line_number, rule=rule))

            for match in ASSIGNMENT_PATTERN.finditer(line):
                value = match.group(1)
                variable_reference = re.fullmatch(
                    r"(?:Config\.)?[A-Z][A-Z0-9_]*(?:\)|,)?",
                    value,
                )
                if variable_reference or value in {"resolved_key", "resolved_key,", "api_key"}:
                    continue
                if not _is_placeholder(value):
                    findings.add(Finding(path=path, line=line_number, rule="credential_assignment"))

    return sorted(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only failures; useful for CI smoke tests.",
    )
    parser.add_argument(
        "--blocklist-file",
        default=os.getenv("OSS_RELEASE_BLOCKLIST_FILE"),
        help=(
            "Optional untracked file containing one private deployment marker per line; "
            "defaults to OSS_RELEASE_BLOCKLIST_FILE."
        ),
    )
    args = parser.parse_args()

    try:
        blocked_markers = load_blocked_markers(args.blocklist_file)
        findings = audit_index(blocked_markers)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(
            f"OSS release audit could not read the Git index: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 2

    if findings:
        print(f"OSS release audit failed with {len(findings)} finding(s):", file=sys.stderr)
        for finding in findings:
            location = f"{finding.path}:{finding.line}" if finding.line else finding.path
            print(f"- {finding.rule}: {location}", file=sys.stderr)
        return 1

    if not args.quiet:
        print("OSS release audit passed: no blocked public-release findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
