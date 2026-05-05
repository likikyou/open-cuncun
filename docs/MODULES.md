# Feishu AI Companion 模块说明

> 最后整理：2026-04-23
> 当前仓库状态：V5.7.1 (2026-04-08) + Unreleased，见 [CHANGELOG.md](CHANGELOG.md)。

## 一、怎么读这份文档

这份文档只回答三件事：

1. 这个模块现在是不是“真实实现”还是“兼容 facade”
2. 它对外暴露什么入口
3. 它大致负责哪一层

如果你是第一次接手项目，先看 [READING_ORDER.md](READING_ORDER.md)。

## 二、环境变量总表

### 飞书与服务入口

| 变量 | 默认值 | 说明 |
|:---|:---|:---|
| `FEISHU_APP_ID` | 无 | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 无 | 飞书应用 App Secret |
| `FEISHU_VERIFY_TOKEN` | 无 | 飞书事件验证 Token；当前属于兼容保留项 |
| `FEISHU_ENCRYPT_KEY` | 无 | 飞书加密消息解密 Key |
| `SERVER_HOST` | `0.0.0.0` | Flask 服务监听地址 |
| `SERVER_PORT` | `8081` | Flask 服务监听端口 |
| `DEBUG_MODE` | `false` | Flask debug 开关；当前仍固定关闭 reloader |
| `ADMIN_OPEN_ID` | 无 | 管理员 Open ID，供提醒和主动消息使用 |
| `PRESENCE_AUTH_TOKEN` | 无 | `/presence` 只读观察接口的鉴权 token；未配置时接口返回 `503 disabled` |

### AI 与联网

| 变量 | 默认值 | 说明 |
|:---|:---|:---|
| `AI_PROVIDER` | `cerebras` | 主引擎选择：`cerebras` / `groq` / `deepseek` |
| `CEREBRAS_API_KEY` | 无 | Cerebras API Key |
| `CEREBRAS_API_BASE` | `https://api.cerebras.ai/v1` | Cerebras API Base URL |
| `CEREBRAS_MODEL` | `llama-3.3-70b` | Cerebras 模型名 |
| `GROQ_API_KEY` | 无 | Groq API Key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq 模型名 |
| `DEEPSEEK_API_KEY` | 无 | DeepSeek API Key |
| `AI_REQUEST_TIMEOUT_SECONDS` | `20` | OpenAI 兼容 provider 单次请求超时 |
| `AI_CIRCUIT_ENABLED` | `true` | 是否启用 AI provider 熔断 |
| `AI_CIRCUIT_FAILURE_THRESHOLD` | `3` | 窗口内连续失败达到多少次后熔断 |
| `AI_CIRCUIT_WINDOW_SECONDS` | `60` | 失败计数滚动窗口秒数 |
| `AI_CIRCUIT_OPEN_SECONDS` | `300` | 熔断打开后跳过该 provider 的秒数；到期后进入半开探测 |
| `CHATANYWHERE_API_KEY` | 无 | 低成本后台推理 Key，供反思、整合和提醒任务优先使用 |
| `BOCHA_API_KEY` | 无 | 联网搜索 API Key |
| `ALI_API_KEY` | 无 | 图片识别所需 DashScope Key |
| `DEEP_THINKING` | `false` | 状态面板中的深度思考开关展示项 |

### 机器人行为与线程

| 变量 | 默认值 | 说明 |
|:---|:---|:---|
| `BOT_NAME` | `Companion` | 机器人显示名 |
| `INGRESS_MAX_WORKERS` | `3` | 飞书入口线程池大小 |
| `EXECUTOR_MAX_WORKERS` | `5` | 后台任务线程池大小 |

### 调度与记忆

| 变量 | 默认值 | 说明 |
|:---|:---|:---|
| `SCHEDULE_MORNING` | `09:00` | 早安提醒时间 |
| `SCHEDULE_NIGHT` | `00:00` | 晚安提醒时间 |
| `SCHEDULE_BRUSH_TEETH` | `22:00` | 刷牙提醒时间 |
| `SCHEDULE_BACKUP` | `02:00` | 数据库备份时间 |
| `SCHEDULE_MEMORY_CONSOLIDATE` | `03:00` | 记忆整合时间 |
| `SCHEDULE_MEMORY_DECAY` | `04:00` | 记忆衰减时间 |
| `MEMORY_FORGET_THRESHOLD` | `0.1` | 低于该强度且不满足保护条件时触发遗忘 |
| `MEMORY_IMPORTANCE_PROTECT` | `0.5` | 高于该重要度时不轻易遗忘 |
| `OBSERVATION_CACHE_SECONDS` | `180` | 实时观察快照缓存秒数；缓存未过期时 `/observe` 与 `/presence` 共用同一份 `presence_snapshot` |

### 路径覆盖

| 变量 | 默认值 | 说明 |
|:---|:---|:---|
| `DB_PATH` | `data/db/companion_memory.db` | SQLite 数据库路径 |
| `PROMPT_PATH` | `data/prompts/prompt_template.txt` | 运行时人格提示词模板路径 |
| `ASSETS_PATH` | `data/voice_local` | 历史音频资产目录兼容项 |
| `VOICE_LIB` | `data/voice/Companion_Voice_Library` | 原始语音文件目录；若不存在会回退到历史目录 |
| `MEMORY_PATH` | `data/db_local` | 记忆与知识库向量路径 |
| `EMOTICON_DIR` | `emoticon` | 表情包目录；不存在时兼容旧目录 |
| `LOG_FILE` | `logs/feishu-companion.log` | 运行日志文件 |
| `SERVICE_NAME` | `feishu-companion` | 结构化日志里的 `service` 字段；`run.py` / `wsgi.py` / `run_scheduler.py` 会分别默认覆盖为 `feishu-companion-dev` / `feishu-companion-web` / `feishu-companion-scheduler` |
| `BACKUP_DIR` | `backups` | 备份目录 |

说明：相对路径会按 `PROJECT_ROOT` 自动解析。

## 三、最重要的模块边界

### 0. 工程与依赖文件

| 文件 | 角色 | 说明 |
|:---|:---|:---|
| `pyproject.toml` | 当前工程配置入口 | 收口项目依赖、Python 版本约束与 `Ruff` 基础配置 |
| `uv.lock` | 锁文件 | 记录当前 `uv lock` 解析后的依赖快照，便于新机器复现 |
| `requirements.txt` | 兼容安装入口 | 现阶段继续保留，方便旧环境或临时机器沿用 `pip install -r requirements.txt` |
| `run.py` | 开发启动入口 | 本地开发一键启动 Web + 进程内 scheduler；默认日志 `service=feishu-companion-dev` |
| `wsgi.py` | 生产 Web 入口 | Gunicorn 加载的 WSGI app；默认日志 `service=feishu-companion-web` |
| `run_scheduler.py` | 生产 scheduler 入口 | 独立 scheduler 进程启动脚本；默认日志 `service=feishu-companion-scheduler` |
| `.gitignore` | 本地缓存与产物忽略 | 当前已额外忽略 `.ruff_cache/` |

### 1. 真实入口与主链模块

| 模块 | 类型 | 说明 |
|:---|:---|:---|
| `app/main.py` | 薄入口/兼容导出 | 暴露 `create_app()`、`get_app()`、懒加载 canonical app 单例、`/health`、`/presence`、路由与 `start_app()`，内部转发到 bootstrap / entrypoints |
| `app/bootstrap.py` | 真实入口 | 启动前初始化、资产预热、运行时资产检查，以及开发模式 scheduler 线程启动 |
| `app/entrypoints/feishu_webhook.py` | 真实入口 | 飞书 challenge、解密、验签、去重与异步投递 |
| `app/entrypoints/scheduler_runner.py` | 真实入口 | scheduler 真实入口、任务注册与 pending loop |
| `app/application/chat_orchestrator.py` | 真实主链入口 | 同用户串行化、命令分发、主对话编排、写入顺序和后台任务触发 |

### 2. Presentation 层

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/presentation/parsers/feishu_event_parser.py` | `parse_message()` | 解析文本、图片、sticker、卡片按钮回调；`/observe` 也在命令白名单里 |
| `app/presentation/cards/builders.py` | `build_*_card()` | 生成 `/status`、`/reply`、`/pure`、`/memory`、`/model`、`/chat`、`/story`、`/reset`、`/clear`、`/help` 卡片 JSON；`/chat`、`/story` 与 `/memory audit` 是二级控制台，卡片按钮可见文案保持中文动作名；帮助卡片里也提供 `/observe` 快捷入口 |
| `app/presentation/cards/assets.py` | `preload_card_images()`、`build_card_hero_image()` | 负责主图查找、缓存、预热；上传策略可注入 |
| `app/presentation/formatters/status_formatter.py` | `format_status_summary()` 等 | 状态和模型卡片文案格式化 |
| `app/presentation/formatters/memory_formatter.py` | `format_memory_state()` 等 | 记忆看板进度条、关系阶段、摘要格式化 |

### 3. Application 层

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/application/chat_orchestrator.py` | `core_logic()`、`executor` | 同用户串行化、命令分发、主对话编排、写入顺序和后台任务触发；同时暴露入口线程池 |
| `app/application/command_service.py` | `handle_command()` | 统一处理所有用户命令；`/observe` 返回实时观察文字，`/chat`、`/story` 会优先返回可点击卡片控制台，`/memory audit` 用于审核疑似剧情污染记忆并触发逐条遗忘 |
| `app/application/observation_service.py` | `get_or_create_observation_snapshot()`、`build_presence_payload()`、`observation_runtime_state()` | 实时观察快照编排、显式运行时状态管理、缓存复用、第三人称白描渲染与 `/presence` 载荷构建；AI 失败时回退模板文案 |
| `app/application/observation_media_service.py` | `build_observation_media_task()`、`complete_observation_media_task()`、`normalize_observation_media_type()` | 实时观察媒体任务占位骨架；当前不接真实图片/GIF/视频 API，只归一媒体类型、写入 `pending/ready/failed`、复用 `media_prompt` 并清理 `media_rendering` 状态 |
| `app/application/reply_service.py` | `generate_reply()` | prompt、AI 流式回复、卡片预创建、摘要提炼；纯当前时间问句直接发送普通文本，不再创建流式卡片 |
| `app/application/post_reply_jobs.py` | `async_reflect()`、`async_voice_reply()` | 回复后的反思、语音、告警任务；剧情对话会跳过现实仿生记忆反思 |
| `app/application/context_assembler.py` | `build_messages()` | 按策略并发检索与上下文装配，并显式记录 `context_degradations`；回忆问题优先注入真实对话回看；剧情对话会注入仅限当前会话的剧情设定 |
| `app/application/reset_service.py` | `clear_user_history()`、`clear_chat_context()` | 定义 reset/clear 的真实边界：`/clear` 只切换上下文边界，`/reset` 才会删除聊天、画像和仿生记忆 |
| `app/application/memory_reflection_service.py` | `reflect_on_conversation()`、`retrieve_bionic_memories()`、`get_runtime_state_context()` | 反思提炼、仿生记忆检索、运行时状态；反思前会按 scope 过滤临场私人剧情，低成本 AI 调用会回写 provider 熔断状态 |
| `app/application/memory_maintenance_service.py` | `consolidate_memories()`、`decay_and_forget()` | 夜间整合与遗忘 |
| `app/application/reminder_service.py` | `morning_greeting()` 等 | 早安、晚安、刷牙提醒 |
| `app/application/proactive_chat_service.py` | `proactive_thought_task()` | 主动消息判断与发送 |

### 4. Domain 层

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/domain/query_intent.py` | `is_memory_recall_query()`、`get_memory_recall_day_offset()`、`is_persona_private_life_query()`、`normalize_weather_query()` | 回忆追问识别、相对日期提取、短跟问继承、Companion私人生活问句识别与默认天气地点归一 |
| `app/domain/reply_mode.py` | `_normalize_reply_mode()`、`_resolve_reply_mode()` | `light / normal / qa` 规则和 heuristics |
| `app/domain/context_policy.py` | `_adjust_effective_mode_for_pure_mode()` 等 | `pure_mode`、检索开关、各类 context 限额；纯当前时间问句会关闭 `knowledge/web`，混合天气问句仍允许联网查天气 |
| `app/domain/observation_rules.py` | `resolve_routine_slot()`、`build_observation_seed()`、`build_observation_context()` | 实时观察的时间槽位、稳定随机 seed 与意外事件生成；保持同一时间桶内场景稳定 |
| `app/domain/reply_text.py` | `normalize_reply_text()` | 把模型多段短句压成单段自然文本，保留括号动作和停顿画面感 |
| `app/domain/memory_rules.py` | `clamp_importance()`、`classify_reflection_scope()`、`calculate_retention()` 等 | importance、反思 scope、共同经历保护、关系阶段和心情规则 |

### 5. Infrastructure 层

#### AI

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/infrastructure/ai/__init__.py` | `get_active_client()`、`call_with_fallback()`、`AIFallbackExhaustedError` | AI 基础设施公共导出入口 |
| `app/infrastructure/ai/provider_registry.py` | `resolve_active_provider()`、`get_active_client()` | provider 选择、用户级模型偏好、熔断跳过与 fallback 起点 |
| `app/infrastructure/ai/provider_health.py` | `can_try_provider()`、`record_provider_failure()`、`get_provider_circuit_summary()` | provider 熔断状态机、半开探测和 `/health` 摘要 |
| `app/infrastructure/ai/fallback_gateway.py` | `call_with_fallback()` | 统一 fallback 调用；主链已失败时可跳过二次主模型调用，主链耗尽时抛 `AIFallbackExhaustedError`，并记录降级与熔断事件 |

#### Feishu

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/infrastructure/feishu/__init__.py` | `send_feishu()`、`upload_audio_v2()`、`feishu_client` | Feishu 基础设施公共导出入口 |
| `app/infrastructure/feishu/client.py` | `FeishuClient`、`get_token()` | token 和 HTTP 请求 |
| `app/infrastructure/feishu/messenger.py` | `send_feishu()`、`send_interactive_card()`、`create_streaming_card()` 等 | 文本/卡片/流式消息发送 |
| `app/infrastructure/feishu/media_store.py` | `upload_image()`、`upload_audio_v2()`、`download_resource()` | 飞书媒体上传与下载 |
| `app/infrastructure/feishu/card_streamer.py` | `prepare_streaming_card()`、`stream_reply()` | 飞书流式卡片与文本降级链路 |

#### Persistence

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/infrastructure/persistence/_sqlite_common.py` | `init_db()`、`get_db_cursor()` | SQLite 连接与建表 |
| `app/infrastructure/persistence/sqlite_conversation_repo.py` | `create_conversation()`、`get_active_conversation()`、`list_conversations()`、`set_active_conversation()`、`rename_conversation()` | 同一飞书私聊里的多重对话元数据、剧情模式字段与当前活跃会话 |
| `app/infrastructure/persistence/sqlite_history_repo.py` | `save_message()`、`get_recent_history()`、`get_history_by_day_offset()`、`clear_chat_history()`、`delete_chat_history()` | 聊天记录、按日期回看、按 `conversation_id` 隔离的上下文边界与计数；`clear_chat_history()` 只更新当前对话边界，不物理删记录 |
| `app/infrastructure/persistence/sqlite_settings_repo.py` | `get_user_setting()`、`set_user_setting()` | 用户设置；同时承载 `active_conversation_id`、`chat_context_after_id:{conversation_id}` 这类运行时上下文边界 |
| `app/infrastructure/persistence/sqlite_memory_repo.py` | `save_bionic_memory()`、`get_memory_stats()`、`get_active_memories()`、`mark_user_memories_forgotten()` 等 | 仿生记忆、运行时状态与记忆审核中的用户限定遗忘操作 |
| `app/infrastructure/persistence/sqlite_observation_repo.py` | `get_presence_snapshot()`、`save_presence_snapshot()`、`get_presence_runtime_state()`、`save_presence_runtime_state()` | `presence_snapshot` 与 `presence_runtime_state` 的读取、覆盖写入和缓存失效；供 `/observe`、`/presence` 与显式状态入口共用 |
| `app/infrastructure/persistence/sqlite_profile_repo.py` | `upsert_user_profile_fact()`、`upsert_relationship_insight()` | 用户画像与关系洞察 |

#### Vector

| 模块 | 关键入口 | 说明 |
|:---|:---|:---|
| `app/infrastructure/vector/chroma_memory_store.py` | `delete_bionic_memory_vectors()` 等 | reset 时的向量删除 |
| `app/infrastructure/vector/chroma_audio_store.py` | 骨架 | 预留音频向量仓储抽象 |
| `app/infrastructure/vector/embedding_gateway.py` | 骨架 | 预留 embedding 抽象 |

### 6. 仍作为稳定底座的能力模块

| 模块 | 说明 |
|:---|:---|
| `app/prompt_builder.py` | 运行时人格提示词构建与热更新；会按用户输入动态追加语义提醒，例如把“想死你了”纠偏为强烈思念而非字面求死 |
| `app/ai_engine.py` | LLM 调用、工具循环、摘要提炼，并记录请求/首包/工具/fallback 运行事件 |
| `app/tools_registry.py` | 本地时间/天气工具定义与执行；`get_current_time` 当前直接读取服务器本地时区 |
| `app/retrieval.py` | Chroma/FastEmbed 检索与多集合加载 |
| `app/logger.py` | 结构化 JSON 日志；`service` 字段可按入口自动区分，也可由 `SERVICE_NAME` 覆盖 |
| `app/voice_matcher.py` | 语音匹配、Metadata 过滤、tags 重排、显式降级观测与保底 |
| `app/search.py` | Bocha 搜索、显式失败抛错与实时性判断 |
| `app/vision.py` | 图片分析 |
| `app/weather.py` | 天气查询 |
| `app/security.py` | 飞书签名校验与 AES 解密 |
| `app/ops.py` | 健康检查、备份与 `/health` 的 `recent_degradations/recent_ai_runs` 聚合；支持公开脱敏摘要与授权详情 |
| `app/observability.py` | 最近 5 分钟降级事件与 AI 运行事件缓冲，以及 `/health` 聚合摘要 |
| `app/http_client.py` | 带重试的统一 Session |
| `app/time_utils.py` | SQLite naive UTC 与本地时间换算 |

## 四、当前最关键的行为约束

- `app/main.py` 只保留 `create_app()`、`get_app()`、Flask 路由、`start_app()` 与兼容导出；challenge、验签、解密与 `event_id` 去重由 `app/entrypoints/feishu_webhook.py` 承接。
- `run.py` 是开发模式入口；生产模式现在通过 `wsgi.py` 承接 Web 进程，通过 `run_scheduler.py` 承接独立 scheduler 进程。
- PM2 拉起 `gunicorn` 时应使用 `pm2 start .venv/bin/gunicorn --interpreter none ...`，否则可能被 PM2 当成 Node 脚本执行。
- `app/entrypoints/feishu_webhook.py` 对坏 JSON、坏密文和解密后空对象直接返回 `400`，不再把异常请求吞成空对象或继续进入 challenge/event 解析。
- 同一用户消息在 `app/application/chat_orchestrator.py` 里串行化。
- `reply_mode` 与 `pure_mode` 的实际规则由 `domain/reply_mode.py`、`domain/context_policy.py` 决定。
- “你记得我昨天说了什么”“那前天呢”这类问题的识别与日期提取由 `domain/query_intent.py` 决定，避免短跟问误掉进 `light`；“现在几点/今天几号”、天气默认地点和Companion私人生活问句也在这里单独识别。
- “你今天休息吗”“给哪些明星化妆”“你明天去哪”这类问Companion私人生活/工作/行程的问题不应触发 knowledge/web；它们应该走关系内回答，避免外部新闻污染Companion自己的经历。
- 天气问句没有明确地点时默认查“默认城市”；如果和“现在几点”混在同一句里，时间仍读本地时间，天气仍允许联网查默认城市。
- 流式卡片成功路径与文本降级路径统一收口到 `infrastructure/feishu/card_streamer.py`；卡片更新和文本降级前都会先走 `domain/reply_text.py` 做单段化归一。
- 纯当前时间问句现在直接发送普通文本，不再创建流式卡片，也不再走 AI 摘要链路。
- 回复结束后的摘要提炼仍在 `reply_service.generate_reply()` 内执行，但会先对回复做归一化，保证落库文本、摘要输入和用户最终看到的内容口径一致。
- `prompt_builder.py` 除了拼接当前时间和基础人格提示外，还会针对少数容易误判的中文口语追加当轮语义提醒；目前已覆盖“想死你了/想你想死了”这类强思念表达，避免模型误判成自伤或说教。
- `fallback_gateway.py` 在主引擎和备用链路都失败时抛 `AIFallbackExhaustedError`；最终用户兜底文案只留在 `ai_engine.py` 边界层。
- `provider_health.py` 维护每个 provider 的熔断状态：失败窗口内达到阈值会打开熔断，打开期间直接跳过该 provider，到期后只放行一次半开探测；只读状态检查不会占用探测名额。
- `memory_reflection_service.py` / `memory_maintenance_service.py` / reminder 链路共用的低成本 AI 入口现在会显式回写 `record_provider_success/failure`，避免 half-open probe 被后台任务卡住。
- `search.py` 只有“确实没搜索结果”才返回空字符串；配置缺失、HTTP 失败、返回非法 JSON 或业务失败都会显式抛错，由 `context_assembler.py` 记录为降级。
- `tools_registry.get_current_time()` 现在直接读取 VPS 本地时区时间；当前时间问句不会再触发 `knowledge/web`，避免把搜索脏数据混进时间回答。
- `voice_matcher.py` 把“语义没命中”和“系统故障”分开：语义没命中只记 `info` 并保底回退；向量/集合/查询故障记 `warning/error`，会进入 `/health` 的 `observability.recent_degradations`。
- `ai_engine.py` 现在会按轮记录 `request_started/request_completed/first_chunk/tool_batch_completed/fallback_*` 等 AI 运行事件，供 `/health` 和排障查看。
- `ops.check_health()` 会把最近 5 分钟的降级事件聚合进 `observability.recent_degradations`，把 AI 主链事件聚合进 `observability.recent_ai_runs`，并返回 `ai_circuit` provider 熔断摘要；窗口内出现 `error` 或 `warning >= 3` 时，健康状态会标成 `degraded`。
- `app/main.py` 的 `/health` 默认只返回脱敏公开摘要；配置 `HEALTH_AUTH_TOKEN` 后，带 `Authorization: Bearer <token>` 或 `X-Health-Token: <token>` 才返回完整路径和观测 details。
- `app/main.py` 的 `/presence` 默认不会开放；只有配置 `PRESENCE_AUTH_TOKEN` 后，带 `Authorization: Bearer <token>` 或 `X-Presence-Token: <token>` 才会返回观察快照；若未传 `user_id`，当前实现会回退到 `ADMIN_OPEN_ID`。
- `application/reset_service.py` 决定 reset/clear 的真正删除边界；repo 本身不直接决定向量清理策略。
- `sqlite_history_repo.clear_chat_history()` 不再直接删除 `chat_history`，而是把当前 `MAX(id)` 写到 `user_settings.chat_context_after_id`；`get_recent_history()` 只返回这个边界之后的消息。
- 多重对话会把 `chat_history.conversation_id` 作为上下文隔离边界；旧聊天会自动迁入 `default:<open_id>`，当前激活对话写在 `user_settings.active_conversation_id`。
- `observation_service.py` 不会混进主聊天 prompt；它先生成并缓存 `presence_snapshot`，再用低成本 AI 把结构化状态渲染成第三人称白描；AI 不可用时仍会回退模板文案。
- `observation_media_service.py` 当前只负责媒体任务占位，不调用真实生成 API；它会把 `jpg/jpeg/png` 归一为 `image`、把 `mp4` 归一为 `video`，并把任务状态写回同一份 `presence_snapshot`。
- `chat_orchestrator.py`、`post_reply_jobs.py`、`reminder_service.py`、`proactive_chat_service.py` 和未来媒体 worker 会短时写入 `presence_runtime_state`；`replying > media_rendering > reflecting > proactive > reminder` 由优先级和 token 清理共同保证，不会被低优先级状态误覆盖。
- 剧情模式是 `conversations.mode='story'` 的独立对话：`context_assembler.py` 只在当前会话注入剧情设定，`post_reply_jobs.async_reflect()` 会跳过现实仿生记忆反思。
- `/memory audit` 通过 `get_active_memories()` 扫描疑似临场剧情污染的 active 仿生记忆，用户点击“标记遗忘”后由 `mark_user_memories_forgotten()` 只处理当前用户对应记忆。
- 当问题明确是在追问昨天/前天聊了什么时，`context_assembler.py` 会优先调用 `sqlite_history_repo.get_history_by_day_offset()` 注入原始对话片段，而不是只靠抽象仿生记忆。
- `memory_reflection_service.py` 会把反思分为 `shared_experience / user_fact / relationship_moment / assistant_private_claim / ephemeral`：用户明确参与的共同经历会提高重要度并保留，只来自Companion回复的明星客户、私人行程等临场剧情不会写入可检索仿生记忆。
- 真正的聊天物理删除只通过 `sqlite_history_repo.delete_chat_history()` 发生，并由 `application/reset_service.clear_user_history()` 调用；`/reset` 与 `/clear` 的数据后果已经明确分离。

## 五、不要混淆的两类 Prompt

- `.prompts/`
  开发协作用提示词，不参与运行时对话。
- `data/prompts/prompt_template.txt`
  运行时人格提示词模板，`prompt_builder.py` 会热加载它。

## 六、建议搭配阅读

- 总览先看 [ARCHITECTURE.md](ARCHITECTURE.md)
- 实际读代码按 [READING_ORDER.md](READING_ORDER.md)
- 查本地未发布变更看 [CHANGELOG.md](CHANGELOG.md)
