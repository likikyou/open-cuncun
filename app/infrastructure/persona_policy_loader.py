"""从部署侧 JSON 文件加载角色边界策略扩展。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.persona_policy import (
    PERSONA_POLICY_MARKER_FIELDS,
    PUBLIC_PERSONA_BOUNDARY_POLICY,
    PersonaBoundaryPolicy,
    extend_persona_boundary_policy,
)

PERSONA_POLICY_SCHEMA_VERSION = 1
_MAX_POLICY_BYTES = 64 * 1024
_MAX_MARKERS_PER_FIELD = 256
_MAX_MARKER_LENGTH = 128


class PersonaPolicyLoadError(ValueError):
    """部署侧策略文件无法安全加载。"""


def _validate_payload(payload: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(payload, dict):
        raise PersonaPolicyLoadError("policy payload must be an object")
    if type(payload.get("schema_version")) is not int:
        raise PersonaPolicyLoadError("policy schema_version must be an integer")
    if payload["schema_version"] != PERSONA_POLICY_SCHEMA_VERSION:
        raise PersonaPolicyLoadError("policy schema_version is unsupported")

    allowed_fields = {"schema_version", *PERSONA_POLICY_MARKER_FIELDS}
    if set(payload) - allowed_fields:
        raise PersonaPolicyLoadError("policy payload contains unsupported fields")

    extensions: dict[str, tuple[str, ...]] = {}
    for field_name in PERSONA_POLICY_MARKER_FIELDS:
        raw_markers = payload.get(field_name, [])
        if not isinstance(raw_markers, list):
            raise PersonaPolicyLoadError("policy marker fields must be arrays")
        if len(raw_markers) > _MAX_MARKERS_PER_FIELD:
            raise PersonaPolicyLoadError("policy marker field is too large")

        markers: list[str] = []
        for raw_marker in raw_markers:
            if not isinstance(raw_marker, str):
                raise PersonaPolicyLoadError("policy markers must be strings")
            marker = raw_marker.strip()
            if not marker or len(marker) > _MAX_MARKER_LENGTH:
                raise PersonaPolicyLoadError("policy marker length is invalid")
            markers.append(marker)
        extensions[field_name] = tuple(markers)
    return extensions


def _warn_safe_fallback(logger_obj, error: Exception) -> None:
    if logger_obj is None:
        return
    try:
        logger_obj.warning(
            "Persona boundary policy extension unavailable; using public defaults",
            extra={
                "persona_policy_status": "fallback",
                "error_type": type(error).__name__,
            },
        )
    except Exception:
        return


def load_persona_boundary_policy(
    path: str | Path | None,
    *,
    logger_obj=None,
    base_policy: PersonaBoundaryPolicy = PUBLIC_PERSONA_BOUNDARY_POLICY,
) -> PersonaBoundaryPolicy:
    """加载 JSON 扩展；未配置、缺失或无效时安全回退公共默认。"""
    if path is None or not str(path).strip():
        return base_policy

    try:
        policy_path = Path(path)
        if not policy_path.exists():
            raise FileNotFoundError("persona policy file is missing")
        if not policy_path.is_file():
            raise PersonaPolicyLoadError("policy path must be a regular file")
        with policy_path.open("rb") as policy_file:
            raw_payload = policy_file.read(_MAX_POLICY_BYTES + 1)
        if len(raw_payload) > _MAX_POLICY_BYTES:
            raise PersonaPolicyLoadError("policy file is too large")
        payload = json.loads(raw_payload.decode("utf-8"))
        extensions = _validate_payload(payload)
        return extend_persona_boundary_policy(base_policy, extensions)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        PersonaPolicyLoadError,
        TypeError,
    ) as error:
        _warn_safe_fallback(logger_obj, error)
        return base_policy
