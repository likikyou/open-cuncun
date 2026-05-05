# Feishu AI Companion

> 最后整理：2026-04-23
> 当前仓库状态：V5.7.1 (2026-04-08) + Unreleased，见 [CHANGELOG.md](CHANGELOG.md)。

Companion是运行在飞书上的 AI 伴侣项目：

- Flask 路由入口仍在 `app/main.py`，但生产 WSGI 入口已单独拆到 `wsgi.py`，独立 scheduler 入口拆到 `run_scheduler.py`

## 看不懂时先这样读

### 第一步：先分清两类文件

#### 1. 运行入口和稳定底座

这些文件先知道“请求从哪里进、线程从哪里起、底层能力在哪里”就够了：

- `app/main.py`
- `app/bootstrap.py`
- `app/ai_engine.py`

#### 2. 值得精读的实现层

第一轮只读这几类：

- `app/entrypoints/`
- `app/application/`
- `app/presentation/`
- `app/infrastructure/`
- `app/domain/`

### 第二步：只跑一条主链，不要同时看全项目

最推荐的第一条主链：

```text
app/main.py
  -> app/entrypoints/feishu_webhook.py
  -> app/application/chat_orchestrator.py
  -> app/application/reply_service.py
  -> app/ai_engine.py
  -> app/application/context_assembler.py
  -> app/infrastructure/feishu/card_streamer.py
```

这条链能帮你先回答 4 个最重要的问题：

- 请求从哪里进来
- 命令和普通聊天在哪里分流
- AI 回复在哪里生成
- 飞书卡片/文本在哪里发出去

### 第三步：按功能而不是按目录看

不要试图一次看完整个 `app/`。更省力的办法是按你关心的功能读：

| 你想搞懂什么 | 先看这些文件 |
|:---|:---|
| 飞书消息怎么进来 | `app/main.py` → `app/entrypoints/feishu_webhook.py` |
| 普通对话怎么跑 | `app/application/chat_orchestrator.py` → `app/application/reply_service.py` |
| 命令怎么处理 | `app/presentation/parsers/feishu_event_parser.py` → `app/application/command_service.py` |
| 上下文怎么拼 | `app/ai_engine.py` → `app/application/context_assembler.py` → `app/domain/query_intent.py` → `app/domain/reply_mode.py` → `app/domain/context_policy.py` |
| 卡片怎么生成 | `app/presentation/cards/builders.py` → `app/presentation/formatters/*.py` |
| 记忆怎么写入/遗忘 | `app/application/memory_reflection_service.py` → `app/application/memory_maintenance_service.py` → `app/domain/memory_rules.py` |
| 定时任务怎么跑 | `app/entrypoints/scheduler_runner.py` → `app/application/reminder_service.py` → `app/application/proactive_chat_service.py` |

### 第四步：第一次阅读时，允许自己主动忽略

第一遍可以暂时不深究这些内容：

- `deps={...}` 这类依赖注入细节
- 大段卡片 JSON
- 向量库底层细节
- 历史兼容导出

只先抓“输入 -> 编排 -> 输出”的骨架。

### 第五步：用一个最小目标来读代码

不要把目标定成“看懂整个重构”。那样很容易卡住。

先定成下面这种小目标之一：

1. 我今天只搞懂“用户发一句话后，回复是怎么出来的”。
2. 我今天只搞懂“/status 卡片是怎么发出去的”。
3. 我今天只搞懂“记忆是在哪一层落库的”。

当你能独立讲清其中一条链，整个项目就会开始从“碎片”变成“地图”。

## 当前核心特性

| 特性 | 说明 |
|:---|:---|
| 飞书安全接入 | 支持 webhook 解密、challenge、签名校验、`event_id` 去重 |
| 同用户串行处理 | 主对话链按 `open_id` 加逻辑锁，避免并发串话 |
| 命令卡片化 | `/status`、`/reply`、`/model`、`/memory`、`/reset`、`/clear`、`/pure`、`/chat`、`/story`、`/help` 已卡片化；卡片可见按钮使用中文动作名，真实命令隐藏在按钮回调里；`/observe` 也已接入帮助卡片快捷入口 |
| 实时观察系统 | `/observe` 会返回第三人称文字快照；配置 `PRESENCE_AUTH_TOKEN` 后，`/presence` 会返回同源的只读 JSON；底层统一复用 `presence_snapshot`，并会优先读取 `replying / media_rendering / reflecting / proactive / reminder` 这类显式系统状态；图片/视频第一阶段仅保留媒体任务占位骨架 |
| 多重对话 | `/chat` 支持在同一个飞书私聊里新建、列出、切换、重命名多个独立聊天上下文；`/help` 可直接进入对话控制台 |
| 剧情模式 | `/story` 会开启独立剧情对话，剧情提示只注入当前会话，回复后不会写入现实仿生记忆；`/help` 可直接进入剧情控制台 |
| 记忆审核 | `/memory audit` 会列出疑似剧情污染的活跃仿生记忆，并可在卡片里逐条标记遗忘 |
| `/clear` 只清上下文不删档 | `/clear` 现在只重置后续带给模型的上下文窗口，历史聊天记录仍保留；真正删除聊天记录只在 `/reset` 发生 |
| 日期回忆优先回看原始聊天记录 | 问“昨天/前天/上次聊了什么”时，优先读取 `chat_history` 的真实片段，而不是只靠抽象仿生记忆猜测 |
| 回复格式收口 | 轻聊和事实问答都会优先输出单段自然文本，少量动作描写会内嵌在句子里，不再默认拆成多段短句 |
| 中文口语思念纠偏 | 像“想死你了”“想你想死了”这类高频口语会默认按强烈思念、撒娇和黏人理解，不再优先按字面死亡或闹情绪处理 |
| 流式回复与降级 | 先创建飞书流式卡片；卡片失败时退回普通文本单次发送，不再模拟多条文本打字机流 |
| 当前时间优先读本机 | 问“现在几点/今天几号”时，优先走本地时间工具并直接返回普通文本，读取 VPS 本地时区时间，不再混入 web/knowledge 结果，也不再准备流式卡片 |
| 多模型 fallback | `Cerebras -> Groq -> DeepSeek` 双向 fallback，支持用户级 `/model` 切换，并带 provider 熔断避免主模型故障时每轮都等超时 |
| 混合上下文检索 | `persona / user_profile / relationship / long_term / bionic / knowledge / web` 分层注入 |
| 运行时可观测 | AI / context / web / voice 的降级会进入结构化日志，并汇总到 `/health` 的 `observability.recent_degradations`；AI 主链最近 5 分钟的请求、首包、工具调用与 fallback 摘要会进入 `observability.recent_ai_runs`，provider 熔断状态会进入 `ai_circuit` |
| 仿生记忆闭环 | 反思、整合、遗忘、运行时状态与 recall boost 已拆到独立应用服务 |
| 主动任务 | 定时提醒、主动消息、备份、记忆维护由独立 scheduler 进程执行；开发模式 `python run.py` 仍会顺手起一个进程内线程 |

## 当前工程形态

```text
run.py                          # 开发模式入口：内建 Flask + 进程内 scheduler
wsgi.py                         # 生产 Web 入口：给 Gunicorn 加载
run_scheduler.py                # 生产 scheduler 入口：独立进程运行
app/main.py                     # Flask 路由入口与兼容导出
app/bootstrap.py                # 运行时初始化与开发模式启动引导
app/entrypoints/feishu_webhook.py # webhook 处理
app/entrypoints/scheduler_runner.py # scheduler 入口与 job 注册

app/application/*               # 用例编排
app/domain/*                    # 纯规则
app/infrastructure/*            # Feishu / AI / SQLite / Chroma 适配
app/presentation/*              # 事件解析、卡片 JSON、格式化
```

## 3 步启动

### 1. 安装依赖

```bash
cd open-cuncun
python3 -m uv sync --extra dev
```

兼容旧方式：

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

最小必填项：

```bash
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_ENCRYPT_KEY=your_encrypt_key

AI_PROVIDER=cerebras
CEREBRAS_API_KEY=your_cerebras_key
AI_REQUEST_TIMEOUT_SECONDS=20
AI_CIRCUIT_ENABLED=true
AI_CIRCUIT_FAILURE_THRESHOLD=3
AI_CIRCUIT_WINDOW_SECONDS=60
AI_CIRCUIT_OPEN_SECONDS=300
```

完整变量说明见 [MODULES.md](MODULES.md)。

### 3. 启动并验证

```bash
python run.py
curl http://localhost:8081/health
python scripts/verify.py --offline
python scripts/verify.py
python3 -m pytest scripts/test_persona_consistency_smoke.py
python3 -m ruff check app scripts
```

生产环境常用方式：

```bash
python3 -m uv sync --extra dev --extra server
pm2 start .venv/bin/gunicorn --interpreter none --name feishu-companion-web -- -w 1 --threads 8 -b 0.0.0.0:8081 wsgi:app
pm2 start run_scheduler.py --name feishu-companion-scheduler --interpreter .venv/bin/python
```

补充说明：

- `run.py` 现在定位为开发模式入口；生产建议使用 `Gunicorn + 独立 scheduler`。
- 若刚更新过依赖或锁文件，先重新执行一次 `python3 -m uv sync --extra dev --extra server`，确保 `.venv` 里已经包含 `fastembed`、`gunicorn` 等运行时依赖。
- 结构化日志里的 `service` 会按入口自动区分：`feishu-companion-web` / `feishu-companion-scheduler` / `feishu-companion-dev`；也可通过 `SERVICE_NAME` 覆盖。
- `feishu-companion-web` 当前建议保持 `1 worker`，因为 webhook `event_id` 去重、`ai_circuit` 和 recent observability 摘要仍是进程内状态。

## 文档导航

- [ARCHITECTURE.md](ARCHITECTURE.md)：当前真实分层、主链流程、兼容 facade 映射
- [MODULES.md](MODULES.md)：模块分区、关键入口、环境变量和能力边界
- [READING_ORDER.md](READING_ORDER.md)：新同学建议阅读顺序
- [PROJECT_HISTORY.md](PROJECT_HISTORY.md)：从 210 次 Git 提交整理出的Companion成长史与关键里程碑
- [TECHNICAL_EVOLUTION.md](TECHNICAL_EVOLUTION.md)：关键提交 diff 视角的技术演化复盘
- [STABILITY_CHECKLIST.md](STABILITY_CHECKLIST.md)：日常巡检、线上冒烟、备份恢复与稳定性优化清单
- [ONLINE_SMOKE_REPORT_TEMPLATE.md](ONLINE_SMOKE_REPORT_TEMPLATE.md)：每次部署/重启后的飞书线上冒烟记录模板
- [OBSERVATION_SYSTEM.md](OBSERVATION_SYSTEM.md)：实时观察系统第一阶段实现与后续扩展稿，收口 `/observe`、`/presence`、显式系统状态、媒体任务占位骨架与未来图片/视频扩展位
- [DEPLOYMENT.md](DEPLOYMENT.md)：部署、启动、运维与常见问题
- [CHANGELOG.md](CHANGELOG.md)：版本与本地未发布改动
- [DEVNOTES.md](DEVNOTES.md)：历史过程记录与临时备忘

文档维护约定：

- 改分层或调用链，同步 `ARCHITECTURE.md`
- 改模块职责或配置项，同步 `MODULES.md`
- 改协作者上手路径，同步 `READING_ORDER.md`
- 改部署或运维流程，同步 `DEPLOYMENT.md`
