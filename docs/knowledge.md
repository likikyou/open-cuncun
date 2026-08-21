# 文档同步清单

> 最后整理：2026-08-21
> 当前文档体系：`README.md` / `ARCHITECTURE.md` / `MODULES.md` / `DEPLOYMENT.md` / `CHANGELOG.md` / `DEVNOTES.md` / `OBSERVATION_SYSTEM.md` / `knowledge.md`

## 一、这份文件是干什么的

这份文件是维护者使用的文档变更速查表：代码变化后，可以据此判断哪些公开文档需要同步更新。

公开仓库当前不提供知识库导入或迁移脚本，也不把部署方的向量数据、私有人格材料或业务资料纳入版本控制。本文中的“同步”默认指 Git 中的文档同步，不代表已经更新某个部署环境的外部知识库。

## 二、公开仓库与外部知识库的边界

### 1. `docs/` 是公开项目文档的权威来源

架构、模块、部署和版本信息以 `docs/` 中的文件为准。提交前应更新对应文件，并运行仓库现有的本地验证入口：

```bash
python scripts/verify.py --offline
```

### 2. 外部材料与导入流程由部署方维护

私有人格资料、业务 FAQ、第三方材料以及向量数据库都属于部署侧资产。若部署环境需要把 `docs/` 或其他材料导入知识库，应在仓库外使用部署方自己的管道，并至少保证：

- 来源使用相对路径，避免同名文件互相覆盖
- 已删除或改名的来源会清理旧 chunk
- 私有材料、凭证和运行数据不会回写到公开仓库

公开仓库没有可执行的 `scripts/ingest_knowledge.py`，因此本文不会给出一个并不存在的通用导入命令。

### 3. 什么时候算“同步完成”

一次公开文档同步至少满足：

1. 代码相关文档已经更新
2. 仓库内的离线验证通过
3. 如果某个部署使用外部知识库，部署维护者另行运行并验证自己的导入管道

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
| `knowledge.md` | 文档同步规则、代码改动到文档的映射、公开仓库与外部知识库的边界 | 不写业务功能说明、部署细节、版本正文 |

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
- PM2 / 健康检查 / 备份相关脚本

必须同步：

- `DEPLOYMENT.md`

视情况同步：

- `DEVNOTES.md`
  当验证入口、排查命令、经验结论变化时
- `MODULES.md`
  当 `ops.py` / `bootstrap.py` / `entrypoints/scheduler_runner.py` 的函数行为或配置项变化时
- `README.md`
  当 3 步快速开始受影响时
- `knowledge.md`
  当公开文档同步规则或外部知识库边界变化时

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

必须同步：

- `ARCHITECTURE.md`
- `MODULES.md`

视情况同步：

- `DEPLOYMENT.md`
  当备份、迁移、路径或运维操作受影响时
- `CHANGELOG.md`
- `knowledge.md`
  当公开仓库与部署侧知识库的职责边界变化时

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
| `tests/*_smoke.py` | `DEVNOTES.md`、必要时 `DEPLOYMENT.md` / `CHANGELOG.md` |
| 部署侧知识库导入流程（仓库外） | `knowledge.md`、必要时 `DEPLOYMENT.md` |
| `data/prompts/example_prompt_template.txt` | `MODULES.md`、必要时 `README.md` / `CHANGELOG.md` |

## 六、最常用判断法

如果懒得想，直接按下面的规则：

1. 改了调用链或数据流：先改 `ARCHITECTURE.md`
2. 改了函数、参数、环境变量：先改 `MODULES.md`
3. 改了启动、运维、排障：先改 `DEPLOYMENT.md`
4. 改了用户能感知到的功能：补改 `README.md`
5. 改了正式版本内容：补改 `CHANGELOG.md`
6. 改了验证脚本或踩坑经验：补改 `DEVNOTES.md`
7. 改了文档同步规则或外部知识库边界：补改 `knowledge.md`

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

8. 改完 `docs/` 不等于部署侧知识库已经更新。
   公开仓库没有内置导入命令；使用外部知识库的部署应在仓库验证通过后，运行自己的导入管道并检查旧 chunk 是否清理。

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
4. 如果部署使用外部知识库，是否已经运行并验证部署侧导入管道？

只要前 3 个问题里任意一个答案是“有”，就不要只改代码，顺手把对应文档一起改掉。

第 4 项只适用于实际启用了外部知识库的部署，不是公开仓库的内置发布步骤。
