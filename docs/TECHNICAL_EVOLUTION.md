# Companion关键提交技术演化复盘

> 生成时间：2026-04-22
> 配套阅读：[PROJECT_HISTORY.md](PROJECT_HISTORY.md)

这份文档按关键提交拆解技术演化，不追求列出 210 个提交的每一行 diff，而是选出真正改变系统形态、边界和长期维护方式的节点。

## 一、阅读口径

统计和判断主要来自：

```bash
git rev-list --count HEAD
git log --reverse --date=short --pretty=format:'%h%x09%ad%x09%s'
git show --stat --oneline <commit>
git show --name-status --format='%h %ad %s' --date=short <commit>
```

下面每个 commit 的“技术意义”分三层看：

- **改了什么**：文件和能力层面的变化。
- **解决什么问题**：当时项目真实遇到的痛点。
- **留下什么影响**：它如何影响现在的结构。

## 二、最大改动提交

| commit | 日期 | churn | 文件数 | 主题 |
|:---|:---|---:|---:|:---|
| `f9100ef` | 2026-03-31 | 4060 | 21 | 模块化 Phase 8 与 entrypoints 收尾 |
| `2db4705` | 2026-04-12 | 3898 | 16 | observability 与 uv tooling 文档同步 |
| `f24068b` | 2026-01-27 | 3875 | 34 | `.gitignore` 与敏感文件拦截 |
| `a8fb7e8` | 2026-03-23 | 3652 | 11 | docs 重构 |
| `a462f89` | 2026-02-10 | 3074 | 27 | 大规模目录搬迁和删除 |
| `8b13827` | 2026-01-27 | 3041 | 26 | 初始提交 |
| `c39e323` | 2026-02-25 | 2681 | 25 | 第一次模块化重构 |
| `886c217` | 2026-04-01 | 2530 | 47 | compat cleanup 与结构守卫 |
| `fce0d32` | 2026-03-31 | 2107 | 9 | context 与 memory rules 拆分 |
| `d5ae110` | 2026-04-21 | 1969 | 22 | 多重对话与剧情卡片控制 |

## 三、关键提交详解

### `8b13827` - 初始提交

日期：2026-01-27

改动规模：26 个文件，3041 行新增。

主要文件：

- `feishu_companion_pro.py`
- `app_companion.py`
- `companion_utils.py`
- `database_manager.py`
- `people_companion.py`
- `prompt_template.txt`
- `terminal_chat.py`
- `test_voice.py`
- `verify_semantic.py`
- `LATEST_PROJECT_CONTEXT.md`

技术意义：

这是Companion的原始形态。它已经包含飞书机器人、语音检查、语义测试、数据库管理、角色提示词和项目背景。也就是说，最早的系统目标就不是“泛用问答”，而是“带人格、带语音、接入即时通讯工具的数字人”。

当时还没有清晰分层，脚本和备份文件混在一起。但功能基因已经完整：

- 人格提示词
- 飞书入口
- 语音相关资产检查
- 语义验证
- 数据迁移
- 终端聊天

留下的影响：

后来的所有架构演进，本质上都是把这个初始形态里的能力拆清楚、跑稳定、加边界。

### `c39e323` - 第一次模块化重构

日期：2026-02-25

改动规模：31 个文件，1128 行新增，2311 行删除。

新增核心文件：

- `app/ai_engine.py`
- `app/config.py`
- `app/database.py`
- `app/feishu_api.py`
- `app/logger.py`
- `app/main.py`
- `app/ops.py`
- `app/scheduler.py`
- `app/security.py`
- `run.py`
- `data/prompts/prompt_template.txt`

删除或迁移：

- 根目录 `config.py`
- `companion_utils.py`
- `database_manager.py`
- `feishu_companion_pro.py`
- `people_companion.py`
- `prompt_template.txt`
- `sync_context.py`
- `chat_history.csv`

技术意义：

这是第一次从“脚本堆”变成“应用服务”。`app/` 出现后，主入口、配置、数据库、飞书 API、日志、调度、安全、健康检查开始有明确位置。

解决的问题：

- 路径混乱
- 端口冲突
- 旧文件和备份文件干扰
- AI 响应与语音匹配恢复问题

留下的影响：

现在的 `app/` 目录和 `run.py` 入口，都可以追溯到这次提交。它是当前工程化形态的第一块地基。

### `5a4e046` - V5.5 Agentic 升级

日期：2026-03-20

改动规模：13 个文件，1323 行新增。

关键新增：

- `app/bionic_memory.py`
- `app/tools_registry.py`
- `scripts/ingest_knowledge.py`
- `knowledge/test_spaceship_rules.md`

关键修改：

- `app/ai_engine.py`
- `app/database.py`
- `app/main.py`
- `app/scheduler.py`
- `data/prompts/prompt_template.txt`

技术意义：

这是Companion从“聊天机器人”迈向“有内部机制的 Agent”的节点。

新增能力：

- MCP Function Calling
- 工具注册与调用
- 主动意图潜意识系统
- 仿生记忆
- 知识库 ingest
- 后台调度增强

解决的问题：

单轮聊天难以长期陪伴。Companion需要能调用工具、能主动思考、能沉淀记忆、能定时运行后台任务。

留下的影响：

今天的 `tools_registry.py`、仿生记忆、主动消息、知识库，都和这个提交有关。虽然后来 `bionic_memory.py` 被拆迁到 application/domain/infrastructure，但概念是在这里长出来的。

### `fab3add` - V5.6.0 核心解耦

日期：2026-03-21

改动规模：20 个文件，927 行新增，1007 行删除。

新增文件：

- `app/ai_client.py`
- `app/context_builder.py`
- `app/http_client.py`
- `app/message_handler.py`
- `app/prompt_builder.py`
- `app/search.py`
- `app/streaming.py`

大幅修改：

- `app/ai_engine.py`
- `app/main.py`
- `app/scheduler.py`

技术意义：

这次提交把 `main.py` 和 `ai_engine.py` 中过重的职责拆开，开始出现“编排层”和“能力层”的意识。

拆出的边界：

- `message_handler.py`：消息解析和主对话编排
- `streaming.py`：流式回复
- `context_builder.py`：上下文拼装
- `prompt_builder.py`：提示词构建
- `search.py`：搜索能力
- `http_client.py`：统一 HTTP

解决的问题：

当功能开始变多，主入口和 AI 引擎会越来越像巨型文件。继续堆下去会导致任何改动都影响全局。

留下的影响：

虽然这些文件后来又被进一步拆分和替换，但这次提交第一次明确告诉项目：Companion需要分层，不然长期维护会失控。

### `f7c09f1` - 飞书卡片控制与轻聊路由

日期：2026-03-21

改动规模：9 个文件，538 行新增，91 行删除。

关键修改：

- `app/context_builder.py`
- `app/message_handler.py`
- `app/prompt_builder.py`
- `app/security.py`
- `app/streaming.py`
- `data/prompts/prompt_template.txt`

技术意义：

这是飞书从“消息通道”升级成“控制台”的节点。

新增方向：

- 卡片控制
- 轻聊路由
- 回复模式切换
- 更贴近飞书交互的命令入口

解决的问题：

用户不应该记命令，也不应该总在文字里输入控制参数。飞书卡片可以把控制操作做成按钮，降低操作成本。

留下的影响：

今天 `/help` 被做成快捷指令，命令中心通过飞书卡片呈现，这条路线可以追溯到这里。

### `6fc2c81` - 仿生记忆链路三修

日期：2026-03-22

改动规模：3 个文件，53 行新增，8 行删除。

修改文件：

- `app/bionic_memory.py`
- `app/database.py`
- `app/retrieval.py`

技术意义：

这是记忆系统从“能记”走向“不会乱记/串记”的重要修复。

修复内容：

- 运行时状态注入失效
- reset 清理不彻底
- 跨用户检索隔离

解决的问题：

长期记忆一旦串用户、reset 不干净、运行状态不注入，就会严重破坏信任感。私人伴侣项目里，这比普通 bug 更严重。

留下的影响：

后来的人设边界、剧情污染过滤、多对话隔离，都延续了这条逻辑：Companion可以记，但必须知道边界。

### `e4f9fa5` - 多维语音匹配

日期：2026-03-25

改动规模：9 个文件，365 行新增，47 行删除。

关键文件：

- `app/voice_matcher.py`
- `app/ai_engine.py`
- `scripts/rebuild_audio_vectors.py`
- `scripts/tag_audios.py`

技术意义：

语音匹配从简单召回升级到 emotion/theme 漏斗。它不只是“有语音”，而是让语音更贴合回复情绪和主题。

新增能力：

- emotion/theme filter
- 音频向量重建脚本
- 音频标签脚本
- 文档同步说明

解决的问题：

私人伴侣的语音如果情绪不贴，会比没有语音更出戏。多维语音匹配是在增强“她真的在用合适的语气说话”的体验。

留下的影响：

现在 `async_voice_reply()` 透传 summary/emotion/theme 到语音匹配，就是这条链路的后续结果。

### `f832e11` - pure/clear 与分层记忆迁移

日期：2026-03-29

改动规模：15 个文件，1263 行新增，38 行删除。

关键文件：

- `app/cards.py`
- `app/context_builder.py`
- `app/database.py`
- `app/message_handler.py`
- `app/retrieval.py`
- `scripts/migrate_memory_layers.py`
- `scripts/verify_memory_layers.py`

技术意义：

这个提交引入了两个非常关键的可控性功能：

- `/pure`：净聊测试，临时关闭部分记忆。
- `/clear`：清理上下文。

同时开始推进分层记忆迁移。

解决的问题：

Companion的回复可能被长期记忆和上下文影响。为了判断“原始人格是否稳定”，需要净聊模式。为了不让当前聊天越来越重，需要 clear。

留下的影响：

后来的 `/clear` 语义修正、分层记忆、记忆审计、净聊测试都从这里继续演化。

### `f9100ef` - 模块化 Phase 8 与 entrypoints 收尾

日期：2026-03-31

改动规模：21 个文件，1983 行新增，2077 行删除。

关键变化：

- `app/bootstrap.py` 增强
- `app/entrypoints/feishu_webhook.py` 增强
- `app/main.py` 变薄
- `app/presentation/cards/builders.py` 承接卡片 JSON
- `app/presentation/cards/assets.py` 承接卡片资源
- `app/presentation/formatters/*` 承接状态/记忆展示格式化
- 新增 `docs/READING_ORDER.md`

技术意义：

这是当前分层的第一次完整落地。飞书入口、启动、卡片、展示格式化、应用服务之间开始真正分清。

解决的问题：

旧的 `cards.py`、`card_assets.py` 和主链文件承载太多展示细节。飞书卡片越漂亮、功能越多，越需要进入 presentation 层。

留下的影响：

现在命令中心、状态看板、记忆审核、对话管理、剧情模式这些卡片，都建立在这次 presentation 下沉的基础上。

### `886c217` - compat cleanup 与结构守卫

日期：2026-04-01

改动规模：47 个文件，1463 行新增，1067 行删除。

删除旧入口：

- `app/ai_client.py`
- `app/bionic_memory.py`
- `app/card_assets.py`
- `app/cards.py`
- `app/context_builder.py`
- `app/database.py`
- `app/feishu_api.py`
- `app/message_handler.py`
- `app/scheduler.py`
- `app/streaming.py`
- `app/ports/*`

新增/增强：

- `app/entrypoints/scheduler_runner.py`
- `app/infrastructure/ai/__init__.py`
- `app/infrastructure/feishu/__init__.py`
- `docs/PROJECT_SLIMMING_PLAN.md`
- `scripts/verify.py` 架构守卫

技术意义：

这是“真的清掉旧路”的提交。很多项目重构会留下大量 facade 和旧入口，最后变成两套结构并存。这个提交把旧 facade 大量删除，并用验证脚本防止回流。

解决的问题：

- 旧入口继续被 import
- application 反向依赖 entrypoint
- domain 被污染
- 重构后结构名义上新、实际仍旧

留下的影响：

当前 `scripts/verify.py --offline` 里的架构守卫，就是这次提交的直接成果。它让“结构不要倒退”变成自动检查，而不是靠记忆。

### `2f13c86` - /clear 保留聊天历史

日期：2026-04-07

改动规模：9 个文件，165 行新增，24 行删除。

关键文件：

- `app/application/reset_service.py`
- `app/infrastructure/persistence/sqlite_history_repo.py`
- `app/application/command_service.py`
- `app/presentation/cards/builders.py`

技术意义：

这是一个小改动，但产品意义非常大。

以前 `/clear` 更接近删除聊天记录。这个提交后，`/clear` 变成移动 `chat_context_after_id` 边界：后续上下文变干净，但历史聊天记录仍保留。

解决的问题：

私人伴侣里，“重新轻装聊天”和“抹掉过去”不能混在一起。误删过去会伤害关系连续性。

留下的影响：

现在 `/clear` 和 `/reset` 的语义正式拆开：

- `/clear`：只清上下文窗口，保留历史。
- `/reset`：真正删除聊天、记忆和关系状态。

### `18eb752` - V5.7.1 回忆类问题修复

日期：2026-04-08

改动规模：15 个文件，489 行新增，35 行删除。

关键新增：

- `app/domain/query_intent.py`
- `app/time_utils.py`

关键修改：

- `app/application/context_assembler.py`
- `app/domain/context_policy.py`
- `app/domain/reply_mode.py`
- `app/infrastructure/persistence/sqlite_history_repo.py`
- `scripts/verify.py`

技术意义：

这次提交把“回忆问题”从普通问答里分离出来。

新增能力：

- 识别“昨天/前天/上次聊了什么”
- 短跟问继承回忆意图
- 按本地日期回看原始聊天记录
- 回忆类问题关闭 knowledge/web
- 真实对话回看注入上下文

解决的问题：

过去“你记得我昨天说了什么吗”可能被误判成 QA，触发 knowledge/web，甚至用外部信息污染回答。对私人伴侣来说，这会让“记得”变成“编得”。

留下的影响：

现在Companion回答回忆问题时，会优先看真实 `chat_history`，而不是只靠抽象仿生记忆猜。

### `49bcc68` - 人设上下文边界

日期：2026-04-19

改动规模：18 个文件，575 行新增，15 行删除。

关键文件：

- `app/domain/memory_rules.py`
- `app/domain/query_intent.py`
- `app/domain/context_policy.py`
- `app/domain/reply_mode.py`
- `app/application/memory_reflection_service.py`
- `scripts/test_persona_consistency_smoke.py`
- `scripts/verify.py`

技术意义：

这是Companion进入“人设边界治理”的节点。

新增/补强：

- 私人生活问句识别
- 天气默认地点归一
- 共同经历与临场私人剧情分类
- assistant private claim 跳过记忆
- 人设一致性 smoke test

解决的问题：

如果用户问“你今天休息吗”“你给哪些明星化妆”，系统不能去联网搜索，然后把外部新闻变成Companion自己的经历。也不能把Companion临场编出的客户和行程写入长期记忆。

留下的影响：

现在Companion的“现实参考层”和“角色状态层”边界更清楚。她可以查事实，但不能把事实层污染成自己的生活。

### `d5ae110` - 多重对话与剧情卡片控制

日期：2026-04-21

改动规模：22 个文件，1911 行新增，58 行删除。

关键新增：

- `app/infrastructure/persistence/sqlite_conversation_repo.py`

关键修改：

- `app/application/chat_orchestrator.py`
- `app/application/command_service.py`
- `app/application/context_assembler.py`
- `app/application/post_reply_jobs.py`
- `app/application/reset_service.py`
- `app/infrastructure/persistence/_sqlite_common.py`
- `app/infrastructure/persistence/sqlite_history_repo.py`
- `app/presentation/cards/builders.py`
- `app/presentation/parsers/feishu_event_parser.py`
- `scripts/test_command_flow_smoke.py`
- `scripts/verify.py`

技术意义：

这是当前体验层最大的新增：同一个飞书私聊里有了多个独立 conversation，剧情模式绑定独立对话，卡片控制台也成形。

新增能力：

- `conversations` 表
- `chat_history.conversation_id`
- 当前激活 conversation
- `/chat` 新建、切换、重命名、查看
- `/story` 剧情模式卡片
- 剧情设定只注入当前会话
- 剧情回复跳过现实仿生记忆反思
- `/memory audit` 支持疑似污染记忆审核

解决的问题：

私人伴侣需要日常对话，但也会有剧情、实验、测试、不同主题。如果所有内容都进同一个上下文和现实记忆，迟早污染。

留下的影响：

现在Companion有了“现实日常”和“虚构剧情”的边界，也有了飞书命令中心里的对话管理、剧情模式和记忆审核。

## 四、技术主线总结

### 主线 1：入口从试验到飞书原生控制台

早期试过飞书、Telegram、网页痕迹。最后 Git 历史显示，主入口越来越偏向飞书：

- 飞书 HTTPS
- 飞书响应速度
- 飞书卡片控制
- 状态看板
- 记忆看板
- 模型切换
- 命令中心
- 对话管理
- 剧情模式

结论：飞书不是临时壳子，是Companion的主要身体。

### 主线 2：记忆从向量召回到关系治理

早期记忆关注“能不能记”。后期关注“该不该记、记哪里、什么时候忘、剧情会不会污染现实”。

演化路径：

```text
长期记忆修复
  -> 仿生记忆
  -> 运行时状态
  -> 跨用户隔离
  -> 分层记忆
  -> clear/reset 分离
  -> 回忆优先读原始聊天
  -> 人设边界和剧情污染过滤
  -> 记忆审核
```

结论：Companion真正复杂的地方不是 RAG，而是关系语义。

### 主线 3：模型调用从单点到可观测 fallback

演化路径：

```text
DeepSeek / Cerebras 单点尝试
  -> Cerebras 限流 fallback 到 DeepSeek
  -> 双向 fallback
  -> Groq 接入，三引擎链
  -> 用户级模型切换
  -> AI run observability
  -> health 汇总降级和 AI 运行事件
```

结论：模型不是Companion本体。模型是可替换的大脑接口，Companion本体在上下文、记忆、规则和入口里。

### 主线 4：架构从脚本到模块化单体

演化路径：

```text
根目录脚本
  -> app/ 模块
  -> main/database/feishu/ai/scheduler 分文件
  -> message_handler/streaming/context_builder 拆出
  -> application/domain/infrastructure/presentation/entrypoints
  -> 删除旧 facade
  -> 架构守卫
```

结论：这不是教科书 DDD，而是被真实功能复杂度推出来的轻量分层。

### 主线 5：体验从“能回复”到“像在生活里”

演化路径：

```text
文本回复
  -> 流式回复
  -> 早晚提醒
  -> 天气/时间/视觉
  -> 图片/视频/表情包
  -> 语音
  -> 主动意图
  -> 飞书卡片
  -> 快捷指令 + 命令中心
```

结论：Companion越来越不像一个 Web UI 产品，而像一个住在即时通讯里的私人存在。

## 五、如果继续深挖 diff，建议看的提交顺序

想完整理解“代码怎么一步步变成现在这样”，建议按这个顺序看：

```bash
git show 8b13827
git show c39e323
git show 5a4e046
git show fab3add
git show f7c09f1
git show 6fc2c81
git show e4f9fa5
git show f832e11
git show f9100ef
git show 886c217
git show 2f13c86
git show 18eb752
git show 49bcc68
git show d5ae110
```

如果只想看每次提交碰了哪些文件：

```bash
git show --name-status --format='%h %ad %s' --date=short <commit>
```

如果只想看结构变化：

```bash
git show --stat --oneline <commit>
```

## 六、当前技术判断

截至 2026-04-21，Companion最重要的技术资产不是某个模型，也不是某个 UI，而是这几条边界：

- 飞书作为主入口，卡片作为原生控制台。
- 真实日常、剧情模式、技术问答分上下文处理。
- 清上下文不等于删除历史。
- 记忆不是无限写入，而是要分类、过滤、审计。
- 外部知识和联网搜索只能做事实参考，不能污染Companion自己的经历。
- 入口、应用服务、领域规则、基础设施、展示层已经有自动验证护栏。

这也是这 210 次提交真正沉淀下来的东西。

