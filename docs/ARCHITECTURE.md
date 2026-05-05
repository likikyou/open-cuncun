# Feishu AI Companion 架构

> 最后整理：2026-04-23
> 当前仓库状态：V5.7.1 (2026-04-08) + Unreleased，见 [CHANGELOG.md](CHANGELOG.md)。

## 一、当前判断

当前项目已经从“高耦合大文件单体”收敛到“主链 compat 已清空的模块化单体”：

- 新分层目录已经落地：`application / domain / infrastructure / presentation`
- 根目录旧 facade 已清空，主链直接落到 `entrypoints / application / presentation`
- Phase 8 已把飞书卡片 JSON、卡片主图资源和展示文案格式化收口到 `presentation`
- `app/main.py` 现在只保留薄 Flask 入口；启动初始化和 webhook 处理已分别下沉到 `app/bootstrap.py` 与 `app/entrypoints/feishu_webhook.py`

这意味着当前代码阅读策略应该是：

1. 先看运行入口，确认请求从哪里进来
2. 再顺着入口进入真实应用服务
3. 最后进入基础设施实现

## 二、实际分层图

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ 用户层                                                                   │
│ 飞书客户端：文本 / 图片 / sticker / 卡片按钮 / 命令                       │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 运行入口                                                                  │
│ app/main.py + app/bootstrap.py + app/entrypoints/feishu_webhook.py        │
│ - main.py: 暴露 create_app/get_app、懒加载 app 单例、/health、/presence   │
│ - bootstrap.py: 启动初始化、资产预热、开发模式 scheduler 线程             │
│ - feishu_webhook.py: challenge / 解密 / 验签 / 去重 / 异步投递            │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌─────────────────────────┐
│ presentation         │ │ application          │ │ domain                  │
│ - feishu_event_parser│ │ - chat_orchestrator  │ │ - reply_mode            │
│ - cards.builders     │ │ - command_service    │ │ - context_policy        │
│ - cards.assets       │ │ - observation_service│ │ - observation_rules     │
│ - formatters.*       │ │ - observation_media  │ │ - memory_rules          │
│                      │ │ - reply_service      │ │                         │
│                      │ │ - reset_service      │ │                         │
│                      │ │ - memory_*_service   │ │                         │
│                      │ │ - reminder/proactive  │ │                         │
└──────────────────────┘ └──────────────────────┘ └─────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ infrastructure                                                            │
│ - ai/provider_registry + provider_health + fallback_gateway               │
│ - feishu/client / messenger / media_store / card_streamer                 │
│ - persistence/sqlite_*_repo                                               │
│ - vector/chroma_*                                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

## 三、当前真实调用链

### 1. 飞书消息主链

```text
POST /  (app.main.feishu_handler)
  -> app.entrypoints.feishu_webhook.handle_feishu_webhook()
     -> security.AESCipher / verify_signature
     -> encrypted payload 必须解密为非空 JSON object，否则返回 400
     -> processed_ids 去重
     -> executor.submit(app.application.chat_orchestrator.core_logic, data)
        -> app.presentation.parsers.feishu_event_parser.parse_message
        -> 命令: app.application.command_service.handle_command
        -> 普通对话:
           -> get_active_conversation()
           -> get_recent_history()
           -> save_message(user)
           -> app.application.reply_service.generate_reply
              -> 纯当前时间问句: tools_registry.build_current_time_reply()
                 -> infrastructure.feishu.send_feishu(text)
              -> 普通对话:
                 -> prompt_builder.build_prompt()
                 -> ai_engine.call_ai_stream()
                 -> application.context_assembler.build_messages()
                 -> domain.reply_mode / domain.context_policy
                 -> infrastructure.feishu.card_streamer.stream_reply()
                 -> ai_engine.call_ai_summarize()
           -> save_message(assistant)
           -> post_reply_jobs.async_reflect()  # 剧情对话会跳过现实仿生记忆反思
           -> post_reply_jobs.async_voice_reply()
```

### 2. 观察与只读状态链

```text
GET /presence  (app.main.presence_endpoint)
  -> 校验 PRESENCE_AUTH_TOKEN
  -> application.observation_service.build_presence_payload()
     -> get_or_create_observation_snapshot()
        -> persistence.sqlite_observation_repo.get_presence_snapshot()
        -> persistence.sqlite_observation_repo.get_presence_runtime_state()
        -> domain.observation_rules.build_observation_context()
        -> weather.get_weather()
        -> sqlite_memory_repo.get_bionic_state() / get_active_memories()
        -> sqlite_history_repo.get_last_interaction_time() / get_recent_history()
        -> call_low_cost_ai() 渲染 observation_text
        -> persistence.sqlite_observation_repo.save_presence_snapshot()

/observe
  -> app.application.command_service.handle_command()
     -> _handle_observe_command()
        -> application.observation_service.get_observation_text()
        -> infrastructure.feishu.messenger.send_feishu(text)

未来媒体任务
  -> application.observation_media_service.build_observation_media_task()
     -> 写入 media_status=pending
     -> 复用 presence_snapshot.media_prompt
     -> 写入 media_rendering runtime_state
  -> application.observation_media_service.complete_observation_media_task()
     -> 写回 ready/failed 与 media_key
     -> 清理 media_rendering runtime_state
```

### 3. 卡片与命令链

```text
card.action.trigger
  -> feishu_event_parser.parse_message()
  -> set_reply_mode / set_pure_mode / set_ai_provider / confirm_reset /
     confirm_clear_context / run_command
  -> application.command_service.handle_command()
     -> /observe 返回实时观察文字
  -> presentation.cards.builders.*
     -> /chat 多重对话控制台
     -> /story 剧情模式控制台
     -> /memory audit 记忆审核控制台
  -> infrastructure.feishu.messenger.send_interactive_card()
```

### 4. 调度链

```text
开发模式:
run.py
  -> app.main.start_app()
     -> app.bootstrap.start_app(get_app)
        -> initialize_runtime(preload_card_images_enabled=True)
        -> start_scheduler_thread()
        -> get_app()
        -> app.run(...)

生产模式:
pm2 -> gunicorn wsgi:app  (--interpreter none)
  -> wsgi.py
     -> app.bootstrap.initialize_runtime(preload_card_images_enabled=True)
     -> app.main.get_app()

pm2 -> python run_scheduler.py
  -> run_scheduler.py
     -> app.bootstrap.initialize_runtime(preload_card_images_enabled=False)
     -> app.entrypoints.scheduler_runner.run_scheduler()

app.entrypoints.scheduler_runner.run_scheduler
  -> run_scheduler_loop()
     -> reminder_service.morning_greeting()
     -> reminder_service.night_reminder()
     -> reminder_service.brush_teeth_reminder()
     -> memory_maintenance_service.consolidate_memories()
     -> memory_maintenance_service.decay_and_forget()
     -> proactive_chat_service.proactive_thought_task()
```

## 四、目录与职责速查

| 路径 | 当前状态 | 主要职责 |
|:---|:---|:---|
| `run.py` | 开发入口 | 开发模式一键启动：运行时初始化 + 进程内 scheduler + Flask 内建服务器 |
| `wsgi.py` | 生产 Web 入口 | 生产模式给 Gunicorn 加载的 WSGI 入口 |
| `run_scheduler.py` | 生产 scheduler 入口 | 生产模式独立 scheduler 进程入口 |
| `app/main.py` | 薄入口/兼容导出 | 暴露 `create_app()`、`get_app()`、懒加载 canonical app 单例、`/health`、`/presence`、路由与 `start_app()` |
| `app/bootstrap.py` | 真实实现 | 运行时初始化、资产预热、运行时资产检查与开发模式 scheduler 线程启动 |
| `app/entrypoints/feishu_webhook.py` | 真实实现 | 飞书 webhook 解密、challenge、验签、去重与异步投递 |
| `app/entrypoints/scheduler_runner.py` | 真实实现 | scheduler 真实入口、任务注册与 pending loop |
| `app/presentation/parsers/feishu_event_parser.py` | 真实实现 | 解析文本、图片、sticker、卡片回调为内部事件 |
| `app/presentation/cards/builders.py` | 真实实现 | 所有飞书命令卡片 JSON 构建 |
| `app/presentation/cards/assets.py` | 真实实现 | 卡片主图查找、缓存、预热；上传策略可注入 |
| `app/presentation/formatters/*.py` | 真实实现 | 卡片文案与展示字段格式化 |
| `app/application/chat_orchestrator.py` | 真实实现 | 普通对话主编排、同用户串行化、保存顺序、后台任务触发 |
| `app/application/command_service.py` | 真实实现 | `/status /observe /reply /pure /model /memory /memory audit /chat /story /reset /clear /help` |
| `app/application/observation_service.py` | 真实实现 | 观察快照编排、显式运行时状态管理、缓存复用、第三人称文字渲染与 `/presence` 载荷构建 |
| `app/application/observation_media_service.py` | 占位实现 | 未来图片/GIF/视频 worker 的任务状态骨架；当前只归一媒体类型、写入 `pending/ready/failed`、复用 `media_prompt` 与清理 `media_rendering` |
| `app/application/reply_service.py` | 真实实现 | prompt、AI 流式回复、卡片准备、摘要提炼；纯当前时间问句直接走普通文本快路径 |
| `app/application/context_assembler.py` | 真实实现 | 按策略并发检索并组装上下文；回忆问题优先注入真实对话回看 |
| `app/application/reset_service.py` | 真实实现 | 决定 reset/clear 的真实边界：`/clear` 只切上下文，`/reset` 才删聊天与记忆 |
| `app/application/memory_reflection_service.py` | 真实实现 | 反思提炼、scope 过滤、向量写入、运行时状态更新、仿生记忆检索；低成本 AI 调用会回写 provider 成功/失败状态 |
| `app/application/memory_maintenance_service.py` | 真实实现 | 记忆整合、遗忘与向量清理 |
| `app/application/reminder_service.py` | 真实实现 | 定时提醒文案生成、发送与语音透传 |
| `app/application/proactive_chat_service.py` | 真实实现 | 主动消息判断、清洗、发送 |
| `app/ai_engine.py` | 真实实现 | AI 主链编排、工具调用、fallback 边界与运行事件记录 |
| `app/infrastructure/ai/provider_registry.py` | 真实实现 | provider 选择链解析、用户级模型偏好与熔断跳过 |
| `app/infrastructure/ai/provider_health.py` | 真实实现 | provider 熔断状态机、半开探测与 `/health.ai_circuit` 摘要 |
| `app/infrastructure/ai/fallback_gateway.py` | 真实实现 | 统一 fallback 执行；主链已失败时可跳过重复主 provider 调用 |
| `app/observability.py` | 真实实现 | 统一记录运行时降级事件与 AI 运行事件，并为 `/health` 提供最近窗口聚合 |
| `app/domain/query_intent.py` | 真实实现 | 回忆追问识别、相对日期提取、短跟问继承、私人生活问句识别与默认天气地点归一 |
| `app/domain/reply_mode.py` | 真实实现 | `light/normal/qa` 规则与 heuristics |
| `app/domain/context_policy.py` | 真实实现 | `pure_mode`、检索开关、上下文块限额 |
| `app/domain/observation_rules.py` | 真实实现 | 实时观察的时间槽位、稳定 seed 与意外规则 |
| `app/domain/memory_rules.py` | 真实实现 | importance、retention、relationship/mood 规则 |

## 五、数据与边界

### 1. SQLite / Chroma 边界

```text
application.reset_service
  -> persistence.sqlite_history_repo / sqlite_memory_repo / sqlite_profile_repo
  -> vector.chroma_memory_store
```

当前边界已经收口为：

- sqlite repo 只负责表读写与本地缓存失效
- 向量删除由 `application/reset_service` 决定是否触发
- 数据库 facade 已删除，持久化读写直接落到 `persistence/sqlite_*_repo.py` 与 `application/reset_service.py`
- `conversations` 表保存同一飞书私聊里的多重对话元数据，包含 `mode`、`summary` 等字段；`user_settings.active_conversation_id` 决定当前激活对话
- `chat_history.conversation_id` 是聊天上下文隔离边界；旧历史会自动迁入 `default:<open_id>` 默认对话
- `/clear` 不再物理删除 `chat_history`；`sqlite_history_repo` 会把当前最大消息 ID 写入 `user_settings.chat_context_after_id`，后续上下文读取只取这个边界之后的新消息
- 多重对话下，`/clear` 的上下文边界会按当前 `conversation_id` 存成 `chat_context_after_id:<conversation_id>`，不会影响其他对话
- `sqlite_history_repo.get_history_by_day_offset()` 会按本地日期换算 UTC 边界，供“昨天/前天聊了什么”这类问题优先读取原始聊天片段
- `/reset` 仍会通过 `delete_chat_history()` 删除聊天记录，并继续清理仿生记忆、画像关系层和对应向量
- `presence_snapshot` 表保存实时观察共享快照；`/observe` 与 `/presence` 都只消费这一份状态，并提前预留 `media_type / media_status / media_prompt / media_key`
- `presence_runtime_state` 表保存 observation 的短时显式状态，如 `replying / media_rendering / reflecting / proactive / reminder`；状态切换时会主动让缓存 snapshot 过期

### 2. 记忆链路

```text
对话结束
  -> post_reply_jobs.async_reflect
     -> 如果当前 conversation.mode == story，直接跳过现实仿生记忆反思
  -> application.memory_reflection_service.reflect_on_conversation
     -> 低成本 LLM 提炼 JSON
        -> provider_health.record_provider_success/failure
     -> domain.memory_rules 判断 shared_experience / assistant_private_claim
     -> sqlite_memory_repo.save_bionic_memory
     -> retrieval.bio_collection.add
     -> domain.memory_rules 更新心情/关系阶段

记忆审核
  -> application.command_service._handle_memory_command("/memory audit")
     -> sqlite_memory_repo.get_active_memories
     -> domain.memory_rules.should_include_memory_in_context 反向筛出疑似污染候选
     -> presentation.cards.builders.build_memory_audit_card
     -> 点击“标记遗忘”
        -> sqlite_memory_repo.mark_user_memories_forgotten

定时任务
  -> application.memory_maintenance_service.consolidate_memories
  -> application.memory_maintenance_service.decay_and_forget
```

### 3. 回复链路

```text
application.reply_service.generate_reply
  -> 纯当前时间问句
     -> build_current_time_reply
     -> send_feishu(text)
  -> 其他对话
     -> get_user_setting(reply_mode)
     -> prompt_builder.build_prompt
     -> ai_engine.call_ai_stream
     -> application.context_assembler.build_messages
        -> domain.reply_mode / context_policy
     -> infrastructure.feishu.card_streamer
     -> ai_engine.call_ai_summarize
```

### 4. 实时观察链路

```text
application.observation_service.get_or_create_observation_snapshot
  -> sqlite_observation_repo.get_presence_snapshot
  -> sqlite_observation_repo.get_presence_runtime_state
  -> domain.observation_rules.build_observation_context
  -> weather.get_weather
  -> sqlite_memory_repo.get_bionic_state / get_active_memories
  -> sqlite_history_repo.get_last_interaction_time / get_recent_history
  -> memory_reflection_service.call_low_cost_ai
  -> sqlite_observation_repo.save_presence_snapshot

application.observation_service.get_observation_text
  -> /observe 文字返回

application.observation_service.build_presence_payload
  -> /presence JSON 返回

application.observation_media_service.build_observation_media_task
  -> media_type 归一
  -> presence_runtime_state 写入 media_rendering
  -> presence_snapshot 写入 media_status=pending

application.observation_media_service.complete_observation_media_task
  -> presence_snapshot 写回 ready/failed 与 media_key
  -> presence_runtime_state 按 token 清理
```

## 六、历史 compat 映射表

| 已删除旧入口 | 当前真实实现 |
|:---|:---|
| `app.message_handler.parse_message()` | `app.presentation.parsers.feishu_event_parser.parse_message()` |
| `app.message_handler.core_logic()` | `app.application.chat_orchestrator.core_logic()` |
| `app.message_handler.handle_command()` | `app.application.command_service.handle_command()` |

## 七、当前仍需注意的真实情况

- `app/main.py` 仍是 Flask app 所在模块，但现在通过 `get_app()` 懒加载 canonical 单例；生产和开发入口都不再额外创建第二个 Flask 实例。
- `app/entrypoints/scheduler_runner.py` 现在直接承接 scheduler 入口；`reply_service.py` 和 `card_streamer.py` 也已经直接承接回复生成与流式输出。
- `app/entrypoints/feishu_webhook.py` 现在把非法 JSON、坏密文和解密后空对象都视为协议错误返回 `400`，不再静默吞掉或继续进入 challenge/event 解析。
- `app/ai_engine.py` 现在会记录 AI 主链的请求开始、首包、工具批次、完成与 fallback 阶段事件；`app/observability.py` 负责统一缓冲这些 AI 运行事件以及 AI fallback、上下文检索、联网搜索、语音匹配等降级事件；`ops.check_health()` 再把它们汇总进 `/health`。
- `app/infrastructure/ai/provider_registry.py`、`provider_health.py` 和 `fallback_gateway.py` 现在把 AI provider 选择拆成三层：registry 先结合用户偏好和熔断状态决定当前 provider，health 模块维护失败窗口、打开时长和半开探测，fallback 网关在主链已经失败时会直接跳过主 provider，避免同一轮再等一次超时。
- `run.py` 现在只服务开发模式；生产入口已经拆成 `wsgi.py` 和 `run_scheduler.py` 两个独立进程，避免 Web worker 和定时任务继续绑在同一个启动函数里。
- 当前时间问句在 `reply_service.py` 内直接发送普通文本，不再准备流式卡片或走 AI 摘要链路。
- `memory_reflection_service.py` / `memory_maintenance_service.py` / reminder 链路共用的低成本 AI 入口现在会回写 provider success/failure，半开探测不会再卡死在 `probe_in_flight=True`。
- `app/application/reset_service.py` 和 `sqlite_history_repo.py` 现在把“清空上下文”和“删除聊天记录”拆成两条链：`/clear` 只移动上下文边界，`/reset` 才做真实删除。
- `sqlite_conversation_repo.py`、`sqlite_history_repo.py` 和 `_sqlite_common.py` 现在承接同一飞书私聊里的多重对话：默认对话、当前激活对话、按 `conversation_id` 隔离的历史读取与上下文边界都在 SQLite 层持久化。
- `app/application/observation_service.py` 当前独立于主聊天 prompt：它优先复用 `presence_snapshot`，只有缓存过期或强制刷新时才重新拉天气、情绪、最近聊天和低成本 AI 渲染文字。
- `replying / media_rendering / reflecting / proactive / reminder` 现在会通过 `presence_runtime_state` 短时写入 observation 状态源；`observation_service.py` 会优先读这些显式状态，低优先级状态不会覆盖更高优先级状态。
- `observation_media_service.py` 当前只是媒体任务占位骨架，不调用真实图片/GIF/视频 API；它为未来 worker 固定 `pending -> ready/failed` 的 snapshot 写回契约。
- `app/main.py` 的 `/presence` 只有配置 `PRESENCE_AUTH_TOKEN` 且请求头带 `Authorization: Bearer <token>` 或 `X-Presence-Token` 才会返回快照；若未显式传 `user_id`，当前实现会回退到 `ADMIN_OPEN_ID`。
- `/chat` 和 `/story` 现在都是飞书卡片二级控制台；卡片按钮可见文案使用中文动作名，真实 slash command 只放在按钮回调 value 中。
- 剧情模式绑定到独立对话：剧情设定只注入当前会话，不会写入现实仿生记忆；退出剧情会切回默认“日常聊天”。
- `/memory audit` 会扫描 active 仿生记忆中的疑似临场剧情污染，并通过用户限定的 `mark_user_memories_forgotten()` 逐条标记遗忘。
- `domain/query_intent.py` 会把“你今天休息吗/给哪些明星化妆/私人行程”这类关系内问题从普通 QA 里剥离出来，避免 `knowledge/web` 把外部新闻污染成Companion自己的经历；天气问句无明确地点时默认查询“默认城市”。
- `memory_reflection_service.py` 不再把只来自Companion回复的明星客户、私人行程等临场剧情写入可检索仿生记忆；用户明确参与的共同吃饭、一起玩、约会、见面等经历会作为 `shared_experience` 提高重要度并保留。
- AI、Feishu、memory、context、database、streaming、scheduler 与 message handler 的外围 facade 已全部清空。
- `prompt_builder.py`、`ai_engine.py`、`retrieval.py`、`voice_matcher.py` 与 `observability.py` 仍是稳定底座，当前没有再做大拆。
- `.prompts/` 下的是开发协作提示词；运行时人格提示词仍在 `data/prompts/prompt_template.txt`。

## 八、依赖方向护栏

当前仓库不是“为了分层而分层”的理想化架构，护栏只约束已经跑通、并且对理解项目真正有帮助的边界。

- 入口层：`app/main.py`、`app/bootstrap.py`、`app/entrypoints/*` 负责 Flask、启动初始化、调度线程和 webhook 协议处理。
- 应用层：`app/application/*` 可以依赖 `domain / infrastructure / presentation` 和稳定底座模块，但不允许反向 import `app.main`、`app.bootstrap`、`app.entrypoints/*`。
- 展示层：`app/presentation/*` 负责飞书事件解析、卡片 JSON 和展示格式化；可以调用基础设施与稳定工具，但不承接主业务编排。
- 规则层：`app/domain/*` 只放纯规则，禁止依赖 `application / presentation / infrastructure / main / bootstrap / entrypoints`。
- 历史 facade：`ai_client / feishu_api / bionic_memory / context_builder / database / streaming / scheduler / message_handler` 都已经退场，只保留历史映射，不应重新出现 import。

这些规则已经同步进入 [scripts/verify.py](../scripts/verify.py) 的架构守卫检查里；以后优先让脚本拦住结构回退，而不是靠人脑记住。

## 九、建议阅读顺序

详细顺序见 [READING_ORDER.md](READING_ORDER.md)。如果只读一条链：

1. `app/main.py`
2. `app/entrypoints/feishu_webhook.py`
3. `app/application/chat_orchestrator.py`
4. `app/presentation/parsers/feishu_event_parser.py`
5. `app/application/command_service.py`
6. `app/application/reply_service.py`
7. `app/application/context_assembler.py`
8. `app/infrastructure/feishu/card_streamer.py`
