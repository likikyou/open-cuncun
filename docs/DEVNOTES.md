# 开发笔记

> 当前仓库状态：V5.7.1 (2026-04-08) + Unreleased，见 [CHANGELOG.md](CHANGELOG.md)。

这份文档只保留三类内容：

- 历史备忘
- 测试与验证命令
- 滚动开发日志

## 一、历史备忘

### 1. 早期文件背景

- 早期主程序 `feishu_companion_pro.py` 已重构到 `app/main.py`
- 之前还存在 `app_companion.py` 作为网页版

### 2. 语音上传成功方案

上传音频到飞书的关键是使用 `file` 字段名：

```python
files = {
    'file_type': (None, 'opus'),
    'file_name': (None, filename),
    'file': (filename, f.read(), 'application/octet-stream')
}
```

### 3. ChromaDB 集合演进

- `companion_voice` 为旧版语音匹配库，已废弃（V5.6.2 起），代码已清理
- 当前语音匹配使用 `companion_audio`，通过 emotion/theme 元数据过滤并结合 tags 重排候选

### 4. 技术决策背景

- 回复模式最终收敛为 `light / normal / qa`
- provider 映射统一以 `infrastructure/ai/provider_registry.py` 为唯一出处
- `scripts/verify.sh` 已收口为调用 `python3 scripts/verify.py`
- 版本记录不再写在开发笔记里，统一收敛到 `CHANGELOG.md`

## 二、测试与验证命令

### 当前首选入口

```bash
bash scripts/verify.sh
```

它会统一调用：

```bash
python3 scripts/verify.py
```

日常快速验证可先跑：

```bash
python3 scripts/verify.py --offline
```

工程侧当前建议再补一条：

```bash
python3 -m ruff check app scripts
python3 -m pytest scripts/test_webhook_entrypoint_smoke.py scripts/test_persona_consistency_smoke.py scripts/test_command_flow_smoke.py
```

当前验证脚本已额外覆盖：

- 已删除 facade 是否有回流 import
- `application/*` 是否反向依赖入口层
- `domain/*` 是否越界依赖实现层
- “角色状态层 / 现实参考层” 分离是否还在
- 语音匹配在向量失败时是否仍会回退到真实语音
- tags 重排是否真的会改变候选排序
- `/health` 是否返回 `runtime/assets` 等关键运行态字段
- `/health` 是否返回 `observability.recent_ai_runs`
- 人设一致性 smoke 是否锁住私人生活问句、默认天气地点、共同经历记忆和技术问答边界
- `/chat`、`/story`、`/memory audit` 是否保持卡片化入口，且卡片可见文案不露出 slash command
- `/observe` 是否走共享 snapshot，`/presence` 是否保持鉴权与只读返回
- observation 媒体任务占位是否能写入 `pending/ready/failed`、保留 `media_prompt` 并清理 `media_rendering`

### 常用手工验证

```bash
# 全模块导入
python3 -c "from app import main, ai_engine, retrieval, voice_matcher, vision; from app.application.context_assembler import build_messages; print('✅ All imports OK')"

# Flask 初始化
python3 -c "from app.main import app; print(app.name)"

# AI 对话基本通
python3 -c "from app.ai_engine import call_ai; print(call_ai('你是一个傲娇角色', '你好')[:80])"

# 运行时状态上下文
python3 -c "from app.application.memory_reflection_service import get_runtime_state_context; print(get_runtime_state_context('test_user'))"

# 实时观察只读接口（需先配置 PRESENCE_AUTH_TOKEN）
curl -H "Authorization: Bearer $PRESENCE_AUTH_TOKEN" "http://localhost:8081/presence?refresh=1"

# 图片格式检测
python3 -c "from app.vision import _get_image_media_type; print(_get_image_media_type(b'\\xff\\xd8\\xff'))"

# 分层记忆链路验证（隔离环境）
python3 scripts/verify_memory_layers.py

# 人设一致性边界验证
python3 -m pytest scripts/test_persona_consistency_smoke.py

# 命令卡片入口验证
python3 -m pytest scripts/test_command_flow_smoke.py

# 基础静态检查
python3 -m ruff check app scripts
```

### 每次重构必跑顺序

1. `bash scripts/verify.sh`
2. `python3 -m py_compile app/*.py`
3. 全模块导入检查
4. Flask 初始化检查
5. AI 对话冒烟检查
6. 反思链路或上下文注入链路抽查

### 2026-04-12：AI 运行观测与 uv/Ruff 工程链路落地

- `ai_engine.py` 现在会记录 AI 主链的 `request_started / first_chunk / tool_batch_completed / request_completed / fallback_*` 等运行事件，供 `/health -> observability.recent_ai_runs` 聚合查看。
- `ops.py` 的健康检查已补充 `observability.recent_ai_runs`，现在除了降级摘要，还能看最近 5 分钟 AI 主链阶段统计、provider 分布、工具调用与 fallback 次数。
- `scripts/verify.py` 新增了 AI 运行观测验证项，覆盖“AI 事件是否写入 recent_ai_runs”。
- 新增 `pyproject.toml` 与 `uv.lock`，并引入基础 `Ruff` 配置；`requirements.txt` 继续保留给旧环境兼容使用。
- 当前建议的工程命令已变为：优先 `python3 -m uv sync --extra dev`，日常静态检查走 `python3 -m ruff check app scripts`。

### 2026-04-23：入口收口、时间快路径与 PM2 真实启动命令对齐

- `app/main.py` 现在通过 `get_app()` 懒加载 canonical Flask app 单例；`wsgi.py` 与开发入口都改为初始化完成后再取同一个 app，不再出现 `app.main.app` 和 `wsgi.app` 两个不同实例。
- `memory_reflection_service.py` 的低成本 AI 调用已补上 provider success/failure 回写；后台反思、记忆整合、提醒任务不再把 half-open probe 卡在 `probe_in_flight=True`。
- `reply_service.py` 的纯当前时间问句改为真正的本地普通文本快路径：直接 `send_feishu(text)`，不再准备流式卡片，也不再走空的 `stream_reply`。
- `logger.py` 新增 `SERVICE_NAME` 配置，`run.py` / `wsgi.py` / `run_scheduler.py` 会分别默认写入 `feishu-companion-dev` / `feishu-companion-web` / `feishu-companion-scheduler`。
- 线上实际验证表明：PM2 拉 Python console script 形式的 `gunicorn` 时要带 `--interpreter none`；否则 PM2 会把它当成 Node 脚本执行。
- 若 `.venv` 是旧环境，先执行 `python3 -m uv sync --extra dev --extra server`，否则 `fastembed` / `gunicorn` 之类的新依赖不会自动出现在 PM2 运行环境里。

## 三、滚动开发日志

### 2026-04-23：实时观察系统文字版 MVP

- `observation_rules.py` 新增基础时间槽位、稳定 seed 和意外事件规则，保证同一时间桶内观察场景尽量稳定。
- `observation_service.py` 新增 observation snapshot 编排：复用天气、运行时情绪、最近聊天和 active memories，再用低成本 AI 渲染成第三人称白描；AI 失败时回退模板文案。
- SQLite 新增 `presence_snapshot` 表与 `sqlite_observation_repo.py`，让 `/observe` 与 `/presence` 共用同一份缓存状态，同时提前预留 `media_type/media_status/media_prompt/media_key`。
- `command_service.py` 接入 `/observe`，`main.py` 接入 `GET /presence`，鉴权走 `PRESENCE_AUTH_TOKEN`，未传 `user_id` 时回退 `ADMIN_OPEN_ID`。
- `scripts/verify.py --offline` 已补上 observation snapshot 复用和 `/presence` 鉴权路由验证，当前离线验证保持通过。

### 2026-04-23：实时观察补齐显式运行时状态

- SQLite 新增 `presence_runtime_state`，用于挂 observation 的短时显式状态；进入和退出状态时都会主动让 `presence_snapshot` 过期。
- `chat_orchestrator.py`、`post_reply_jobs.py`、`reminder_service.py`、`proactive_chat_service.py` 已分别接入 `replying / reflecting / reminder / proactive` 的 observation 状态写入。
- `observation_service.py` 现在会优先读取显式运行时状态，再回退到 `recent_chat / mood / routine`；低优先级状态不会覆盖更高优先级状态。
- `scripts/verify.py --offline` 新增 observation runtime_state 优先级验证，当前离线验证提升到 `16/16`。

### 2026-04-23：实时观察媒体任务占位骨架

- `observation_service.py` 新增 `media_rendering` 显式状态，优先级介于 `replying` 与 `reflecting` 之间，给未来图片/GIF/视频生成期提供可观察状态。
- `observation_media_service.py` 新增媒体任务占位入口：创建任务时写入 `media_status=pending` 并返回 `media_prompt`，完成时写回 `ready + media_key` 或 `failed`。
- `/presence` 的 `media` 结构现在会带上 `prompt`，方便未来 worker 或只读前端消费同一份 snapshot。
- `scripts/verify.py --offline` 新增 observation media placeholder 验证，当前离线验证为 `17/17`。

### 2026-04-21：多重对话、剧情模式与记忆审核卡片

- `sqlite_conversation_repo.py` 新增多重对话元数据仓储，`chat_history` 增加 `conversation_id`，旧历史会迁入默认“日常聊天”。
- `/chat` 现在支持同一飞书私聊内新建、切换、重命名和查看当前对话；`/help` 可进入中文化的对话管理卡片。
- `/story` 现在绑定到独立剧情对话，剧情设定只注入当前会话；剧情对话回复后会跳过现实仿生记忆反思。
- `/memory audit` 新增记忆审核卡片，扫描疑似剧情污染的 active 仿生记忆，并可逐条标记遗忘；该操作不会删除原始聊天记录。
- 卡片按钮可见文案已中文化，真实 slash command 只保留在按钮回调 value 中。
- `scripts/verify.py --offline` 新增多重对话隔离、剧情模式隔离、卡片中文化和记忆审核覆盖；`scripts/test_command_flow_smoke.py` 同步覆盖 `/chat`、`/story`、`/memory audit`。

### 2026-04-19：人设一致性边界补强

- `query_intent.py` 新增Companion私人生活问句识别和默认天气地点归一；“你那边天气”默认查“默认城市”。
- `reply_mode.py` / `context_policy.py` 避免“今天休息吗、给哪些明星化妆、私人行程”等关系内问题误触发 knowledge/web；混合“现在几点 + 天气”仍允许联网查天气。
- `context_assembler.py` 的现实参考层新增硬约束：外部新闻不能变成Companion自己的客户、出行安排或私人经历。
- `memory_rules.py` / `memory_reflection_service.py` 新增反思 scope：共同吃饭、一起玩、约会、见面等用户明确参与的经历会保留并提高重要度；只来自Companion回复的明星客户、私人行程等临场剧情会跳过可检索仿生记忆。
- `prompt_template.txt` 放开技术讨论边界：可以自然聊代码/报错/部署，但仍不能把自己说成程序或工具。
- 新增 `scripts/test_persona_consistency_smoke.py`，覆盖强思念口语、默认天气地点、私人生活不联网、共同经历记忆保护和技术问答边界。

### 2026-04-18：审计修复、smoke 迁移与离线验证补齐

- `entrypoints/feishu_webhook.py` 已补上解密空结果守卫，坏密文会明确返回 `400`，不再继续进入事件解析。
- `scripts/test_*_smoke.py` 已从旧 facade 迁移到当前分层模块，覆盖命令、消息、流式、调度、基础设施、上下文和 webhook 入口。
- `scripts/verify.py` 新增 `--offline` 快速验证模式，适合不碰真实 AI / embedding / 飞书接口时做本地回归。
- 当前建议的本地检查顺序：`python3 scripts/verify.py --offline`、`python3 -m ruff check app scripts`、相关 smoke `pytest`。

### 2026-04-01：进入结构守卫阶段

- `scripts/verify.py` 已新增 AST 级架构守卫，开始显式检查旧 facade 回流和依赖方向退化
- `docs/ARCHITECTURE.md` 已补充当前允许依赖方向，不再只描述模块位置
- `docs/PROJECT_SLIMMING_PLAN.md` 已从“继续删”切换到“减负完成后如何稳结构”
- 当前首选回归入口仍是 `python scripts/verify.py`，最新结果为 `18/18`

### 2026-03-31：第八轮项目减负与 Message Handler facade 收口

- `app/main.py` 已改为直连 `app/application/chat_orchestrator.py`
- 删除 `app/message_handler.py`，主对话链入口 compat 已清空
- `scripts/verify.py` 已同步移除对旧入口的导入检查
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：第七轮项目减负与 Scheduler facade 收口

- `app/bootstrap.py` 已改为直连 `app/entrypoints/scheduler_runner.py`
- `app/entrypoints/scheduler_runner.py` 现在直接承接调度线程入口、任务注册和 reminder / proactive / memory maintenance 的依赖装配
- 删除 `app/scheduler.py`，根目录 compat 再减少一层
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：第六轮项目减负与 Streaming facade 收口

- `app/application/chat_orchestrator.py` 已改直连 `app/application/reply_service.py`
- `app/message_handler.py` 现在直接注入 `generate_reply`
- 删除 `app/streaming.py`，回复生成链改为直接收口到 `reply_service.py` 与 `infrastructure/feishu/card_streamer.py`
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：第五轮项目减负与 Database facade 收口

- `app/bootstrap.py`、`message_handler.py`、`streaming.py`、`scheduler.py`、`command_service.py`、`reply_service.py`、`memory_*_service.py`、`context_assembler.py`、`provider_registry.py` 与迁移/验证脚本已改直连 `persistence/sqlite_*_repo.py`、`_sqlite_common.py` 和 `reset_service.py`
- 删除 `app/database.py`，根目录 compat 再减少一层
- `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`READING_ORDER.md`、`knowledge.md`、`PROJECT_SLIMMING_PLAN.md` 已同步到第五轮后的结构
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：第四轮项目减负与 Context facade 收口

- `app/application/context_assembler.py` 现在直接承接默认依赖装配，`build_messages()` 可在不经过 facade 的情况下独立工作
- `ai_engine.py`、`scripts/verify.py`、`scripts/verify_memory_layers.py`、`scripts/profile_latency.py` 已改直连 `app/application/context_assembler.py`
- 删除 `app/context_builder.py`，根目录 compat 再减少一层
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：第三轮项目减负与 Memory facade 收口

- `context_builder.py`、`message_handler.py`、`post_reply_jobs.py` 与验证脚本已改直连 `app/application/memory_reflection_service.py`
- 删除 `app/bionic_memory.py`，memory 相关能力现在直接落到 `memory_reflection_service.py` / `memory_maintenance_service.py`
- `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`READING_ORDER.md`、`knowledge.md`、`PROJECT_SLIMMING_PLAN.md` 已同步到第三轮后的结构
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：第二轮项目减负与 Feishu facade 收口

- `message_handler.py`、`streaming.py`、`scheduler.py`、`command_service.py`、`post_reply_jobs.py`、`ops.py`、`feishu_event_parser.py` 已改直连 `app/infrastructure/feishu/*`
- `app/infrastructure/feishu/__init__.py` 现在作为 Feishu 基础设施公共导出入口，收口 client / messenger / media_store
- 删除 `app/feishu_api.py`，根目录 compat 再减少一层
- `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`READING_ORDER.md`、`knowledge.md`、`PROJECT_SLIMMING_PLAN.md` 已同步到第二轮后的结构
- 回归验证保持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-03-31：首轮项目减负与 AI facade 收口

- 删除未接入骨架：`app/ports/*`、`app/domain/models.py`、`app/domain/proactive_rules.py`
- `app/application/command_service.py` 已直接依赖 `presentation.cards.builders`，并删除 `app/cards.py`、`app/card_assets.py`
- `ai_engine.py`、`ops.py`、`command_service.py`、`memory_reflection_service.py` 及脚本已改直连 `app/infrastructure/ai/*`，并删除 `app/ai_client.py`
- `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`READING_ORDER.md`、`knowledge.md`、`PROJECT_SLIMMING_PLAN.md` 已同步到最新结构
- 验证维持通过：`scripts/verify.py` 为 `17/17`，`scripts/verify_memory_layers.py` 通过

### 2026-04-02：文档全面对齐最新 commit，验证项扩充至 19/19

- 更新 `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`DEPLOYMENT.md`、`CHANGELOG.md` 顶部的“最后整理”日期为 `2026-04-02`。
- `CHANGELOG.md` “Unreleased” 部分同步补齐了昨日关于 `observability` 和 `verify.py` 的关键更新。
- 确认当前仓库已完成 8 波减负，根目录主要 facade 已清零，主对话链完全迁移至分层结构。
- 确认 `scripts/verify.py` 达到 19/19 全量通过。

### 2026-04-01：显式降级观测收口到 health，搜索与语音不再静默吞错

- 新增 `app/observability.py`，统一缓冲最近 5 分钟的降级事件，并由 `ops.check_health()` 聚合到 `/health -> observability.recent_degradations`。
- `fallback_gateway.py` 不再在核心层返回固定兜底文案或静默 `None`；当主引擎与 fallback 链路都失败时，会抛 `AIFallbackExhaustedError`，最终用户文案兜底只留在 `ai_engine.py` 边界层。
- `context_assembler.py` 现在会在日志里显式输出 `context_degraded/context_degradations`，不再把“空结果”和“检索异常”混成一类。
- `entrypoints/feishu_webhook.py` 去掉 `get_json(silent=True)`；非法 JSON 现在直接返回 `400` 并记录 `body_preview`，方便排查错误回调。
- `search.py` 只有“确实没搜索结果”才返回空字符串；`BOCHA_API_KEY` 缺失、HTTP 失败、返回非法 JSON 或业务错误都会显式抛错并由上层打标。
- `voice_matcher.py` 现在把“语义没命中”和“系统故障”分开：语义没命中只记 `info` 并回退保底语音；向量、集合、目录、查询异常记 `warning/error`，会反映到 `/health`。
- `scripts/verify.py` 补充了 `/health` `observability` 结构检查、联网搜索显式失败检查，并把语音保底回退纳入降级事件验证；当前验证为 `19/19` 通过。

### 2026-03-30：净聊测试稳定化、摘要复用恢复与多用户迁移隔离

- `context_builder.py` 调整 `pure_mode` 语义：当用户手动处于 `normal` 时，不再因短句自动降到 `light`，保证净聊测试只关闭 `long_term+bionic`，不让实验条件随输入长度漂移。
- `streaming.py` + `message_handler.py` 恢复 Fusion 摘要复用：`handle_ai_reply()` 现在会回传 `intent/emotion/theme`，并透传给 `async_voice_reply()`，避免语音匹配对同一轮回复重复发起摘要提炼。
- `bionic_memory.py` 把遗忘引擎时间基准统一为 naive UTC（`datetime.utcnow()`），与 SQLite `CURRENT_TIMESTAMP` 格式保持一致，避免 aware/naive 时间相减异常。
- `time_utils.py` 新增统一时间 helper：把 SQLite naive UTC 解析、本地时间转换和“本地今天 -> UTC 边界”换算收口，`database.py` / `scheduler.py` 不再各自混用 SQL `localtime` 与 Python 本地时间。
- `ai_engine.py` 把 `call_ai_summarize()` 收敛为稳定字典契约，空输入、无 client、解析失败和异常分支都统一返回 `intent/emotion/theme` 三字段结构；`streaming.py` 因此去掉了旧的字符串兼容分支。
- `cards.py` 的 `/reply` 卡片高亮逻辑改为跟随 `current_mode`，不再固定高亮 `normal`。
- `scripts/migrate_memory_layers.py` 改为为 `user_profile/relationship` 生成按用户隔离的稳定向量 ID，并在升级时按 `metadata.user_id` 定向清理旧版固定 ID。
- `scripts/verify_memory_layers.py` 新增双用户迁移验证；`scripts/test_context_builder_modes.py` 新增 `pure-normal` 短句保持 `normal` 的回归测试。

### 2026-04-07：`/clear` 行为修正与文档同步

- `sqlite_history_repo.py` 为聊天上下文新增 `chat_context_after_id` 逻辑边界，`clear_chat_history()` 不再删除 `chat_history`，而是只让后续上下文读取跳过旧消息。
- `reset_service.py` 把真正的聊天物理删除收口到 `delete_chat_history()`，因此 `/clear` 与 `/reset` 的数据后果正式拆开。
- `/clear` 的确认卡片、完成卡片和纯文本 fallback 文案已同步改为“保留历史聊天记录”，避免把“清空上下文”误理解成“删档”。
- `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`CHANGELOG.md` 已按真实行为补齐；改完后需继续执行 `python scripts/ingest_knowledge.py --source-dir docs` 更新知识库。

### 2026-04-08：日期回忆改查原始聊天记录

- `query_intent.py` 新增回忆追问识别与相对日期提取，`reply_mode.py` / `context_policy.py` 会把“昨天/前天说了什么”从普通 `qa` 问答里剥离出来，避免误触发 `knowledge/web`。
- `sqlite_history_repo.py` 新增 `get_history_by_day_offset()`，配合 `time_utils.py` 的本地日期边界换算，可直接回看指定日期的 `chat_history` 原文。
- `context_assembler.py` 对回忆类问题新增“真实对话回看”层，并在拿到原始聊天片段时降低抽象仿生记忆的权重，减少“凭感觉编具体原话”。
- 短跟问如“那前天呢？”现在会继承上一轮的回忆意图，不再因为句子太短被误判成 `light`。
- `bootstrap.VERSION`、`CHANGELOG.md`、`README.md`、`ARCHITECTURE.md`、`MODULES.md`、`DEPLOYMENT.md`、`knowledge.md` 已同步切到 `V5.7.1 (2026-04-08)`。

### 2026-03-30：路径收口、现实参考分层与语音兜底加固

- `config.py` 收口 `VOICE_LIB` 与 `EMOTICON_DIR` 路径解析，`VOICE_LIB` 现在会优先选择真实可用的音频目录，并校验目录中是否存在音频文件。
- `main.py` 新增启动期运行时资产自检，会打印提示词、语音库、卡片主图、`MEMORY_PATH` 与 `companion_audio` 集合状态。
- `ops.py` 的健康检查从简单二元状态改为 `healthy / degraded / unhealthy`，并返回 `resolved_provider`、`assets` 等字段；飞书 token 缓存未预热时不再等价于“主服务不可用”。
- `retrieval.py` 在初始化 Chroma 时会自动创建 `MEMORY_PATH`；`get_long_term_memory()` 会排除 `bionic_reflection/bionic_consolidation`，避免长期记忆与仿生记忆重复注入。
- `context_builder.py` 把上下文拆成“角色状态层”和“现实参考层”，知识库 / 联网结果不再直接混入角色意识流。
- `voice_matcher.py` 保留 `emotion/theme` 漏斗，同时新增 tags 词表抽取与候选重排；即使摘要、向量或集合异常，也会回退到真实语音文件，优先保证语音发送成功率。
- `scripts/profile_latency.py` 修复了对已删除私有函数的引用；`scripts/verify.py` 新增现实参考分层、语音保底回退、tags 重排和健康检查结构的验证项。

### 2026-03-29：分层记忆接入、净聊测试与上下文可观测性

- `context_builder.py` 接入 `persona/user_profile/relationship` 三层检索，并新增 `pure_mode` 分支（关闭 `long_term+bionic`）与 `🔎 上下文命中概览` 日志。
- `message_handler.py` + `cards.py` 新增 `/clear`（只清上下文）和 `/pure`（净聊测试）双命令及卡片回调链路；`/clear` 的初版实现当时仍是直接删 `chat_history`，后续已改为逻辑上下文边界。
- `database.py` 增加 `clear_chat_context()`，并落地 `user_profile_facts` / `relationship_insights` 的 upsert 与读取接口。
- `retrieval.py` 扩展 `companion_persona/companion_user_profile/companion_relationship` 集合及对应检索函数。
- 新增 `scripts/migrate_memory_layers.py` 与 `scripts/verify_memory_layers.py`，用于分层迁移和隔离验证。
- `prompt_template.txt` 轻调文风：轻聊场景优先短口语、降低动作描写频率，并弱化“熬夜/黑眼圈”高频提示词强度。

### 2026-03-26：provider 解析统一、路径配置去绝对化与验证脚本对齐

- `infrastructure/ai/provider_registry.py` 新增更完整的 `resolve_active_provider()` 观测字段，统一状态展示与真实调用的 provider 解析结果。
- `message_handler.py` 的线程池大小改为统一从 `Config` 读取，不再在模块顶层直接二次解析环境变量。
- `config.py` 的路径类配置改为支持相对路径自动按项目根目录解析；`EMOTICON_DIR` 默认优先项目内目录。
- `scripts/verify.py` 的运行时状态断言已同步到当前“去系统化”文案，恢复 13/13 通过。
- `retrieval.py` 的 FastEmbed 懒加载日志补充了“首次下载会阻塞当前请求”的提示，并同步到部署文档与模块说明，避免把首次下载误判成进程假死。
- `message_handler.py` 中的卡片资源与卡片构建已低风险拆分到 `card_assets.py` 和 `cards.py`，主编排文件从 1200+ 行收缩到 500+ 行，后续改卡片时更不容易误伤命令主链。
- `feishu_api.py` 的随机表情包发送补了目录扫描缓存，减少 sticker 触发时重复 `glob` 带来的额外开销。

### 2026-03-24：主动意图引擎时差 Bug 修复

- 排查并修复了 `scheduler.py` 触发主动思绪时时间差凭空多出 8 小时的问题。
- 根因：`datetime.now()` 使用本地时间，而 SQLite `CURRENT_TIMESTAMP` 存的是 UTC。
- 解决：在 `database.py` 中查时间时直接包一层 `datetime(timestamp, 'localtime')` 转换对齐。
- 更新了 `knowledge.md` 加入知识卡片记录。

### 2026-03-21：验证可信度、安全收口与文档归并

- `scripts/verify.py` 的 `check()` 从“只打印失败”改为真实抛出 `AssertionError`
- `scripts/verify.sh` 收敛为单一入口，不再维护两套验证逻辑
- 新增 `.env.example`，并把敏感文件移出 Git 跟踪
- 文档结构开始从“混写”向“唯一出处”收口

### 2026-03-21：提示词减负、三档模式重构与飞书卡片交互

- `prompt_builder.py` 顶层约束从强行长文改为按场景自然变化
- `context_builder.py` 开始裁剪长期记忆、仿生记忆、知识库和联网结果
- 默认模式从旧的 `"all"` 收敛为 `"normal"`
- `/reply`、`/help`、`/status`、`/memory` 逐步回归交互卡片
- 飞书卡片回调签名逻辑改为兼容非数字时间戳

### 2026-03-22：视觉卡片统一、图片预热与回调稳定性加固

- 五类卡片接入定制视觉稿
- `message_handler.py` 新增卡片主图预上传与本地缓存
- `/reset` 改为确认卡片 + 完成卡片的双阶段交互
- `card.action.trigger` 做快速确认与日志区分，便于判断飞书重试和用户重复点击

### 2026-03-22：仿生记忆链路修复与流式降级优化

- `get_runtime_state_context()` 的死代码被清理，运行时状态重新注入 AI 上下文
- `/reset` 现在同步清理 SQLite 与 ChromaDB
- `bio_collection` 检索增加 `user_id` 过滤，避免跨用户记忆泄漏
- 流式卡片失败时改用普通文本流式，不再等待完整回复一次性发送

### 2026-03-22：架构扫描修复

- 流式卡片更新统一走 `FeishuClient`
- `/status` 模型映射动态化
- `get_current_time` 统一 UTC+8
- `context_builder` 行为指令去重
- 遗忘引擎时区注释和实现标准化
- `weather.py` 增加城市坐标映射
