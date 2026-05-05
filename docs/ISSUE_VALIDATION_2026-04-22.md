# 2026-04-22 问题复核报告

## 结论总览

这批问题里，当前仓库中可以确认的真实问题有 5 类：

| 议题 | 结论 | 当前建议 |
| --- | --- | --- |
| 低成本 AI 链路未回写熔断状态 | 确认真实存在，且我已复现 `probe_in_flight` 被占住不释放 | 立即修 |
| `fastembed` 依赖缺失 | 确认真实存在，`pyproject.toml` 与 `uv.lock` 都缺 | 立即修 |
| 双 Flask app 实例 / 验证入口不一致 | 确认真实存在，`app.main.app is not wsgi.app` | 本周修 |
| 纯时间问句仍走流式卡片准备链路 | 确认真实存在，但影响低 | 顺手修 |
| 结构化日志 `service` 写死旧名 | 确认真实存在，但影响低 | 顺手修 |

另有 1 个点属于“架构边界而非当前缺陷”：

| 议题 | 结论 | 当前建议 |
| --- | --- | --- |
| 熔断器是进程内单例，跨多 worker 不共享 | 真实，但你当前文档和部署方式已经明确要求 `gunicorn -w 1` | 维持现状，补约束即可 |

---

## Findings

### 1. 高优先级：低成本 AI 链路会卡住 half-open probe

**结论**

这是当前项目里的真实 bug，而且不是“理论上可能”，我已经在仓库里按当前实现复现到了。

**涉及代码**

- `app/infrastructure/ai/provider_registry.py:158`
- `app/infrastructure/ai/provider_health.py:111-145`
- `app/application/memory_reflection_service.py:132-172`
- `app/application/reminder_service.py:5-10`
- `app/application/memory_maintenance_service.py:28,64`
- `app/application/post_reply_jobs.py:13`

**为什么它是真的**

1. `get_active_client()` 默认 `reserve_probe=True`，会在 provider 进入 `half_open` 时占用一次 probe。
2. `_call_ai_cheap()` 在 `app/application/memory_reflection_service.py:154-172` 里拿到 `client, model, provider_name` 后，直接裸调 `client.chat.completions.create(...)`。
3. 这条链路没有像主链 `app/ai_engine.py` 和共享网关 `app/infrastructure/ai/fallback_gateway.py` 那样调用 `record_provider_success()` / `record_provider_failure()`。
4. 因为没有 success/failure 回写，half-open probe 不会被释放；失败也不会进入熔断统计。

**我在本地的复现结果**

我把 `cerebras` 人工打到熔断开启，再把 `opened_until` 调成已到期，让它处于 `half_open_ready`。随后在不走 `ChatAnywhere` 的前提下调用 `_call_ai_cheap()`：

- 当底层请求失败时，调用结束后 circuit 状态变成 `state=half_open, probe_in_flight=True`
- 当底层请求成功时，调用结束后依然是 `state=half_open, probe_in_flight=True`

也就是说，这不是只在异常路径发生，成功路径一样会把 probe 卡住。

**对你这个“私有化 AI 聊天伴侣”项目的实际影响**

- 提醒任务会走这条低成本链路
- 回复后的反思会走这条低成本链路
- 记忆整合也会走这条低成本链路
- 一旦踩中 half-open probe，provider 会长期停在 `circuit_half_open_probe_in_flight`
- `/health` 里的 `ai_circuit` 会失真
- 这类任务大多是后台任务，出问题后更隐蔽，不容易第一时间被主聊天链路发现

**建议怎么修**

优先推荐把 `_call_ai_cheap()` 收口到共享网关，而不是继续裸调：

- 最好复用 `call_with_fallback(...)`，让 success/failure/fallback 统计统一收口
- 如果暂时不改成共享网关，至少在 `_call_ai_cheap()` 里补上 `record_provider_success()` / `record_provider_failure()`

**项目定制建议**

你这里其实不一定要先做“解析 provider 再慢慢处理”。当前 `_call_ai_cheap()` 从拿到 provider 到发请求几乎没有额外阶段，因此最务实的修法就是：

- 保持真实请求前才占用 probe
- 请求结束后无论成功还是失败都明确回写状态

如果未来这条链路要先做额外解析、打点、排队，再真正发请求，那时再把“解析阶段 `reserve_probe=False`、真正发请求时再占 probe”拆开更合适。

---

### 2. 高优先级：`fastembed` 依赖确实漏了，干净环境部署会炸

**结论**

这是当前仓库的真实问题，而且是典型的“你本机能跑，别人新环境会炸”的问题。

**涉及代码**

- `app/retrieval.py:12`
- `pyproject.toml:10-136`
- `uv.lock`

**为什么它是真的**

1. `app/retrieval.py` 明确有 `from fastembed import TextEmbedding`
2. `pyproject.toml` 的 `dependencies` 里没有 `fastembed`
3. `uv.lock` 里也搜不到 `fastembed`
4. 文档里已经把 FastEmbed 当成正式方案在讲，说明这不是实验代码，而是当前主实现的一部分

**当前状态判断**

- 你现在这台机器的 Python 环境里确实已经装了 `fastembed`
- 但这并不能说明项目依赖声明正确
- 只要换一台干净机器执行 `uv sync`，当前锁文件不会把 `fastembed` 安装进去

**对你项目的实际影响**

这个项目是私有化部署、自己维护环境的，最容易踩到的不是日常开发，而是：

- 新机器恢复
- 重建 `.venv`
- CI / 验证环境
- 其他协作者拉代码本地跑

一旦环境里没有手工残留的 `fastembed`，`app.retrieval` 导入就会直接失败。

**建议怎么修**

- 在 `pyproject.toml` 中补 `fastembed`
- 更新 `uv.lock`
- 如果你还保留 `requirements.txt` 作为备用安装方式，也建议同步

**建议级别**

这条建议排到“立即修”，因为它影响的是仓库可部署性和可恢复性。

---

### 3. 中高优先级：当前确实存在“双 Flask app 实例”，验证入口和生产入口不是同一个对象

**结论**

这是当前仓库里的真实问题，且我已经直接验证过。

**涉及代码**

- `app/main.py:23-66`
- `wsgi.py:3-7`
- `run.py:6`
- `scripts/verify.py:1121-1127`
- `docs/DEPLOYMENT.md:144-148`

**为什么它是真的**

1. `app/main.py` 模块导入时会执行 `app = create_app()`
2. `wsgi.py` 又执行了一次 `app = create_app()`
3. `scripts/verify.py` 检查的是 `from app.main import app`
4. Gunicorn 实际跑的是 `wsgi:app`

我本地直接执行后，结果是：

- `app.main.app is wsgi.app` 为 `False`
- `app.main.app.extensions["processed_ids"] is wsgi.app.extensions["processed_ids"]` 也为 `False`

也就是说，当前“验证通过的 app”和“生产实际跑的 app”不是同一个实例。

**对你项目的实际影响**

这个项目不是纯无状态 Flask 壳子，`processed_ids` 已经是 app 级状态了。当前后果包括：

- 离线验证并没有真正覆盖生产入口对象
- 以后如果给 app 挂扩展、middleware、hook、缓存，极容易只改到其中一个实例
- 文档对 `scripts/verify.py --offline` 的表述比真实覆盖范围更大

**和“WSGI 初始化顺序倒置”这条的关系**

你提到的初始化顺序风险本质上是成立的，但要注意一个关键细节：

- 仅仅把 `wsgi.py` 里的 `initialize_runtime()` 和 `app = create_app()` 两行顺序对调，并不能彻底解决问题
- 因为只要 `wsgi.py` 还是 `from app.main import create_app`，导入 `app.main` 时就已经先执行了模块级 `app = create_app()`

所以，这里真正要解决的不是“换两行顺序”这么简单，而是“收敛 canonical app”。

**更适合你项目的修法**

有两个可选方向：

**方案 A：低风险短修**

- `wsgi.py` 先执行 `initialize_runtime(...)`
- 然后再 `from app.main import app`
- 不再在 `wsgi.py` 里二次 `create_app()`

这个方案能让生产 WSGI 入口和 `app.main.app` 统一到同一个对象，也顺带避免 WSGI 侧的初始化顺序问题。

**方案 B：长期更干净**

- 移除 `app.main` 的模块级 `app = create_app()`
- `app.main` 只保留纯 factory
- `run.py` / `wsgi.py` 各自在 runtime 初始化后显式创建 app
- `scripts/verify.py` 增加对 `wsgi.app` 和 `run_scheduler.main` 的入口级 smoke

如果按“长期维护最省心”来选，我更推荐方案 B。

**建议级别**

这一条不像 probe 卡死那样会直接影响每次后台任务，但它会持续削弱你对“验证结果=生产入口”的信心，建议本周修掉。

---

### 4. 低优先级：纯时间问句确实存在“幽灵流式卡片”开销

**结论**

这是当前实现里的真实低优先级问题。

**涉及代码**

- `app/application/reply_service.py:65-109`
- `app/infrastructure/feishu/card_streamer.py:216-245`

**为什么它是真的**

`generate_reply()` 在判断 `direct_current_time_reply` 之前，就已经：

- 创建了 `card_id_queue`
- 启动了 `prepare_streaming_card` 后台线程

然后命中纯时间问句时：

- 用 `iter([build_current_time_reply(user_text)])` 包了一次本地字符串
- `first_chunk = next(ai_iterator)` 把迭代器取空
- 后面仍然会继续调用 `stream_reply_fn(...)`

我本地按依赖注入统计过一次，纯时间问句时：

- `prepare_streaming_card` 被调用了 1 次
- `stream_reply` 也被调用了 1 次

说明它确实没有走“纯本地文本快路径”。

**对你项目的实际影响**

这是低优先级，不会导致错误回复，但会带来：

- 额外的飞书卡片创建尝试
- 额外线程与日志噪音
- 纯本地秒回场景仍绕一层复杂流式逻辑

**更适合当前项目的修法**

不一定非要在 `generate_reply()` 里直接调用 `send_feishu()`。

更贴近你当前结构的修法是：

- 纯时间问句时，不要启动 `prepare_streaming_card` 线程
- 直接走“普通文本单次发送”路径

这样能复用现有投递层，又不会把 `generate_reply()` 的职责继续扩张。

**建议级别**

顺手修即可，放在前面几条之后。

---

### 5. 低优先级：结构化日志里的 `service` 字段确实写死了旧名字

**结论**

这是个真实但低风险的问题。

**涉及代码**

- `app/logger.py:49-58`
- `docs/README.md:179-190`
- `docs/DEPLOYMENT.md:115-128`

**为什么它是真的**

- 文档和 PM2 进程名已经拆成 `feishu-companion-web` / `feishu-companion-scheduler`
- 但 JSON 日志里 `service` 仍固定是 `"feishu-companion"`

这会导致部署层和日志字段不一致。

**对你项目的实际影响**

对这种自托管双进程项目来说，日志可区分性很重要。现在的问题是：

- 看 PM2 是两个进程
- 看日志却像一个旧服务名
- 做日志聚合、告警过滤、线上排障时会增加辨认成本

**建议怎么修**

最小可行方案：

- 让 `service` 读取环境变量，例如 `SERVICE_NAME`
- PM2 启动 `feishu-companion-web` 时注入 `SERVICE_NAME=feishu-companion-web`
- PM2 启动 scheduler 时注入 `SERVICE_NAME=feishu-companion-scheduler`

如果短期不改代码，至少应在部署文档里明确说明日志字段仍沿用旧名，避免误判。

---

## 当前不属于“必须改代码”的项

### 6. Info：熔断器是进程内单例，这个边界真实存在，但你当前部署前提下可接受

**结论**

这是一个真实的架构边界，不是误报。但在你当前文档明确要求 `gunicorn -w 1` 的前提下，它不是眼前最需要改代码的问题。

**依据**

- 熔断状态保存在 `app/infrastructure/ai/provider_health.py` 的 `_CIRCUITS`
- 文档 `docs/DEPLOYMENT.md:127-128` 和 `docs/README.md:189-190` 已经明确说明当前建议单 worker

**我的判断**

对你这个“私有化、单机、PM2、自维护”的项目来说：

- 只要继续坚持单 worker Web 进程
- scheduler 也继续独立进程

那么这个 in-memory circuit 设计是成立的。

**建议**

暂时不用为它做 Redis/SQLite 级别的跨进程共享熔断。

如果要补强，优先做的是：

- 在部署文档里继续强调 `-w 1`
- 有条件的话，在健康检查或启动日志里显式提示“多 worker 会导致熔断状态分裂”

---

## 项目优先级建议

### 第一批：建议立即处理

1. `_call_ai_cheap()` 熔断状态回写缺失
2. `fastembed` 依赖声明与锁文件缺失

这两条一条影响运行稳定性，一条影响可部署性，优先级最高。

### 第二批：建议本周处理

1. 收敛 canonical app，消除 `app.main.app` 与 `wsgi.app` 双实例
2. 给 `scripts/verify.py` 增加 `wsgi.app` 与 `run_scheduler.main` smoke

这组问题的核心不是“现在一定挂”，而是“当前验证链对生产入口覆盖不足”。

### 第三批：可以顺手完善

1. 纯时间问句改成真正的本地文本快路径
2. 结构化日志 `service` 改为按入口可配置

---

## 我建议你补进验证链的 4 个冒烟项

### 1. Half-open probe 释放验证

增加一个离线测试：

- 先把某 provider 打到 `half_open_ready`
- 走一次低成本 AI 入口
- 成功后断言 probe 被释放
- 失败后断言 probe 被释放且失败计数进入熔断统计

### 2. `wsgi.app` 入口烟测

至少补一条：

- `import wsgi`
- 断言 `wsgi.app` 可创建
- 断言关键路由存在

如果你保留双入口结构，最好再断言它与主验证入口是否为同一个对象。

### 3. `run_scheduler.main` 烟测

建议用 patch 把无限循环替掉，只验证：

- `initialize_runtime()` 会先调用
- `run_scheduler()` 会后调用

### 4. 纯时间问句不创建卡片

当前 `scripts/verify.py` 已经测了“纯时间问句不走 AI”，但还没测：

- 不创建流式卡片
- 不起卡片预热线程
- 直接走普通文本投递

---

## 最终判断

如果按“现在就该动手修哪些”来排序，我的结论是：

1. **必须修**：低成本 AI 熔断回写缺失、`fastembed` 依赖声明缺失
2. **建议尽快修**：双 app 实例 / 入口验证不一致
3. **建议完善**：纯时间问句快路径、日志 `service` 可配置
4. **当前不用大改**：进程内熔断器的跨 worker 边界，只要继续坚持 `gunicorn -w 1`

换句话说，你收到的这批问题里，大方向判断是靠谱的，其中最需要你马上处理的不是文档层面的描述，而是：

- 后台低成本 AI 链路对熔断器状态机的破坏
- 打包依赖声明和锁文件不一致

这两条是会在真实运行和真实部署里给你制造麻烦的。
