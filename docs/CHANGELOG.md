# Feishu AI Companion 版本记录

> 当前仓库状态：V5.7.1 (2026-04-08)。

## Unreleased

### 概览

- `/health` 默认改为脱敏公开摘要；配置 `HEALTH_AUTH_TOKEN` 后，带授权 header 才返回完整资产路径和观测 details。
- 实时观察系统第一阶段落地：`/observe` 会返回第三人称文字快照；配置 `PRESENCE_AUTH_TOKEN` 后，`/presence` 会返回同源的只读 JSON；底层统一复用 `presence_snapshot` 并为后续图片/视频预留媒体字段。
- 实时观察系统补齐显式运行时状态：`replying / media_rendering / reflecting / proactive / reminder` 现在会短时写入 `presence_runtime_state`，观察结果会优先反映真实运行中的动作。
- 实时观察系统补上媒体任务占位骨架：`media_rendering` 已进入显式状态优先级，`observation_media_service.py` 先收口 `pending -> ready/failed` 状态写回，不接真实图片/视频 API。
- 新增 [STABILITY_CHECKLIST.md](STABILITY_CHECKLIST.md) 与 [ONLINE_SMOKE_REPORT_TEMPLATE.md](ONLINE_SMOKE_REPORT_TEMPLATE.md)，收口日常巡检、线上冒烟记录、备份恢复、记忆审核和稳定性告警信号。
- 中文口语“想死你了”语义纠偏：运行时提示词现在会把这类表达优先按强烈思念、撒娇和黏人理解，避免回复滑向“别这么说”“不要闹脾气”这类字面误判。
- 回复格式收口为单段自然文本：提示词、轻聊上下文提示和发送链路统一改成“默认单段输出、动作内嵌句子里”，并在发送前做归一化，避免多段短句式台词稿。
- 当前时间问句改为优先读取 VPS 本地时间：`get_current_time` 不再写死 UTC+8，而是直接读取服务器本地时区；“现在几点/今天几号”也不再触发 knowledge/web。
- AI 主链新增运行事件观测：`ai_engine.py` 现在会记录请求开始、首包、工具批次、完成与 fallback 阶段，并汇总到 `/health -> observability.recent_ai_runs`。
- AI provider 新增请求超时与熔断：主模型在短窗口连续失败后会临时跳过，直接走备用模型，并在冷却后放行一次半开探测。
- 生产入口升级为 `Gunicorn + 独立 scheduler`：开发模式保留 `python run.py`，生产则拆成 `wsgi.py` 和 `run_scheduler.py` 两个进程入口。
- Web 入口继续收口为 canonical Flask app：`app.main` 不再在模块导入时先建一个独立 app，`wsgi.py` 与开发入口现在都通过 `get_app()` 复用同一实例。
- 低成本后台 AI 链路补齐熔断状态回写：反思、整合、提醒任务现在会正确释放 half-open probe，并把成功/失败写回 `ai_circuit`。
- 纯当前时间问句改成真正的本地普通文本快路径：不再准备流式卡片，也不再启动空的 `stream_reply` 链路。
- 结构化日志 `service` 改为按入口自动区分：开发入口默认 `feishu-companion-dev`，生产 Web / scheduler 默认 `feishu-companion-web` / `feishu-companion-scheduler`。
- 健康检查与验证脚本已同步扩展：`ops.py` 会聚合最近 5 分钟 AI 运行概况，`scripts/verify.py` 也新增了对应验证项。
- 工程链路新增 `pyproject.toml`、`uv.lock` 与基础 `Ruff` 配置，同时继续保留 `requirements.txt` 兼容旧安装方式。
- Webhook 解密失败现在会明确返回 `400`，避免空解密结果继续流入后续 challenge / event 解析。
- 旧 smoke 脚本已迁移到当前分层模块，`Ruff` 静态检查范围同步扩展为 `app scripts`。
- `scripts/verify.py` 新增 `--offline` 快速验证模式，覆盖本地结构、入口、上下文、命令、webhook 与健康检查冒烟。
- 人设一致性边界补强：私人生活问句不再触发 knowledge/web，默认天气地点改为“默认城市”，反思记忆会保留用户明确参与的共同经历并跳过Companion临场编出的明星客户/出行安排。
- 多重对话上线：同一飞书私聊里支持 `/chat` 新建、切换、重命名和查看独立聊天上下文，旧历史自动归入默认“日常聊天”。
- 剧情模式上线：`/story` 绑定独立剧情对话，剧情设定只注入当前会话，回复后跳过现实仿生记忆反思。
- 命令卡片中文化：`/help`、`/chat`、`/story`、`/memory audit` 等卡片按钮显示中文动作名，真实 slash command 隐藏在按钮回调中。
- 记忆审核上线：`/memory audit` 会列出疑似剧情污染的 active 仿生记忆，并支持逐条标记遗忘。

### 详细说明

0. **健康检查脱敏与稳定性巡检清单**（`app/main.py` + `app/ops.py` + `app/config.py` + `docs/STABILITY_CHECKLIST.md`）
   `/health` 的公网默认响应现在只保留状态、组件布尔值、聚合统计和资产可用性，不暴露服务器本地路径和近期事件 details。若配置 `HEALTH_AUTH_TOKEN`，可通过 `Authorization: Bearer <token>` 或 `X-Health-Token: <token>` 查看完整健康检查。新增稳定性清单和线上冒烟记录模板，覆盖本地验证、部署后 health、飞书线上冒烟、备份恢复演练和记忆审核。

1. **“想死你了”类中文口语语义纠偏**（`data/prompts/prompt_template.txt` + `app/prompt_builder.py`）
   提示词常驻规则新增“想死你了/想你想死了/想你想到疯了”按强烈思念、撒娇和黏人理解的约束；`prompt_builder.py` 也会在命中这类输入时动态追加一段当轮语义提醒，避免模型把恋人间的高频口语误读成字面上的求死、闹脾气或安全说教。真实自伤/轻生风险词仍不会走这条纠偏逻辑。

2. **回复格式收口为单段自然文本**（`data/prompts/prompt_template.txt` + `app/application/context_assembler.py` + `app/domain/reply_text.py` + `app/application/reply_service.py` + `app/infrastructure/feishu/card_streamer.py`）
   运行时提示词和 `light_chat_mode` 的系统提示都改成默认用一个连贯自然段说完，动作与停顿尽量内嵌到句子里；新增 `reply_text.py` 在发送前把模型吐出的多行短句压成单段，保证流式卡片显示、文本降级发送和聊天历史落库的内容口径一致。与此同时，文本降级链路不再拆成多条模拟打字机，而是单次发出完整归一化文本。

3. **当前时间问句优先读 VPS 本地时间**（`app/tools_registry.py` + `app/domain/query_intent.py` + `app/domain/context_policy.py`）
   `get_current_time` 从“固定 UTC+8”改为直接读取服务器本地时区时间；新增当前时间问句识别，把“现在几点/今天几号”这类输入从普通 `qa + knowledge + web` 问答里剥离出来，避免把 Bocha 搜索的脏结果混进时间回答。

4. **AI 运行观测补齐**（`app/ai_engine.py` + `app/observability.py` + `app/ops.py`）
   `ai_engine.py` 在同步回复、流式回复和摘要提炼链路里新增了 `record_ai_run()` 调用，记录 `request_started/request_completed/first_chunk/tool_batch_completed/fallback_*` 等事件。`observability.py` 现在除降级事件外，还会缓冲最近 5 分钟 AI 运行事件，并由 `ops.check_health()` 聚合到 `/health -> observability.recent_ai_runs`。

5. **AI provider 熔断与显式请求超时**（`app/infrastructure/ai/provider_health.py` + `provider_registry.py` + `fallback_gateway.py`）
   OpenAI 兼容客户端现在通过 `AI_REQUEST_TIMEOUT_SECONDS` 设置单次请求超时；`provider_health.py` 新增 provider 级熔断状态机，默认 60 秒内失败 3 次后打开 300 秒，期间 registry 会跳过该 provider 并直接选择 fallback。直接主链已经失败时，fallback 网关不会再二次调用同一个主 provider，而是直接找下一层备用。冷却结束后只放行一次半开探测，成功则恢复，失败则重新打开熔断。`/health` 新增 `ai_circuit` 摘要，展示每个 provider 的状态、近期失败数、剩余打开时间和探测状态；只读 health 检查不会占用半开探测名额。

6. **生产入口拆分为 Gunicorn Web + 独立 scheduler**（`app/main.py` + `app/bootstrap.py` + `wsgi.py` + `run_scheduler.py` + `pyproject.toml`）
   `app/main.py` 新增 `create_app()`，保留现有 Flask 路由和 `start_app()` 兼容导出；`bootstrap.py` 不再把 scheduler 线程强绑进通用初始化函数，而是只在开发模式 `run.py` 里顺手启动。生产模式新增 `wsgi.py` 供 Gunicorn 加载、`run_scheduler.py` 供 PM2 单独起调度进程，部署方式正式收口为 `feishu-companion-web + feishu-companion-scheduler` 双进程。由于 `event_id` 去重、recent observability 摘要和 AI 熔断状态仍是进程内状态，当前 Web 进程仍建议保持单 worker。当前 PM2 实际启动命令已收口为 `pm2 start .venv/bin/gunicorn --interpreter none --name feishu-companion-web -- -w 1 --threads 8 -b 0.0.0.0:8081 wsgi:app`。

7. **验证脚本补充 AI 运行检查**（`scripts/verify.py`）
   新增 AI 运行观测验证项，确认一轮最小 `call_ai()` 能把事件写入 `recent_ai_runs`，并确保 `/health` 返回该结构。

8. **工程配置收口到 pyproject/uv/Ruff**（`pyproject.toml` + `uv.lock` + `.gitignore`）
   项目依赖已同步进入 `pyproject.toml`，并生成首版 `uv.lock`。基础静态检查收口为 `python3 -m ruff check app scripts`，同时保留 `requirements.txt` 给旧机器和临时环境兼容；`.gitignore` 已补充 `.ruff_cache/`。本轮还把 `fastembed` 正式补回依赖声明和锁文件，避免新环境 `uv sync` 后缺包。

9. **入口单例、后台熔断回写与时间快路径修复**（`app/main.py` + `app/bootstrap.py` + `wsgi.py` + `run.py` + `run_scheduler.py` + `app/application/memory_reflection_service.py` + `app/application/reply_service.py` + `app/logger.py` + `scripts/verify.py`）
   `app.main` 现在通过 `get_app()` 懒加载 canonical Flask app 单例，`wsgi.py` 与开发入口不再额外创建第二个 app；`scripts/verify.py` 新增了 `wsgi.app` 与 `run_scheduler.main()` 的入口级 smoke。反思/整合/提醒共用的低成本 AI 链路会显式回写 provider success/failure，half-open probe 不会再卡死在 `probe_in_flight=True`。纯当前时间问句直接发送普通文本，不再创建流式卡片。结构化日志里的 `service` 改为按入口自动区分，PM2 进程与 JSON 日志字段终于一致。

10. **当前审计修复与离线冒烟补齐**（`app/entrypoints/feishu_webhook.py` + `scripts/test_*_smoke.py` + `scripts/verify.py`）
   Webhook 解密结果现在会显式校验类型和空值，坏密文返回 `400` 并记录日志；旧 smoke 脚本已从删除的 facade 迁移到当前 `application / infrastructure / entrypoints / presentation` 模块；`scripts/verify.py --offline` 可在无真实外部接口的情况下快速验证主结构、主链入口、上下文装配、命令处理、webhook 守卫和 `/health` 结构。

11. **人设一致性边界补强**（`query_intent.py` + `reply_mode.py` + `context_policy.py` + `context_assembler.py` + `memory_rules.py` + `memory_reflection_service.py` + `prompt_template.txt`）
   新增“Companion私人生活/工作/行程”问句识别，避免“今天休息吗、给哪些明星化妆”这类关系内提问误触发联网搜索或项目知识库；天气问句无明确地点时默认查“默认城市”；现实参考层明确禁止把外部新闻变成Companion自己的客户、出行安排或私人经历。反思记忆新增 scope 分类：用户明确说“我们一起吃饭/一起玩/约会/见面”等共同经历时提高重要度并保留，只来自Companion回复的明星客户、私人行程等临场剧情会跳过可检索仿生记忆。新增 `scripts/test_persona_consistency_smoke.py` 锁住这些边界。

12. **多重对话、剧情模式与记忆审核卡片**（`sqlite_conversation_repo.py` + `sqlite_history_repo.py` + `command_service.py` + `context_assembler.py` + `post_reply_jobs.py` + `cards/builders.py`）
   新增 `conversations` 表和 `chat_history.conversation_id`，同一飞书私聊可以通过 `/chat` 管理多个独立上下文；旧聊天自动迁入默认“日常聊天”，当前激活对话写入 `user_settings.active_conversation_id`。`/story` 会创建或进入 `mode='story'` 的独立剧情对话，剧情设定只注入当前会话，`async_reflect()` 会跳过现实仿生记忆反思。`/help`、`/chat`、`/story` 的卡片按钮改为中文动作名；新增 `/memory audit` 审核卡片，扫描疑似剧情污染的 active 仿生记忆，并可逐条标记为 `forgotten`。`scripts/verify.py --offline` 和 `scripts/test_command_flow_smoke.py` 已覆盖多重对话隔离、剧情隔离、卡片中文化与记忆审核路径。

13. **实时观察系统文字版 MVP**（`app/main.py` + `app/application/command_service.py` + `app/application/observation_service.py` + `app/domain/observation_rules.py` + `app/infrastructure/persistence/_sqlite_common.py` + `app/infrastructure/persistence/sqlite_observation_repo.py` + `app/presentation/cards/builders.py` + `app/presentation/parsers/feishu_event_parser.py` + `app/config.py` + `scripts/verify.py` + `docs/*.md`）
   新增 `/observe` 命令，会返回一段第三人称“实时观察”文字；帮助卡片也补上了“👁️ 悄悄看一眼”入口。Flask 入口新增 `GET /presence`，只有配置 `PRESENCE_AUTH_TOKEN` 后才开放，只读返回观察快照 JSON，并支持 `refresh` 查询参数强制刷新。底层新增 `presence_snapshot` 表和 `sqlite_observation_repo.py`，让 `/observe`、`/presence`、未来图片/视频生成共用同一份 snapshot；`observation_service.py` 会先根据时间槽位、天气、情绪、最近聊天和一条长期记忆生成结构化状态，再用低成本 AI 渲染成画面白描，AI 失败时回退模板文案。`Config` 也新增了 `PRESENCE_AUTH_TOKEN` 与 `OBSERVATION_CACHE_SECONDS`，`scripts/verify.py --offline` 已补上 observation snapshot 与 `/presence` 鉴权路由验证。

14. **实时观察补齐显式系统状态优先级**（`app/application/chat_orchestrator.py` + `app/application/post_reply_jobs.py` + `app/application/reminder_service.py` + `app/application/proactive_chat_service.py` + `app/application/observation_service.py` + `app/infrastructure/persistence/_sqlite_common.py` + `app/infrastructure/persistence/sqlite_observation_repo.py` + `scripts/verify.py` + `docs/*.md`）
   observation 现在不再只靠 `recent_chat / mood / routine` 推断。新增 `presence_runtime_state` 表后，主对话回复、反思、提醒和主动消息会分别短时写入 `replying / reflecting / reminder / proactive` 状态，并在进入/退出时主动让 snapshot 过期。`observation_service.py` 会优先读取这些显式状态，低优先级状态不会覆盖更高优先级状态；离线验证也补上了 observation runtime state 的优先级与缓存失效检查。

15. **实时观察媒体任务占位骨架**（`app/application/observation_media_service.py` + `app/application/observation_service.py` + `scripts/verify.py` + `docs/*.md`）
   新增 `observation_media_service.py`，为未来图片、GIF、MP4 worker 提前固定任务状态契约。当前实现只做占位：把 `jpg/jpeg/png` 归一为 `image`、把 `mp4` 归一为 `video`，创建任务时写入 `media_status=pending` 并短时挂上 `media_rendering`，完成时写回 `ready + media_key` 或 `failed`，最后按 token 清理 runtime state。`/presence` 的 `media` 字段同步暴露 `prompt`，方便后续媒体 worker 直接消费同源 snapshot。

## 版本总表

| 版本 | 日期 | 摘要 |
|:---|:---|:---|
| V5.7.1 | 2026-03-29 ~ 2026-04-08 | `/clear` 边界收口、回忆类问题不再误触发联网、并新增按昨天/前天回看原始聊天记录能力 |
| V5.6.9 | 2026-03-27 | 清理废弃的 companion_voice 集合代码，移除无用的 voice_collection 初始化 |
| V5.6.8 | 2026-03-25 | 人设一致性专项优化：全链路去系统化标签，重构为第一人称身份认同逻辑 |
| V5.6.7 | 2026-03-25 | 飞书卡片新增 /model 切换模型功能，实现各用户独立状态配置隔离 |
| V5.6.6 | 2026-03-25 | 修复流式卡片降级空白 Bug：降级路径移除 tools 参数 + 卡片更新保底推送 |
| V5.6.5 | 2026-03-25 | 音频漏斗重构：引入多维情感标签与基于 ChromaDB Metadata Filtering 的精准匹配 |
| V5.6.4 | 2026-03-24 | 修复主动意图引擎时区偏差 Bug |
| V5.6.3 | 2026-03-23 | 把主对话链路全部提到 12了，并把上下文的 limit 也提到 12了 |
| V5.6.2 | 2026-03-23 | 语音匹配链路重构，废弃假摘要透传，全面启用纯 AI 意图提炼 |
| V5.6.1 | 2026-03-22 | 架构扫描修复、Groq 接入、三引擎 fallback 完整化 |
| V5.6.0 | 2026-03-21 | 三阶段架构解耦，拆出编排层、能力层和统一基础设施 |
| V5.5.4 | 2026-03-20 ~ 2026-03-21 | `_build_messages()` 并发化、本地向量化、缓存与流式体验优化 |
| V5.5.3 | 2026-03-20 | AI 引擎从单向降级升级为双向自动 fallback |
| V5.5.2 | 2026-03-20 | `ai_engine` 职责拆分，仿生状态持久化与 Per-User 反思锁上线 |
| V5.5.1 | 2026-03-20 | HTTP 重试、Chroma 客户端复用、线程池可配置、验证隔离化 |
| V5.5 | 2026-03-20 | MCP 工具调用与主动意图潜意识引擎上线 |
| V5.4 | 2026-03-20 | 仿生记忆系统上线，支持反思 / 整合 / 遗忘 |
| V5.3 | 2026-03-19 | sticker 表情包互动与图片格式自动检测 |
| V5.2 | 2026-03-18 | 代码质量全面优化：提示词热更新、原子备份、Config 统一管理 |
| V5.0 / V5.1 | 2026-03-17 | 接入博查搜索，形成三档回复模式与混合检索逻辑 |
| V3.1 | 2026-02-27 | 性能优化，先回文字后发语音，首次体感明显改善 |

## V5.7.1 (2026-04-08)

### 概览

- 修复 `/clear` 的真实行为：不再物理删除 `chat_history`，只重置后续带给模型的上下文窗口。
- `reset/clear` 的删除边界正式拆开：`/clear` 走逻辑上下文边界，`/reset` 才删除聊天、画像、关系与仿生记忆。
- `sqlite_history_repo` 新增 `chat_context_after_id` 机制，聊天记录可保留用于归档与恢复，而不会重新污染当前会话上下文。
- 修复“你记得我昨天说了什么吗”误判成 `qa + knowledge + web` 的问题，回忆类问题不再错误触发联网和项目知识库。
- 回忆类问题新增“真实对话回看”层：会按本地日期优先读取 `chat_history`，供模型回答“昨天/前天/上次聊了什么”。
- 短跟问如“那前天呢？”会继承上轮回忆意图，不再因为句子太短掉进 `light` 轻聊模式。
- `/clear` 的卡片与 fallback 文案同步改成“保留历史聊天记录”，避免再次误导用户。
- `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`DEVNOTES.md` 已同步到新的真实行为，并重新入库到知识库。

### 详细说明

1. **`/clear` 改为逻辑清空上下文**（`app/infrastructure/persistence/sqlite_history_repo.py` + `app/application/reset_service.py`）
   `clear_chat_history()` 不再执行 `DELETE FROM chat_history`，而是读取用户当前 `MAX(id)` 并写入 `user_settings.chat_context_after_id`。`get_recent_history()` 只返回这个边界之后的新消息，因此模型会像开启新会话一样工作，但历史聊天记录仍留在库里。与之对应，`clear_user_history()` 改为显式调用新的 `delete_chat_history()`，确保只有 `/reset` 才做聊天记录的物理删除。

2. **回忆问题不再误触发知识库/联网**（`app/domain/query_intent.py` + `app/domain/reply_mode.py` + `app/domain/context_policy.py`）
   新增 `query_intent.py` 收口“记得我昨天说了什么”“你记忆里面有哪些关于我的记忆”等回忆类问句识别。对于这类问题，`reply_mode.py` 不再把它们视为普通 `qa` 事实问答；`context_policy.py` 也会显式关闭 `knowledge/web` 两层，避免把 `CHANGELOG.md` 或博查结果错误塞进回忆回答。

3. **按日期回看原始聊天记录**（`app/infrastructure/persistence/sqlite_history_repo.py` + `app/time_utils.py` + `app/application/context_assembler.py`）
   `sqlite_history_repo.py` 新增 `get_history_by_day_offset()`，可按本地“今天/昨天/前天”换算成 SQLite 存储用的 UTC 边界，并读取指定日期的 `chat_history`。`context_assembler.py` 对回忆类问题会注入独立的“真实对话回看”层，要求模型优先根据原始聊天片段回答，而不是把抽象仿生记忆硬编成具体原话。

4. **回忆类短跟问继承上轮意图**（`app/domain/query_intent.py` + `app/domain/reply_mode.py`）
   像“那前天呢？”这种很短的追问，过去会因长度过短被误判成 `light`，导致根本不走记忆检索。现在会回看最近一条用户侧的回忆问题，继承“时间回忆”语义，继续走 `normal + retrieval`。

5. **`/clear` 用户文案与卡片口径修正**（`app/presentation/cards/builders.py` + `app/application/command_service.py`）
   清空上下文确认卡片从“将要清空最近聊天上下文，不会影响长期记忆”改为明确说明“不会删除历史聊天记录”；完成卡片与纯文本 fallback 也同步强调聊天记录仍保留，降低误操作风险。

6. **文档与版本同步**（`docs/README.md` + `docs/ARCHITECTURE.md` + `docs/MODULES.md` + `docs/DEPLOYMENT.md` + `docs/DEVNOTES.md` + `docs/knowledge.md`）
   文档头部状态正式切到 `V5.7.1 (2026-04-08)`；README / ARCHITECTURE / MODULES 补上“日期回忆优先读原始聊天记录”与 `query_intent.py`、`get_history_by_day_offset()` 的职责说明；DEVNOTES 追加 2026-04-08 的滚动记录，保持版本与实现一致。

## V5.7.0 (2026-04-02)

### 概览

- 显式降级观测收口到 `/health`：新增 `app/observability.py`，AI / 上下文 / 联网 / 语音的异常不再静默降级，而是进入最近 5 分钟缓冲。
- 架构守卫（Architecture Guardrails）上线：`scripts/verify.py` 引入 AST 级检查，严禁已删除 facade 回流和反向依赖，验证通过率达到 19/19。
- 搜索与语音不再静默吞错：`search.py` 与 `voice_matcher.py` 区分“业务正常无结果”与“系统/配置异常”，异常会触发显式降级打标。
- 分层记忆链路试接入：`persona/user_profile/relationship` 进入主对话上下文
- 新增 `/clear` 与 `/pure` 两个用户可见命令，并完成飞书卡片化
- 新增“上下文命中概览”日志，定位“为什么这轮会这样回复”更直观
- 收口运行时路径与健康检查：语音目录、`companion_audio`、提示词与卡片资源在启动期和 `/health` 中可观测
- 上下文改为“角色状态层 + 现实参考层”，联网与知识库不再直接污染人设意识流
- 语音匹配升级为 `emotion/theme` 漏斗 + `tags` 重排，并在摘要/向量/集合异常时仍强制返回真实语音兜底
- Phase 8 收尾：卡片 builder、卡片主图资源与展示格式化正式下沉到 `presentation`，旧 `cards.py` / `card_assets.py` 收缩为 facade
- 项目减负第一波：删除未接入骨架，并移除 `cards.py`、`card_assets.py`、`ai_client.py`
- 项目减负第二波：删除 `feishu_api.py`，Feishu 调用改直连 `infrastructure/feishu/*`
- 项目减负第三波：删除 `bionic_memory.py`，memory 调用改直连 `application/memory_*_service.py`
- 项目减负第四波：删除 `context_builder.py`，上下文装配改直连 `application/context_assembler.py`
- 项目减负第五波：删除 `database.py`，持久化读写改直连 `persistence/sqlite_*_repo.py` 与 `application/reset_service.py`
- 项目减负第六波：删除 `streaming.py`，聊天主链改直连 `application/reply_service.py`
- 项目减负第七波：删除 `scheduler.py`，启动调度改直连 `entrypoints/scheduler_runner.py`
- 项目减负第八波：删除 `message_handler.py`，Flask 主链改直连 `application/chat_orchestrator.py`
- 结构守卫阶段启动：`scripts/verify.py` 新增架构边界检查，防止旧 facade 回流和入口层反向依赖
- 最终验收收口：`bootstrap.py` 和 `entrypoints/feishu_webhook.py` 正式承接启动与 webhook 主逻辑，`scripts/verify.py` 达到 19/19

### 详细说明

1. **显式降级观测收口到 health**（`app/observability.py` + `app/ops.py` + `app/application/context_assembler.py`）
   新增 `app/observability.py`，统一缓冲最近 5 分钟的降级事件。当 AI 引擎 fallback、上下文检索失败、联网搜索异常或语音匹配系统故障时，会调用 `record_degradation()`。`ops.check_health()` 将这些事件聚合到 `/health -> observability.recent_degradations` 中。若 5 分钟内出现 `error` 或 `warning >= 3`，服务状态自动转为 `degraded`。

2. **结构守卫与验证项扩充**（`scripts/verify.py` + `ARCHITECTURE.md` + `PROJECT_SLIMMING_PLAN.md`）
   `scripts/verify.py` 验证项扩充至 19 项，新增了 `/health` 的 `observability` 结构检查、联网搜索显式失败检查，并把语音保底回退纳入降级事件验证。同时，AST 级架构守卫正式生效，严禁已删除 facade 回流。

3. **搜索与语音不再静默吞错**（`search.py` + `voice_matcher.py` + `fallback_gateway.py`）
   - `search.py`：不再将 HTTP 错误或配置缺失伪装成“无搜索结果”，而是抛出 `SearchUnavailableError`，方便运维定位。
   - `voice_matcher.py`：将“语义不匹配”与“向量/集合故障”逻辑分离，后者会作为降级信号反映在健康检查中。
   - `fallback_gateway.py`：引入 `AIFallbackExhaustedError`，在主备链路全部失效时由边界层处理兜底文案。

4. **主链路分层注入**（`context_builder.py` + `retrieval.py`）
   新增 `get_persona_memory/get_user_profile_memory/get_relationship_memory`，`normal/qa` 并发检索分层记忆并注入系统提示。
3. **净聊测试开关**（`message_handler.py` + `cards.py`）
   新增 `/pure` 命令与按钮回调，开启后临时关闭 `long_term+bionic`，保留人设、画像、关系、知识和联网能力。
4. **上下文隔离测试**（`message_handler.py` + `database.py` + `cards.py`）
   新增 `/clear` 命令；该版本的初版实现是直接清理 `chat_history`，后续已在 `2026-04-07` 本地补丁中改为“只移动上下文边界、不物理删聊天记录”。
5. **存储结构扩展**（`database.py`）
   新增 `user_profile_facts`、`relationship_insights` 表及 upsert/读取接口；`/reset` 时同步清理对应向量层。
6. **迁移与验证脚本**（`scripts/migrate_memory_layers.py`、`scripts/verify_memory_layers.py`）
   提供第一阶段分层迁移和隔离环境验证入口，避免在真实库上盲改。
7. **文风微调**（`data/prompts/prompt_template.txt`）
   轻聊模式强调“先说人话、少动作描写”，并弱化固定高频关心词对回复的干扰。
8. **净聊实验稳定化**（`context_builder.py` + `cards.py`）
   `pure_mode=on` 且手动处于 `normal` 时，不再因短句自动降到 `light`；`/reply` 卡片会真实高亮当前模式，避免测试时 UI 与实际状态不一致。
9. **摘要复用修复**（`streaming.py` + `message_handler.py`）
   修复 `handle_ai_reply()` 硬编码返回 `{"content": ""}` 而未真实执行摘要提炼的 Bug；同步修复 `message_handler.py` 读取 `summary_info["content"]` 而非 `["intent"]` 的 key 不匹配问题。语音匹配链路现真实复用主流程摘要，`intent/emotion/theme` 全部透传，不再对同一轮回复重复发起 AI 摘要提炼。
10. **遗忘引擎时区对齐修复**（`bionic_memory.py`）
   修复 `decay_and_forget()` 中 `datetime.now(timezone.utc)`（tz-aware）与 SQLite naive UTC 直接相减导致 Python 3.12+ 抛出 `TypeError` 的问题；统一改为 `datetime.utcnow()` 与 `strptime` 解析的 naive datetime 对齐。
11. **代码卫生优化**（`bionic_memory.py` + `search.py` + `message_handler.py` + `data/prompts/prompt_template.txt`）
    - `bionic_memory.py`：`ChatAnywhere` 初始化静默异常改为 `debug` 级别日志
    - `search.py`：降级路径 HTTP 失败从 `error` 降为 `warning`
    - `message_handler.py`：仿生记忆看板无数据时的文案从技术术语改为角色化表达
    - `prompt_template.txt`：身份定义从"你不是程序/AI"否定句式改为"你就是Companion本人"正向表述
12. **时间语义统一与摘要契约收敛**（`time_utils.py` + `database.py` + `scheduler.py` + `ai_engine.py` + `streaming.py`）
    新增统一时间 helper，显式区分 SQLite naive UTC 与本地业务时间；`get_chat_counts()` 改为按“本地今天对应的 UTC 边界”统计，`get_last_interaction_time()` / 主动思绪调度统一走 helper。与此同时，`call_ai_summarize()` 收敛为始终返回 `intent/emotion/theme` 字典，移除调用方对字符串返回的兼容分支。
13. **路径与运行时资产收口**（`config.py` + `main.py` + `retrieval.py` + `ops.py`）
    `VOICE_LIB` 增加真实目录回退与音频文件校验；`retrieval.py` 初始化时确保 `MEMORY_PATH` 自动创建；启动期新增提示词/语音库/卡片图/`companion_audio` 集合自检；`/health` 返回 `resolved_provider`、`assets` 与 `degraded` 状态，减少“服务明明能跑却被误报 unhealthy”的情况。
14. **长期记忆去重与现实参考分层**（`retrieval.py` + `context_builder.py`）
    `get_long_term_memory()` 会排除 `bionic_reflection/bionic_consolidation`，避免与仿生记忆重复注入；`knowledge/web` 改为进入独立的“现实参考（仅供事实判断）”层，显式约束“只提供事实，不覆盖人格口吻”。
15. **语音匹配成功率与贴合度并行增强**（`voice_matcher.py` + `scripts/rebuild_audio_vectors.py`）
    语音匹配保留 `emotion+theme -> emotion/theme -> global` 的 Metadata 漏斗，同时从 `audio_map_tagged.json` 读取 tags 词表，对召回候选按 `tags/emotion/theme/length_type/距离` 重排；若摘要失败、向量失败、集合不可用或查询异常，仍会稳定回退到真实语音文件，优先保证“有语音”。
16. **验证脚本与文档漂移修复**（`scripts/verify.py` + `scripts/profile_latency.py` + `README.md` + `DEPLOYMENT.md` + `MODULES.md`）
    `scripts/verify.py` 新增“事实层与角色层分离”“语音保底回退”“tags 重排生效”“健康检查返回结构”验证项；`scripts/profile_latency.py` 修复对已删除私有函数的引用；文档统一收口 `VOICE_LIB/MEMORY_PATH`、`FEISHU_VERIFY_TOKEN`、多维语音匹配与健康检查现状。
17. **Presentation 收尾与文档同步**（`app/presentation/cards/*` + `app/presentation/formatters/*` + `app/cards.py` + `app/card_assets.py` + `docs/*.md`）
    `presentation/cards/builders.py` 正式承接全部命令卡片 JSON；`presentation/cards/assets.py` 正式承接主图缓存、预热与可注入上传策略；新增 `presentation/formatters/status_formatter.py` 与 `memory_formatter.py`；旧 `app/cards.py` / `app/card_assets.py` 退化为兼容 facade，同时重写 `README.md`、`ARCHITECTURE.md`、`MODULES.md` 并新增 `READING_ORDER.md`，把文档口径收敛到当前真实运行结构。
18. **最终验收收口**（`app/bootstrap.py` + `app/entrypoints/feishu_webhook.py` + `app/application/memory_reflection_service.py` + `app/application/context_assembler.py`）
    `bootstrap.py` 正式承接启动初始化和运行时资产检查；`entrypoints/feishu_webhook.py` 正式承接 webhook challenge/解密/验签/去重/异步投递；反思服务增加 AI 不可用时的本地兜底编码；上下文提示兼容旧“外界感知”文案，使 `scripts/verify.py` 最终达到 `17/17`。
19. **项目减负第一波**（`app/application/command_service.py` + `app/infrastructure/ai/*` + `docs/*.md`）
    删除 `app/ports/*`、`app/domain/models.py`、`app/domain/proactive_rules.py` 等未接入骨架；`command_service.py` 直接依赖 `presentation.cards.builders` 并删掉 `app/cards.py` / `app/card_assets.py`；`ai_engine.py`、`ops.py`、`memory_reflection_service.py` 与脚本改为直连 `infrastructure/ai/*`，删除 `app/ai_client.py`，文档同步进入“根目录 compat 继续收缩”的新状态。
20. **项目减负第二波**（`app/infrastructure/feishu/*` + `app/message_handler.py` + `app/streaming.py` + `app/scheduler.py` + `docs/*.md`）
    `message_handler.py`、`streaming.py`、`scheduler.py`、`command_service.py`、`post_reply_jobs.py`、`ops.py`、`feishu_event_parser.py` 全部改为直连 `infrastructure/feishu/*`；新增 `app/infrastructure/feishu/__init__.py` 作为公共导出入口；删除 `app/feishu_api.py`，并同步更新阅读路径与减负计划。
21. **项目减负第三波**（`app/application/memory_*_service.py` + `app/context_builder.py` + `docs/*.md`）
    `context_builder.py`、`message_handler.py`、`post_reply_jobs.py` 与验证脚本改为直连 `memory_reflection_service.py` / `memory_maintenance_service.py`；删除 `app/bionic_memory.py`，并同步更新当前 compat 列表、阅读顺序和验证说明。
22. **项目减负第四波**（`app/application/context_assembler.py` + `app/ai_engine.py` + `scripts/*.py`）
    `context_assembler.py` 补齐默认依赖装配能力，`ai_engine.py`、`scripts/verify.py`、`scripts/verify_memory_layers.py`、`scripts/profile_latency.py` 全部改为直连 `application/context_assembler.py`；删除 `app/context_builder.py`，并同步更新减负计划、阅读顺序和模块边界文档。
23. **项目减负第五波**（`app/infrastructure/persistence/*` + `app/application/reset_service.py` + `docs/*.md`）
    `bootstrap.py`、`message_handler.py`、`streaming.py`、`scheduler.py`、`command_service.py`、`reply_service.py`、`memory_*_service.py`、`context_assembler.py`、`provider_registry.py` 以及迁移/验证脚本全部改为直连 `persistence/sqlite_*_repo.py`、`_sqlite_common.py` 与 `reset_service.py`；删除 `app/database.py`，并同步更新减负计划、阅读顺序和模块边界文档。
24. **项目减负第六波**（`app/application/chat_orchestrator.py` + `app/application/reply_service.py` + `docs/*.md`）
    `chat_orchestrator.py` 不再依赖 `app/streaming.py`，而是直接调用 `app/application/reply_service.py`；`message_handler.py` 改为直接注入 `generate_reply`；删除 `app/streaming.py`，并同步更新阅读顺序、模块边界和减负计划。
25. **项目减负第七波**（`app/bootstrap.py` + `app/entrypoints/scheduler_runner.py` + `docs/*.md`）
    `bootstrap.py` 改为直连 `app/entrypoints/scheduler_runner.py`；`scheduler_runner.py` 直接承接 reminder / proactive / memory maintenance 的依赖装配与调度线程入口；删除 `app/scheduler.py`，并同步更新架构图、模块边界和减负计划。
26. **项目减负第八波**（`app/main.py` + `app/application/chat_orchestrator.py` + `docs/*.md`）
    `main.py` 改为直连 `app/application/chat_orchestrator.py` 的 `core_logic` 与 `executor`；删除 `app/message_handler.py`；`scripts/verify.py` 同步移除旧入口导入检查，并更新当前阅读路径、模块边界与减负计划。

## V5.6.9 (2026-03-27)

### 概览

- 清理废弃代码，移除未使用的 `companion_voice` 集合

### 详细说明

1. **retrieval.py**：移除 `voice_collection` 初始化（原集合已废弃未被实际使用）
2. **ai_engine.py**：健康检查更新为检查 `audio_collection`
3. **ARCHITECTURE.md**：数据存储图移除废弃的 `companion_voice` 条目

## V5.6.8 (2026-03-25)

### 概览

- 开启“人设一致性”专项治理，消除系统指令感
- 全链路去系统化：移除所有技术标签，替换为角色化感官描述

### 详细说明

1. **身份认同重构**：修改 `prompt_builder.py`，将外部“指令式”维护改为第一人称“内心的声音”。移除冗余的行为约束，改为角色的内在动机。
2. **上下文去系统化**：修改 `context_builder.py`，将 `### 🧠 思维合成` 等技术分割符替换为 `### 💡 Companion的意识流与外界感知`。移除 `(模式: qa)` 等向模型暴露的技术参数。
3. **记忆感官化处理**：修改 `bionic_memory.py`，剔除记忆计数统计（如“123次对话”），将检索 Header 优化为 `一瞬间闪过的画面`。将结构化情绪标签（如 `[开心]`）从注入文本中淡化，改为更自然的叙事引导。

## V5.6.7 (2026-03-25)

### 概览

- 飞书交互卡片新增 `/model` 按用户隔离的大模型切换功能

### 详细说明

1. 飞书交互卡片新增 `/model` 自由切换 Cerebras / Groq / DeepSeek 模型。
2. 实现用户级配置隔离：模型偏好写入 `user_settings` 表，允许不同用户并行使用不同的大模型而不依赖全局 `.env`。
3. 优化卡片布局设计：使用 bisected 两列布局，并分离"重新开始"危险按钮与其他常规操作按钮。

## V5.6.6 (2026-03-25)

### 概览

- 修复 Cerebras 429 降级到 Groq 时卡片永久停留"思考中..."的 Bug

### 详细说明

1. **根因**：`call_ai_stream()` 的 except 降级路径向 `call_with_fallback()` 传递了 `tools` 参数，Groq (Llama) 收到 `tools` 后以 `tool_calls` 返回内容而非 `delta.content`，导致 `generate()` 中 yield 0 个 chunk、`first_chunk` 为空。
2. **修复**：降级路径（`call_ai` 和 `call_ai_stream` 的 except 块）不再传递 `tools` 参数给 fallback 引擎。
3. **防御加固**：`stream_to_card` 新增卡片更新成功/失败追踪，若异步更新全部失败则在 `finish_streaming` 前同步保底推送。
4. **可观测性**：`stream_update_card_text` 在 HTTP 失败时增加日志输出。

## V5.6.5 (2026-03-25)

### 概览

- 语音匹配大幅升级为多维“灵魂匹配”
- `audio_map.json` 被结构化对象及标签替代

### 详细说明

1. 引入了多维标签体系：通过大模型为近 1400 条原始语音重新打上了 `emotion`、`theme` 和 `tags` 元属性。
2. 创立新集合 `companion_audio`：替换了原先一元 `companion_voice` 的直接文本映射体系，所有的语音特征全部打入了向量库的 Metadata 层。
3. `ai_engine.py` 的提取强化：将提炼意图函数升格为输出格式化的 JSON 数据，包含意图预测及对应的心境参数。
4. 漏斗匹配逻辑（`voice_matcher.py`）：引入 Metadata Filter。如今音频库搜索不再纯测距离，而是会先用 AI 预测的感情去漏网过滤（如果找不到同情感再回退全局搜索），由此显著减少了“情感错位”的假匹配。

## V5.6.4 (2026-03-24)

### 概览

- 修复主动意图引擎时区偏差 Bug

### 详细说明

1. 修复了 `get_last_interaction_time` 直接读取 SQLite `CURRENT_TIMESTAMP`（UTC）导致与本地时间偏差 8 小时的问题，通过 SQL 层 `datetime(timestamp, 'localtime')` 转换对齐系统时区。

## V5.6.2 (2026-03-23)

### 概览

- 语音匹配链路重构与精准度大幅提升

### 详细说明

1. 重构提炼职责：移除 `streaming.py` 粗暴截取前 30 字的假摘要透传逻辑。
2. 强制智能提炼：`voice_matcher.py` 全面启用大模型意图提炼 (`call_ai_summarize`)，过滤干扰动作描写，精准提取口语情感意图供向量检索。

## V5.6.1 (2026-03-22)

### 概览

- 基于全量代码审计完成 6 项高优修复
- 接入 Groq，fallback 链升级为 `Cerebras -> Groq -> DeepSeek`
- 继续清理上下文重复指令和时区不一致问题

### 详细说明

1. 流式卡片更新改为统一走 `feishu_api.stream_update_card_text()`，避免长回复中 token 过期导致 401。
2. `/status` 的模型信息不再手写映射，改为从 `ai_client._PROVIDER_CONFIG` 动态读取。
3. `tools_registry.get_current_time` 统一为 UTC+8，和 `prompt_builder` 保持一致。
4. `context_builder` 中的行为约束去重，减少 token 消耗和文风僵化。
5. `bionic_memory.decay_and_forget` 改为 `datetime.now(timezone.utc)`，明确与 SQLite UTC 一致。
6. `weather.py` 增加城市坐标映射和级联回退，`city` 参数真正生效。

## V5.6.0 (2026-03-21)

### 概览

- 以三阶段方式拆掉“上帝模块”
- 引入严格的单向依赖和分层数据流
- `main.py` 从大编排文件瘦身为纯入口

### 详细说明

1. 编排层拆分：从 `main.py` 拆出 `message_handler.py`、`streaming.py`、`prompt_builder.py`。
2. 能力层拆分：新增 `ai_client.py`、`context_builder.py`、`search.py`，把 AI 客户端、检索决策和联网搜索各自独立。
3. 基础设施统一：新增 `http_client.py`，统一 `requests.Session` 和重试策略。
4. 架构收益：解除了 `ai_engine.py` 与 `bionic_memory.py` 的双向依赖，主链更清晰，验证脚本保持全量可跑。

## V5.5.4 (2026-03-20 ~ 2026-03-21)

### 概览

- `_build_messages()` 并发化
- Embedding 完全本地化到 FastEmbed
- 增加多级缓存，优化流式降级体验

### 详细说明

1. `context_builder.py` 使用 `ThreadPoolExecutor(max_workers=4)` 并发执行长期记忆、仿生记忆、知识库和联网检索。
2. 向量化从阿里云 DashScope 迁移到本地 FastEmbed，Embedding 耗时从秒级降到毫秒级。
3. 新的本地向量目录指向 `data/db_local` 与 `data/voice_local`。
4. 引入搜索缓存和会话 LRU 缓存，减轻联网与 SQLite 读取压力。
5. 流式卡片失败后不再等待完整回复一次性发出，而是用普通文本模拟流式打字机效果。

## V5.5.3 (2026-03-20)

### 概览

- AI 引擎从单向降级升级为双向自动 fallback

### 详细说明

1. `_PROVIDER_CONFIG` 开始描述 provider 之间的 fallback 关系。
2. `_get_active_client()` 根据 `AI_PROVIDER` 决定主引擎，并在主引擎不可用时自动切换。
3. `call_with_fallback()` 支持同步与流式两种调用路径。
4. `call_ai()`、`call_ai_stream()`、`_do_ai_summarize()` 全部纳入统一 fallback 机制。

## V5.5.2 (2026-03-20)

### 概览

- `ai_engine.py` 职责拆分
- 仿生记忆运行时状态持久化
- Per-User 反思锁防止并发写入混乱

### 详细说明

1. `ai_engine.py` 只保留 AI 调用与工具调用。
2. `retrieval.py`、`voice_matcher.py`、`vision.py` 分别承接检索、语音匹配、图片识别。
3. 新增 `bionic_state` 表，持久化当前心情、关系阶段和反思次数。
4. `bionic_memory.py` 增加 Per-User 锁，保证同一用户反思串行执行。

## V5.5.1 (2026-03-20)

### 概览

- 基础设施稳态优化与验证脚本收口

### 详细说明

1. 为 HTTP 请求增加 429/5xx 自动重试。
2. 复用 ChromaDB `PersistentClient`，避免重复初始化。
3. `INGRESS_MAX_WORKERS` 和 `EXECUTOR_MAX_WORKERS` 变为可配置。
4. `scripts/verify.py` 切到临时 `DB_PATH` / `MEMORY_PATH`，防止污染线上数据。
5. 整合引擎按 `user_id + theme` 分桶，修复跨用户整合。

## V5.5 (2026-03-20)

### 概览

- AI 工具调用能力与主动消息能力上线

### 详细说明

1. `tools_registry.py` 统一管理时间和天气工具。
2. 大模型开始支持多轮 `tool_calls`。
3. `scheduler.py` 加入主动意图潜意识机制，每 30 分钟尝试一次“要不要主动找你聊天”。

## V5.4 (2026-03-20)

### 概览

- 仿生记忆系统上线

### 详细说明

1. 反思引擎：每轮对话后异步提炼结构化记忆碎片。
2. 整合引擎：每天凌晨 03:00 合并同主题碎片。
3. 遗忘引擎：每天凌晨 04:00 按艾宾浩斯曲线衰减。
4. `/memory` 命令上线，提供记忆看板。

## V5.3 (2026-03-19)

### 概览

- 表情包互动与图片识别体验增强

### 详细说明

1. 支持 `sticker` 类型消息并自动回发随机表情包。
2. 图片识别增加魔数检测，兼容 `png/jpeg/webp/gif/bmp`。
3. 结合人格提示实现“发图行为吐槽”，避免 AI 编造不可见图片内容。

## V5.2 (2026-03-18)

### 概览

- 以“减少隐式耦合”为目标的一轮代码质量优化

### 详细说明

1. `Config` 统一管理环境变量和路径。
2. `Config.validate()` 让缺失飞书必需配置时启动即失败。
3. 提示词模板按 mtime 热更新。
4. 数据库备份从 `copy2` 改为 `VACUUM INTO`。
5. 健康检查改为通过 `is_ready()` 解耦 AI 引擎。

## V5.0 / V5.1 (2026-03-17)

### 概览

- 联网搜索与三档回复模式形成当前交互基础

### 详细说明

1. 接入 Bocha Web Search。
2. 新增 `/reply` 模式切换。
3. 形成 `light / normal / qa` 三种回复策略。
4. 开始按检索强度决定是否启用长期记忆、知识库和联网搜索。

## V3.1 (2026-02-27)

### 概览

- 第一轮体感性能优化

### 详细说明

1. 先发文字、后发语音，显著降低用户等待感。
2. 批量 Embedding 减少网络往返。
3. 把实时时间信息移到提示词顶部，缓解时间幻觉。
幻觉。
