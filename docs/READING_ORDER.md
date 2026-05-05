# Feishu AI Companion 阅读顺序

> 面向第一次接手这个仓库的人。目标是尽快回答三件事：请求从哪里进来、业务在哪里编排、外部依赖从哪里接入。

## 一、先看总图

1. [README.md](README.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [MODULES.md](MODULES.md)

## 二、先建立一个最重要的心智模型

第一次接手时，请先把文件分成两类：

- 运行入口和稳定底座：`main / bootstrap / ai_engine`
- 真正实现多数在 `entrypoints / application / presentation / infrastructure / domain`

所以第一遍阅读的原则是：

1. 入口层先看“它把你带到哪条真实链路”
2. 真实业务重点看实现层
3. 一次只追一条链，不要横向扫完整个目录

## 三、理解飞书消息主链

1. `app/main.py`
   先确认 Flask app、路由和兼容导出还在这里。
2. `app/bootstrap.py`
   看启动初始化、资产预热和调度线程是怎么起来的。
3. `app/entrypoints/feishu_webhook.py`
   看 challenge、验签、解密、去重和异步投递。
4. `app/application/chat_orchestrator.py`
   看普通对话如何串行化、何时读历史、何时写库、何时触发后台任务。
5. `app/presentation/parsers/feishu_event_parser.py`
   看文本、图片、sticker、卡片回调如何被归一化。
6. `app/application/command_service.py`
   看 `/status /reply /model /memory /reset /clear /pure /help` 的处理边界。

阅读提示：

- 真正的聊天主编排重点在 `app/application/chat_orchestrator.py`。

## 四、理解回复生成链

1. `app/application/reply_service.py`
   看 prompt、流式首包、卡片预创建、摘要提炼的真实编排。
2. `app/ai_engine.py`
   看 LLM 请求、工具调用循环和摘要提炼契约。
3. `app/application/context_assembler.py`
4. `app/domain/reply_mode.py`
5. `app/domain/context_policy.py`
6. `app/infrastructure/feishu/card_streamer.py`

阅读提示：

- `app/ai_engine.py` 只先抓 `build_messages -> model call -> tool loop -> stream/fallback` 这条骨架。

## 五、理解展示层

1. `app/presentation/cards/builders.py`
   所有命令卡片 JSON 都在这里。
2. `app/presentation/cards/assets.py`
   看卡片主图查找、缓存、预热与上传策略注入。
3. `app/presentation/formatters/status_formatter.py`
4. `app/presentation/formatters/memory_formatter.py`

## 六、理解记忆与重置

1. `app/application/memory_reflection_service.py`
2. `app/application/memory_maintenance_service.py`
3. `app/domain/memory_rules.py`
4. `app/application/reset_service.py`
5. `app/infrastructure/persistence/_sqlite_common.py`
6. `app/infrastructure/persistence/sqlite_memory_repo.py`
7. `app/infrastructure/persistence/sqlite_profile_repo.py`
8. `app/infrastructure/persistence/sqlite_history_repo.py`
9. `app/infrastructure/vector/chroma_memory_store.py`

阅读提示：

- 真正的重置边界重点看 `app/application/reset_service.py`。

## 七、理解调度链

1. `app/entrypoints/scheduler_runner.py`
2. `app/application/reminder_service.py`
3. `app/application/proactive_chat_service.py`
4. `app/application/memory_maintenance_service.py`

## 八、理解基础设施接入

1. `app/infrastructure/feishu/__init__.py`
   先认出现在 Feishu 公共导出入口已经在基础设施包内部。
2. `app/infrastructure/feishu/client.py`
3. `app/infrastructure/feishu/messenger.py`
4. `app/infrastructure/feishu/media_store.py`
5. `app/infrastructure/ai/__init__.py`
6. `app/infrastructure/ai/provider_registry.py`
7. `app/infrastructure/ai/fallback_gateway.py`

## 九、最后再看这些稳定底座

1. `app/prompt_builder.py`
2. `app/retrieval.py`
3. `app/voice_matcher.py`
4. `app/search.py`
5. `app/weather.py`
6. `app/security.py`
7. `app/http_client.py`
8. `app/time_utils.py`

## 十、第一次阅读时可以先跳过的东西

- 大段卡片 JSON
- `deps={...}` 的注入细节
- 各种兼容 re-export
- 向量库初始化和底层存储细节

先把一条业务链讲顺，再回来补这些实现细节。

## 十一、阅读时的两个提醒

- `.prompts/` 是开发协作提示词，不是运行时人格提示词。
- 运行时人格提示词在 `data/prompts/prompt_template.txt`，由 `app/prompt_builder.py` 热加载。
