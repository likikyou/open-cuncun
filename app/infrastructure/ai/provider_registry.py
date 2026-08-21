"""AI provider 注册与解析。"""

from __future__ import annotations

from openai import OpenAI

from ...config import Config
from ...logger import logger
from .provider_health import can_try_provider

deepseek_client = None
try:
    if Config.DEEPSEEK_API_KEY:
        deepseek_client = OpenAI(
            api_key=Config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
            timeout=Config.AI_REQUEST_TIMEOUT_SECONDS,
        )
except Exception as exc:
    logger.error(f"DeepSeek 客户端初始化失败: {exc}")

cerebras_client = None
try:
    if Config.CEREBRAS_API_KEY:
        cerebras_client = OpenAI(
            api_key=Config.CEREBRAS_API_KEY,
            base_url=Config.CEREBRAS_API_BASE,
            timeout=Config.AI_REQUEST_TIMEOUT_SECONDS,
        )
        logger.info(f"✅ Cerebras 客户端初始化成功，模型: {Config.CEREBRAS_MODEL}")
except Exception as exc:
    logger.error(f"Cerebras 客户端初始化失败: {exc}")

groq_client = None
if Config.GROQ_API_KEY:
    try:
        groq_client = OpenAI(
            api_key=Config.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=Config.AI_REQUEST_TIMEOUT_SECONDS,
        )
        logger.info(f"✅ Groq 客户端初始化成功，模型: {Config.GROQ_MODEL}")
    except Exception as exc:
        logger.error(f"Groq 客户端初始化失败: {exc}")

_PROVIDER_CONFIG = {
    "cerebras": {
        "client": cerebras_client,
        "model": Config.CEREBRAS_MODEL,
        "name": "Cerebras",
        "fallback": "groq",
    },
    "deepseek": {
        "client": deepseek_client,
        "model": "deepseek-chat",
        "name": "DeepSeek",
        "fallback": "cerebras",
    },
    "groq": {
        "client": groq_client,
        "model": Config.GROQ_MODEL,
        "name": "Groq",
        "fallback": "deepseek",
    },
}


def get_provider_configs() -> dict:
    """暴露 provider 配置，供状态展示和运维检查复用。"""
    return _PROVIDER_CONFIG


def is_provider_available(provider: str) -> bool:
    cfg = _PROVIDER_CONFIG.get(provider)
    return bool(cfg and cfg.get("client"))


def _iter_provider_chain(start_provider: str):
    current = start_provider
    visited = set()
    while current and current not in visited:
        visited.add(current)
        yield current
        current = _PROVIDER_CONFIG.get(current, {}).get("fallback")


def _get_user_provider_preference(user_id: str | None = None) -> tuple[str, bool]:
    provider = Config.AI_PROVIDER
    is_default = True
    if user_id:
        try:
            from ...infrastructure.persistence.sqlite_settings_repo import get_user_setting

            user_provider = get_user_setting(user_id, "ai_provider", "")
            if user_provider and user_provider in _PROVIDER_CONFIG:
                provider = user_provider
                is_default = False
        except Exception as exc:
            logger.warning(f"获取用户 {user_id} 的模型偏好失败: {exc}")

    return provider, is_default


def resolve_active_provider(user_id: str | None = None, *, reserve_probe: bool = True) -> dict:
    preferred_provider, is_default = _get_user_provider_preference(user_id)
    chain = list(_iter_provider_chain(preferred_provider)) or list(_PROVIDER_CONFIG.keys())
    preferred_available = is_provider_available(preferred_provider)
    skip_reasons: dict[str, str] = {}
    for candidate in chain:
        cfg = _PROVIDER_CONFIG.get(candidate)
        if not cfg or not cfg.get("client"):
            skip_reasons[candidate] = "client_unavailable"
            continue

        can_try, circuit_reason = can_try_provider(candidate, reserve_probe=reserve_probe)
        if not can_try:
            skip_reasons[candidate] = circuit_reason or "circuit_blocked"
            continue

        fallback_reason = None
        if candidate != preferred_provider:
            preferred_reason = skip_reasons.get(preferred_provider, "preferred_unavailable")
            fallback_reason = f"{preferred_reason}:{preferred_provider}"
        return {
            "preferred_provider": preferred_provider,
            "preferred_available": preferred_available,
            "provider": candidate,
            "provider_key": candidate,
            "client": cfg["client"],
            "model": cfg["model"],
            "name": cfg["name"],
            "is_default": is_default,
            "used_fallback": candidate != preferred_provider,
            "resolution_chain": chain,
            "resolution_skip_reasons": skip_reasons,
            "circuit_reason": circuit_reason,
            "fallback_reason": fallback_reason,
        }
    return {
        "preferred_provider": preferred_provider,
        "preferred_available": preferred_available,
        "provider": None,
        "provider_key": None,
        "client": None,
        "model": None,
        "name": None,
        "is_default": is_default,
        "used_fallback": False,
        "resolution_chain": chain,
        "resolution_skip_reasons": skip_reasons,
        "circuit_reason": None,
        "fallback_reason": f"no_available_provider_in_chain:{'->'.join(chain)}"
        if chain
        else "no_provider_configured",
    }


def get_active_client(user_id: str | None = None, *, reserve_probe: bool = True):
    resolved = resolve_active_provider(user_id, reserve_probe=reserve_probe)
    if resolved["used_fallback"]:
        logger.warning(
            f"⚠️ 主引擎 {resolved['preferred_provider']} 不可用，自动切换到 {resolved['provider']}"
            f" ({resolved['fallback_reason']})"
        )
    return resolved["client"], resolved["model"], resolved["name"]


def get_fallback_client(current_provider_name: str):
    current_provider_key = next(
        (key for key, cfg in _PROVIDER_CONFIG.items() if cfg.get("name") == current_provider_name),
        None,
    )
    if not current_provider_key:
        return None

    fallback_key = _PROVIDER_CONFIG.get(current_provider_key, {}).get("fallback")
    visited = {current_provider_key}
    while fallback_key and fallback_key not in visited:
        visited.add(fallback_key)
        cfg = _PROVIDER_CONFIG.get(fallback_key)
        if cfg and cfg.get("client"):
            can_try, circuit_reason = can_try_provider(fallback_key)
            if not can_try:
                logger.warning(
                    f"⚠️ fallback provider {fallback_key} 当前熔断，继续寻找下一层"
                    f" ({circuit_reason})"
                )
                fallback_key = (cfg or {}).get("fallback")
                continue
            return fallback_key, cfg["client"], cfg["model"], cfg["name"]
        fallback_key = (cfg or {}).get("fallback")
    return None
