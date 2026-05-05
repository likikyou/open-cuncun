import os
import warnings
from dotenv import load_dotenv

# 项目根目录 = app 目录的上一层
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 自动加载项目根目录下的 .env 文件
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def _resolve_path(path_value: str) -> str:
    if os.path.isabs(path_value):
        return path_value
    return os.path.normpath(os.path.join(PROJECT_ROOT, path_value))


def _get_path_env(env_name: str, default_value: str) -> str:
    return _resolve_path(os.getenv(env_name, default_value))


def _get_bool_env(env_name: str, default_value: bool) -> bool:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _get_positive_int_env(env_name: str, default_value: int) -> int:
    try:
        value = int(os.getenv(env_name, str(default_value)))
    except (ValueError, TypeError):
        warnings.warn(f"{env_name} 不是有效整数，已使用默认值 {default_value}", stacklevel=2)
        return default_value
    return max(1, value)


def _get_positive_float_env(env_name: str, default_value: float) -> float:
    try:
        value = float(os.getenv(env_name, str(default_value)))
    except (ValueError, TypeError):
        warnings.warn(f"{env_name} 不是有效数字，已使用默认值 {default_value}", stacklevel=2)
        return default_value
    return max(0.1, value)


def _get_existing_path_env(
    env_name: str,
    default_value: str,
    fallback_values: list[str] | tuple[str, ...] = (),
    expect_dir: bool = False,
    validator=None,
) -> str:
    primary = _get_path_env(env_name, default_value)

    def _exists(path_value: str) -> bool:
        base_ok = os.path.isdir(path_value) if expect_dir else os.path.exists(path_value)
        if not base_ok:
            return False
        if validator is not None:
            return bool(validator(path_value))
        return True

    if _exists(primary):
        return primary

    for fallback in fallback_values:
        candidate = _resolve_path(fallback)
        if _exists(candidate):
            raw_value = os.getenv(env_name)
            if raw_value:
                warnings.warn(
                    f"{env_name}={primary} 不存在，已自动回退到 {candidate}",
                    stacklevel=2,
                )
            return candidate

    return primary


def _dir_has_files(path_value: str, suffixes: tuple[str, ...]) -> bool:
    try:
        return any(name.lower().endswith(suffixes) for name in os.listdir(path_value))
    except OSError:
        return False


def _get_default_emoticon_dir() -> str:
    project_emoticon_dir = os.path.join(PROJECT_ROOT, "emoticon")
    if os.path.isdir(project_emoticon_dir):
        return project_emoticon_dir
    return project_emoticon_dir


class Config:
    """项目全局配置，所有路径均基于 PROJECT_ROOT 动态计算"""

    # --- 1. 🔴 飞书平台配置 (必需) ---
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
    FEISHU_VERIFY_TOKEN = os.getenv("FEISHU_VERIFY_TOKEN")
    FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY")

    # --- 2. 🧠 AI 模型配置 ---
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")
    BOCHA_API_KEY = os.getenv("BOCHA_API_KEY")

    # 阿里云 DashScope (向量 + 视觉)
    ALI_API_KEY = os.getenv("ALI_API_KEY")

    # Cerebras 快速推理引擎
    CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
    CEREBRAS_API_BASE = os.getenv("CEREBRAS_API_BASE", "https://api.cerebras.ai/v1")
    CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")

    # Groq 极速推理引擎 (Llama, 免费 tier)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # AI 引擎选择：cerebras / deepseek / groq
    AI_PROVIDER = os.getenv("AI_PROVIDER", "cerebras")

    # AI 请求超时与 provider 熔断。主引擎异常时可快速跳过，降低每轮等待超时的体感。
    AI_REQUEST_TIMEOUT_SECONDS = _get_positive_float_env("AI_REQUEST_TIMEOUT_SECONDS", 20.0)
    AI_CIRCUIT_ENABLED = _get_bool_env("AI_CIRCUIT_ENABLED", True)
    AI_CIRCUIT_FAILURE_THRESHOLD = _get_positive_int_env("AI_CIRCUIT_FAILURE_THRESHOLD", 3)
    AI_CIRCUIT_WINDOW_SECONDS = _get_positive_int_env("AI_CIRCUIT_WINDOW_SECONDS", 60)
    AI_CIRCUIT_OPEN_SECONDS = _get_positive_int_env("AI_CIRCUIT_OPEN_SECONDS", 300)

    # 机器人配置
    BOT_NAME = os.getenv("BOT_NAME", "Companion")
    DEEP_THINKING = os.getenv("DEEP_THINKING", "false").lower() == "true"
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

    # 线程池配置
    INGRESS_MAX_WORKERS = max(1, int(os.getenv("INGRESS_MAX_WORKERS", 3)))
    EXECUTOR_MAX_WORKERS = max(1, int(os.getenv("EXECUTOR_MAX_WORKERS", 5)))

    # 定时任务时间（可通过 .env 调整，无需改代码）
    SCHEDULE_MORNING = os.getenv("SCHEDULE_MORNING", "09:00")
    SCHEDULE_NIGHT = os.getenv("SCHEDULE_NIGHT", "00:00")
    SCHEDULE_BRUSH_TEETH = os.getenv("SCHEDULE_BRUSH_TEETH", "22:00")
    SCHEDULE_BACKUP = os.getenv("SCHEDULE_BACKUP", "02:00")
    SCHEDULE_MEMORY_CONSOLIDATE = os.getenv("SCHEDULE_MEMORY_CONSOLIDATE", "03:00")
    SCHEDULE_MEMORY_DECAY = os.getenv("SCHEDULE_MEMORY_DECAY", "04:00")
    MEMORY_FORGET_THRESHOLD = float(os.getenv("MEMORY_FORGET_THRESHOLD", "0.1"))
    MEMORY_IMPORTANCE_PROTECT = float(os.getenv("MEMORY_IMPORTANCE_PROTECT", "0.5"))

    # --- 3. 🛣️ 路径配置 (基于项目根目录) ---
    PROJECT_ROOT = PROJECT_ROOT

    # 核心记忆数据库 (SQLite)
    DB_PATH = _get_path_env("DB_PATH", os.path.join("data", "db", "companion_memory.db"))

    # 提示词与静态资产
    PROMPT_PATH = _get_path_env(
        "PROMPT_PATH", os.path.join("data", "prompts", "example_prompt_template.txt")
    )
    ASSETS_PATH = _get_path_env("ASSETS_PATH", os.path.join("data", "voice_local"))
    VOICE_LIB = _get_existing_path_env(
        "VOICE_LIB",
        os.path.join("assets", "voice"),
        fallback_values=(os.path.join("data", "voice", "Companion_Voice_Library"),),
        expect_dir=True,
        validator=lambda path_value: _dir_has_files(path_value, (".opus", ".mp3", ".wav", ".m4a")),
    )
    MEMORY_PATH = _get_path_env("MEMORY_PATH", os.path.join("data", "db_local"))
    EMOTICON_DIR = _get_existing_path_env(
        "EMOTICON_DIR",
        os.path.relpath(_get_default_emoticon_dir(), PROJECT_ROOT),
        fallback_values=(),
        expect_dir=True,
    )

    # --- 4. 🛡️ 运维配置 ---
    LOG_FILE = _get_path_env("LOG_FILE", os.path.join("logs", "feishu-companion.log"))
    LOG_SERVICE_NAME = os.getenv("SERVICE_NAME", "feishu-companion")
    BACKUP_DIR = _get_path_env("BACKUP_DIR", "backups")

    # 管理员 Open ID
    ADMIN_OPEN_ID = os.getenv("ADMIN_OPEN_ID")

    # 健康检查详情鉴权。未配置时 /health 只返回脱敏公开摘要。
    HEALTH_AUTH_TOKEN = os.getenv("HEALTH_AUTH_TOKEN")
    PRESENCE_AUTH_TOKEN = os.getenv("PRESENCE_AUTH_TOKEN")

    # 实时观察 snapshot 缓存时长（秒）。同一时间窗内默认复用，减少抖动和重复 AI 调用。
    OBSERVATION_CACHE_SECONDS = _get_positive_int_env("OBSERVATION_CACHE_SECONDS", 180)

    # 服务监听地址
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")

    # 服务端口（带类型保护，防止 .env 中写入非数字值导致启动崩溃）
    try:
        SERVER_PORT = int(os.getenv("SERVER_PORT", 8081))
    except (ValueError, TypeError):
        SERVER_PORT = 8081

    # --- 启动校验 ---
    @classmethod
    def validate(cls):
        """校验必需配置项，缺失时抛出明确异常，避免运行时才报错"""
        required = {
            "FEISHU_APP_ID": cls.FEISHU_APP_ID,
            "FEISHU_APP_SECRET": cls.FEISHU_APP_SECRET,
            "FEISHU_ENCRYPT_KEY": cls.FEISHU_ENCRYPT_KEY,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"❌ 缺少必需配置: {', '.join(missing)}，请检查 .env 文件")

        provider_keys = {
            "cerebras": cls.CEREBRAS_API_KEY,
            "groq": cls.GROQ_API_KEY,
            "deepseek": cls.DEEPSEEK_API_KEY,
        }
        if cls.AI_PROVIDER not in provider_keys:
            supported = ", ".join(provider_keys.keys())
            raise ValueError(f"❌ AI_PROVIDER 配置无效: {cls.AI_PROVIDER}，仅支持 {supported}")

        available_providers = [name for name, key in provider_keys.items() if key]
        if not available_providers:
            raise ValueError(
                "❌ 至少需要配置一个 AI Provider 的 API Key："
                "CEREBRAS_API_KEY / GROQ_API_KEY / DEEPSEEK_API_KEY"
            )

        if not provider_keys[cls.AI_PROVIDER]:
            fallback_targets = [name for name in available_providers if name != cls.AI_PROVIDER]
            warnings.warn(
                f"AI_PROVIDER={cls.AI_PROVIDER} 当前未配置对应 API Key，"
                f"启动后将依赖 fallback 到: {', '.join(fallback_targets) or cls.AI_PROVIDER}",
                stacklevel=2,
            )
