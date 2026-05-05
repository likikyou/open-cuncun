# docs 同步知识库

> 最后整理：2026-04-23
> 当前文档体系：`README.md` / `ARCHITECTURE.md` / `MODULES.md` / `DEPLOYMENT.md` / `CHANGELOG.md` / `DEVNOTES.md` / `OBSERVATION_SYSTEM.md` / `knowledge.md`

## 一、这份文件是干什么的

这份文件不是面向外部读者的说明文档，而是给后续维护用的“同步规则速查表”。

现在它负责两件事：

- 改了代码后，能立刻知道哪些文档必须一起改
- 改完文档后，能用一条标准命令把 `docs/` 目录直接同步进知识库

如果只做到第一件事，这份文件就还是“人工提醒表”。
项目变大以后，必须补上第二件事，不然 `docs/` 越多，越容易出现“文档已经更新，但知识库还停在旧版本”的问题。

## 二、标准同步入口

### 1. `docs/` 现在就是可直接入库的文档源

项目文档的权威来源是 `docs/`，不是手工复制出来的中间目录。

改完 `docs/` 后，标准做法是直接运行：

```bash
python scripts/ingest_knowledge.py --source-dir docs
```

这条命令现在会自动做三件事：

- 递归扫描 `docs/` 下的 `.md` / `.txt` 文件
- 以“相对路径”而不是“单纯文件名”作为知识来源标识，避免后续子目录变多后撞名
- 清理 `docs/` 里已经删除、但知识库里还残留的旧 chunk

换句话说，`docs/` 已经具备“一键同步整个目录”的标准入口，不需要再先手工搬到 `knowledge/`。

### 2. `knowledge/` 仍然可以保留给外部材料

如果后面还有单独的人设资料、业务资料、FAQ 原文、第三方说明等，不适合放进 `docs/`，仍然可以继续走：

```bash
python scripts/ingest_knowledge.py --source-dir knowledge
```

约定如下：

- `docs/`：项目正式文档、架构文档、部署文档、开发日志
- `knowledge/`：额外喂给知识库的外部材料

两者都进入同一个 `companion_knowledge` 集合，但会按各自目录打上不同来源标记。

### 3. 新规则下，什么时候算“同步完成”

一次文档同步完成，至少满足下面 3 条：

1. 代码相关文档已经更新到 `docs/`
2. 已执行 `python scripts/ingest_knowledge.py --source-dir docs`
3. 没有遗漏新增文档，也没有保留已删除文档的旧 chunk

以后不要再把“文档改了但没入库”视为同步完成。

## 三、八份文档的固定职责

| 文档 | 固定职责 | 不应该写什么 |
|:---|:---|:---|
| `README.md` | 项目入口、核心特性、性能指标、3 步快速开始、文档导航 | 不写详细模块说明、FAQ、版本演进 |
| `ARCHITECTURE.md` | 架构唯一出处：分层图、对话流程图、数据图、模块职责表、仿生记忆三引擎图 | 不写部署细节、版本历史、函数级说明 |
| `MODULES.md` | 模块说明唯一出处：核心机制、关键函数签名、重要参数、环境变量总表 | 不写完整部署手册、版本演进 |
| `DEPLOYMENT.md` | 部署与运维：基础设施、启动配置、PM2、日志、备份、常见问题 | 不写模块细节、版本历史 |
| `CHANGELOG.md` | 版本记录唯一出处 | 不写部署命令、模块签名 |
| `DEVNOTES.md` | 历史备忘、验证命令、滚动开发日志 | 不写正式架构图、版本总表 |
| `OBSERVATION_SYSTEM.md` | 实时观察系统的设计边界、snapshot 思路、媒体扩展位与分阶段路线图 | 不写部署排障、版本总表 |
| `knowledge.md` | 文档同步规则、代码改动到文档的映射、知识库入库标准命令 | 不写业务功能说明、部署细节、版本正文 |

## 四、同步规则总表

### 1. 改入口、主链、职责边界

涉及文件：

- `run.py`
- `wsgi.py`
- `run_scheduler.py`
- `app/main.py`
- `app/bootstrap.py`
- `app/entrypoints/feishu_webhook.py`
- `app/application/chat_orchestrator.py`
- `app/entrypoints/scheduler_runner.py`
- `app/application/reply_service.py`
- `app/ai_engine.py`
- `app/application/context_assembler.py`
- `app/infrastructure/feishu/__init__.py`
- `app/infrastructure/feishu/client.py`
- `app/infrastructure/feishu/messenger.py`
- `app/infrastructure/feishu/media_store.py`
- `app/infrastructure/ai/provider_registry.py`
- `app/infrastructure/ai/provider_health.py`
- `app/infrastructure/ai/fallback_gateway.py`

必须同步：

- `ARCHITECTURE.md`
- `MODULES.md`

视情况同步：

- `README.md`
  当用户可见特性、快速开始、命令入口发生变化时
- `CHANGELOG.md`
  当这次变更属于版本级能力调整时

### 2. 改环境变量、配置项、路径

涉及文件：

- `app/config.py`
- `app/main.py`
- `.env.example`

必须同步：

- `MODULES.md`

视情况同步：

- `README.md`
  当快速开始里的最小配置步骤变了
- `DEPLOYMENT.md`
  当部署所需配置、启动命令、路径覆盖变了
- `CHANGELOG.md`
  当这是一个正式版本变更点

额外提醒：

- 如果配置项会被启动入口直接消费，例如 `SERVER_HOST`、`SERVER_PORT`、`DEBUG_MODE`，不要只检查 `config.py`，还要同时检查 `main.py` / `run.py` 是否仍有硬编码。
- 如果入口已经拆成 `wsgi.py` / `run_scheduler.py`，也要确认生产启动命令和文档里的进程拆分仍一致，不要只盯着 `run.py`。

### 3. 改部署方式、运维方式、故障排查方式

涉及文件：

- `run.py`
- `wsgi.py`
- `run_scheduler.py`
- `pyproject.toml`
- `uv.lock`
- `scripts/verify.py`
- `scripts/verify.sh`
- `Ruff` / `uv` 相关本地命令
- `app/ops.py`
- `app/observability.py`
- `app/bootstrap.py`
- `app/entrypoints/scheduler_runner.py`
- `scripts/ingest_knowledge.py`
- PM2 / 健康检查 / 备份相关脚本

必须同步：

- `DEPLOYMENT.md`

视情况同步：

- `DEVNOTES.md`
  当验证入口、排查命令、经验结论变化时
- `MODULES.md`
  当 `ops.py` / `bootstrap.py` / `entrypoints/scheduler_runner.py` / `ingest_knowledge.py` 的函数行为、配置项或同步入口变化时
- `README.md`
  当 3 步快速开始受影响时
- `knowledge.md`
  当文档入库标准命令、来源规则、目录约定变化时

额外提醒：

- 如果工程入口从 `requirements.txt` 扩展到 `pyproject.toml` / `uv.lock` / `Ruff`，至少同步检查 `README.md` 的快速开始、`DEPLOYMENT.md` 的安装命令，以及 `DEVNOTES.md` 的日常验证命令是否仍一致。

### 4. 改用户可见能力或交互方式

涉及内容：

- 新命令 / 删除命令
- 新只读接口 / 新观察入口
- reply mode 变化
- 卡片交互变化
- 流式体验变化
- 语音匹配策略变化
- 仿生记忆对用户可见的表现变化
- 帮助文案、状态文案、命令说明文字变化

必须同步：

- `README.md`
- `MODULES.md`

视情况同步：

- `ARCHITECTURE.md`
  当底层流程图或职责边界也变了
- `DEPLOYMENT.md`
  当 FAQ、运维排查方式也要调整时
- `OBSERVATION_SYSTEM.md`
  当观察系统的 snapshot 结构、媒体扩展位或分阶段方案发生变化时
- `CHANGELOG.md`

额外提醒：

- `command_service.py` 里很多命令同时存在“卡片版入口”和“纯文本 fallback 文案”。新增或删除命令时，至少要同步检查：
  - `presentation/cards/builders.py` 里的对应 `build_*_card()`
  - `_handle_help_command()` 的 `help_text`
  - 相关命令自己的 fallback 文案（例如 `/reply`、`/model`、`/reset`）

### 5. 改数据结构、存储结构、检索结构

涉及文件：

- `app/application/reset_service.py`
- `app/infrastructure/persistence/_sqlite_common.py`
- `app/infrastructure/persistence/sqlite_history_repo.py`
- `app/infrastructure/persistence/sqlite_memory_repo.py`
- `app/infrastructure/persistence/sqlite_profile_repo.py`
- `app/infrastructure/persistence/sqlite_settings_repo.py`
- `app/retrieval.py`
- `app/application/memory_reflection_service.py`
- `app/application/memory_maintenance_service.py`
- `app/infrastructure/persistence/sqlite_observation_repo.py`
- `scripts/ingest_knowledge.py`

必须同步：

- `ARCHITECTURE.md`
- `MODULES.md`

视情况同步：

- `DEPLOYMENT.md`
  当备份、迁移、路径或运维操作受影响时
- `CHANGELOG.md`
- `knowledge.md`
  当知识库来源目录、去重规则、清理规则变化时

### 6. 改外部依赖或第三方服务接入

涉及内容：

- Feishu API
- Cerebras / Groq / DeepSeek
- Bocha
- DashScope
- FastEmbed / ChromaDB
- `uv` / `Ruff` / `pyproject.toml` 这类工程依赖与质量工具

必须同步：

- `MODULES.md`

视情况同步：

- `ARCHITECTURE.md`
  当分层图或外部服务图需要更新时
- `DEPLOYMENT.md`
  当部署依赖、网络要求、排查方式变化时
- `README.md`
  当核心特性或快速开始受影响时
- `CHANGELOG.md`

### 7. 改 AI 可观测、健康检查或验证口径

涉及文件：

- `app/ai_engine.py`
- `app/infrastructure/ai/provider_health.py`
- `app/observability.py`
- `app/ops.py`
- `scripts/verify.py`

必须同步：

- `MODULES.md`
- `DEPLOYMENT.md`

视情况同步：

- `ARCHITECTURE.md`
  当主链职责或 `/health` 聚合口径发生变化时
- `DEVNOTES.md`
  当验证项、排障入口、日常命令变化时
- `CHANGELOG.md`
  当这次变更属于正式能力增强或未发布更新点时

## 五、按代码文件反查文档

| 代码文件/区域 | 优先同步文档 |
|:---|:---|
| `run.py` / `wsgi.py` / `run_scheduler.py` | `ARCHITECTURE.md`、`DEPLOYMENT.md`、必要时 `README.md` / `knowledge.md` |
| `app/main.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/bootstrap.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/entrypoints/feishu_webhook.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/application/chat_orchestrator.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `README.md` |
| `app/application/command_service.py` | `README.md`、`MODULES.md`、必要时 `ARCHITECTURE.md` / `CHANGELOG.md` |
| `app/application/observation_service.py` | `ARCHITECTURE.md`、`MODULES.md`、`README.md`、必要时 `DEPLOYMENT.md` / `OBSERVATION_SYSTEM.md` / `CHANGELOG.md` |
| `app/application/observation_media_service.py` | `ARCHITECTURE.md`、`MODULES.md`、`README.md`、`OBSERVATION_SYSTEM.md`、必要时 `CHANGELOG.md` / `DEVNOTES.md` |
| `app/application/reply_service.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `README.md` |
| `app/entrypoints/scheduler_runner.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/prompt_builder.py` | `MODULES.md` |
| `app/ai_engine.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/infrastructure/feishu/__init__.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/infrastructure/feishu/client.py` | `MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/infrastructure/feishu/messenger.py` | `MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/infrastructure/feishu/media_store.py` | `MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/infrastructure/ai/provider_registry.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/infrastructure/ai/provider_health.py` | `ARCHITECTURE.md`、`MODULES.md`、`DEPLOYMENT.md` |
| `app/infrastructure/ai/fallback_gateway.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/time_utils.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `CHANGELOG.md` |
| `app/application/context_assembler.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/retrieval.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/application/memory_reflection_service.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `README.md` |
| `app/application/memory_maintenance_service.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `README.md` |
| `app/application/reset_service.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/domain/query_intent.py` | `MODULES.md`、必要时 `ARCHITECTURE.md` / `README.md` / `CHANGELOG.md` |
| `app/domain/observation_rules.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `OBSERVATION_SYSTEM.md` |
| `app/domain/reply_mode.py` | `MODULES.md`、必要时 `README.md` / `CHANGELOG.md` |
| `app/domain/context_policy.py` | `MODULES.md`、必要时 `ARCHITECTURE.md` / `README.md` / `CHANGELOG.md` |
| `app/domain/memory_rules.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `CHANGELOG.md` |
| `app/infrastructure/persistence/_sqlite_common.py` | `ARCHITECTURE.md`、`MODULES.md` |
| `app/infrastructure/persistence/sqlite_observation_repo.py` | `ARCHITECTURE.md`、`MODULES.md`、必要时 `OBSERVATION_SYSTEM.md` / `CHANGELOG.md` |
| `app/security.py` | `MODULES.md`、必要时 `DEPLOYMENT.md` |
| `app/search.py` | `MODULES.md`、必要时 `README.md` |
| `app/tools_registry.py` | `MODULES.md` |
| `app/weather.py` | `MODULES.md` |
| `app/vision.py` | `MODULES.md` |
| `app/voice_matcher.py` | `MODULES.md`、必要时 `README.md` |
| `app/observability.py` | `ARCHITECTURE.md`、`MODULES.md`、`DEPLOYMENT.md` |
| `app/ops.py` | `MODULES.md`、`DEPLOYMENT.md` |
| `app/config.py` / `.env.example` | `MODULES.md`、必要时 `README.md` / `DEPLOYMENT.md` |
| `scripts/verify.py` / `scripts/verify.sh` | `DEPLOYMENT.md`、`DEVNOTES.md` |
| `scripts/test_*_smoke.py` | `DEVNOTES.md`、必要时 `DEPLOYMENT.md` / `CHANGELOG.md` |
| `scripts/ingest_knowledge.py` | `knowledge.md`、`DEPLOYMENT.md`、必要时 `MODULES.md` |
| `scripts/migrate_memory_layers.py` | `ARCHITECTURE.md`、`MODULES.md`、`DEPLOYMENT.md`、必要时 `CHANGELOG.md` |
| `scripts/verify_memory_layers.py` | `DEVNOTES.md`、`DEPLOYMENT.md`、必要时 `CHANGELOG.md` |
| `data/prompts/prompt_template.txt` | `MODULES.md`、必要时 `README.md` / `CHANGELOG.md` |

## 六、最常用判断法

如果懒得想，直接按下面的规则：

1. 改了调用链或数据流：先改 `ARCHITECTURE.md`
2. 改了函数、参数、环境变量：先改 `MODULES.md`
3. 改了启动、运维、排障：先改 `DEPLOYMENT.md`
4. 改了用户能感知到的功能：补改 `README.md`
5. 改了正式版本内容：补改 `CHANGELOG.md`
6. 改了验证脚本或踩坑经验：补改 `DEVNOTES.md`
7. 改了文档同步入口或知识库来源规则：补改 `knowledge.md`

## 七、最近补充的易漏项

1. 启动配置不是只改 `config.py` 就结束。
   `SERVER_HOST`、`SERVER_PORT`、`DEBUG_MODE` 这类变量如果由 Flask 入口消费，必须反查 `main.py` 是否仍有硬编码，并同步 `MODULES.md`，必要时同步 `DEPLOYMENT.md`。

2. 命令说明往往有两套文案。
   飞书卡片成功时用户看到的是卡片；卡片失败时用户看到的是文字 fallback。像 `/model` 这类新命令加入后，必须同时检查帮助卡片、帮助文本和各命令自己的 fallback 文案，否则会出现“功能已上线但帮助没写全”的文档回归。

3. 文档目录同步不能再按“文件名”理解。
   以后知识库同步要按 `docs/README.md`、`docs/subdir/xxx.md` 这种相对路径识别来源，不能只看 `README.md` 这种 basename。否则 `docs/` 下面一旦分子目录，就会出现来源撞名和错误覆盖。

4. 如果继续把入口编排往 `entrypoints/*` 或 `application/*` 下沉，`knowledge.md` 的“按代码文件反查文档”也要补上新文件映射；否则后续维护者还是会盯着过时入口看。

5. 如果新增统一观测或降级收口模块，例如 `app/observability.py`，不要只改 `/health`。
   至少要同步 `MODULES.md` 和 `DEPLOYMENT.md`，必要时补 `ARCHITECTURE.md`；否则排障时只能看到新字段，却不知道它来自哪一层、由哪些模块写入。

6. 如果新增 provider 级熔断或半开探测，不要只补环境变量表。
   还要同步 `ARCHITECTURE.md` 里的职责边界、`DEPLOYMENT.md` 里的 `/health` 排查口径，以及 `knowledge.md` 自己的代码文件映射；否则后续维护时只知道“有这个开关”，却不知道状态是谁维护、请求是在哪一层被跳过的。

7. 文档版本号也算同步内容。
   如果 `README.md`、`ARCHITECTURE.md`、`MODULES.md`、`DEPLOYMENT.md`、`CHANGELOG.md`、`DEVNOTES.md` 顶部的版本号不一致，要顺手统一，不要让文档头部落后于正文。

8. 改完 `docs/` 不等于知识库已经更新。
   文档提交前后，只要这次变更会影响 QA、项目说明或运维知识，就执行一次：

```bash
python scripts/ingest_knowledge.py --source-dir docs
```

9. 如果启动方式已经拆成“Web 进程 + scheduler 进程”，部署文档和巡检清单里的 PM2 进程名也要一起改。
   否则最容易出现代码已经拆成双进程，但文档还让人只重启旧进程，结果定时任务还跑着旧逻辑。

10. 如果新增的是“共享 snapshot + 多入口复用”的功能，例如 `/observe` + `/presence`。
   不要只改 `README.md` 的功能描述；至少还要同步 `ARCHITECTURE.md` 的调用链、`MODULES.md` 的新配置项和模块职责、`DEPLOYMENT.md` 的鉴权与排查口径，以及 `OBSERVATION_SYSTEM.md` 的扩展位设计。

11. 如果新增观察系统的未来媒体能力，即使还只是占位骨架，也要同步 `OBSERVATION_SYSTEM.md`。
   重点检查 `presence_snapshot.media_*` 字段、`/presence.media` 返回结构、`presence_runtime_state` 优先级，以及未来 worker 的 `pending -> ready/failed` 状态契约是否都写清楚。

## 八、提交前自检

提交涉及代码改动时，至少问自己 4 个问题：

1. 这次改动有没有改变调用链、职责边界或存储结构？
2. 这次改动有没有新增/删除参数、命令、环境变量或外部依赖？
3. 这次改动有没有改变部署方式、验证方式或用户可见行为？
4. 这次改动对应的 `docs/` 是否已经执行过一键同步入库？

只要前 3 个问题里任意一个答案是“有”，就不要只改代码，顺手把对应文档一起改掉。

如果第 4 个问题答案是“没有”，这次同步也还不算真正完成。
