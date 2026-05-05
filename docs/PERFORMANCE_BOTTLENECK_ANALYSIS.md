# 🔍 Feishu AI Companion 主耗时链路分析与优化建议

> **分析日期**：2026-04-23  
> **数据来源**：真实生产日志（2026-04-22/23）+ 全链路代码审读  
> **状态**：待优化

---

## 📊 请求全链路时序

```
用户发消息 → Webhook 接收 → 立即返回 200 → executor.submit(core_logic)
                                                  ↓
                                    parse_message + get_history + save_message
                                                  ↓
                                ┌─── 并行 ───────────────────────────┐
                                │ Thread: create_card → send_card    │
                                │         (427~1511ms) (724~812ms)   │
                                │                                    │
                                │ 主线程: build_messages(4~59ms)     │
                                │         → call_ai_stream           │
                                │         → 等 first_chunk           │
                                │           (1177~1845ms)            │
                                └────────────────────────────────────┘
                                                  ↓
                            card_id_queue.get() 等待卡片就绪 (0~2202ms)
                                                  ↓
                            stream_to_card 流式推送 (1396~2086ms)
                                                  ↓
                            finish_streaming 关闭流式 (523~625ms)
                                                  ↓
                            call_ai_summarize 提取意图 (166~4287ms) ← 同步阻塞
                                                  ↓
                            save_message + 释放用户锁
                                                  ↓
                                ┌─── 后台异步 ───────────────────────┐
                                │ async_reflect (1.5~3.0s)           │
                                │ async_voice_reply (语音匹配)        │
                                └────────────────────────────────────┘
```

## 真实生产耗时数据

| 环节 | 典型耗时 | 最慢耗时 | 日志标识 |
|------|---------|---------|---------|
| **generate_reply 总耗时** | 2.8~3.7s | **9.6s** | `⏱️ [性能] generate_reply 总耗时` |
| create_streaming_card | 427~500ms | **1511ms** | `⏱️ [性能] create_streaming_card` |
| send_card_message | 724~812ms | 812ms | `⏱️ [性能] send_card_message` |
| 等待卡片创建(阻塞) | 0~1380ms | **2202ms** | `⏱️ [性能] 等待卡片创建` |
| AI 流式生成 (Cerebras) | 1177~1845ms | 1845ms | `⏱️ [性能] AI 流式响应完成` |
| stream_to_card | 1396~1708ms | 2086ms | `⏱️ [性能] stream_to_card 总耗时` |
| finish_streaming | 523~625ms | 625ms | `⏱️ [性能] finish_streaming` |
| **AI 提炼多维意图** | 166~566ms | **4287ms** | `⏱️ [性能] AI提炼多维意图` |
| 仿生记忆反思(后台) | 1.5~2.8s | 3.0s | `🧠 反思引擎完成` |
| 构建上下文 | 4~59ms | 59ms | `构建上下文` |

---

## 🔴 瓶颈 #1：飞书 CardKit 三次串行 HTTP

**影响**：占总耗时 40~60%，是用户"发了消息后什么都看不到"空窗期的主要原因。

**位置**：
- `app/application/reply_service.py:77-109` — 卡片创建线程与主线程同步点
- `app/infrastructure/feishu/messenger.py` — 三次飞书 API 调用
- `app/infrastructure/feishu/card_streamer.py:206` — finish_streaming 同步阻塞

**三次串行调用**：

| 调用 | 典型耗时 | 作用 |
|------|---------|------|
| `create_streaming_card` | 427~1511ms | 创建卡片实体 |
| `send_card_message` | 724~812ms | 发送卡片到用户（依赖上一步的 card_id） |
| `finish_streaming` | 523~625ms | 关闭流式动画 |

**根因**：Docker 容器 → Cloudflare 隧道 → 飞书 API，每次 HTTP 往返延迟高。

### 优化方案

#### 方案 A：卡片预创建池（推荐）

在空闲期预创建 card_id 放入队列，reply_service 直接取用，跳过 create_streaming_card 的 RTT。

```python
# 新文件或放在 card_streamer.py 中
class CardIdPool:
    def __init__(self, pool_size=3):
        self._pool = queue.Queue(maxsize=pool_size)
        self._refill_thread = threading.Thread(target=self._refill_loop, daemon=True)
        self._refill_thread.start()

    def _refill_loop(self):
        while True:
            if self._pool.qsize() < 2:
                card_id = create_streaming_card()
                if card_id:
                    self._pool.put(card_id)
            time.sleep(1)

    def get(self, timeout=5):
        try:
            return self._pool.get(timeout=timeout)
        except queue.Empty:
            return create_streaming_card()  # fallback
```

**预期收益**：消除 427~1511ms 等待，`等待卡片创建` 降到 <50ms。

> ⚠️ 注意：需要确认飞书 card_id 的有效期，如果有 TTL 限制需要在池中加过期淘汰逻辑。

#### 方案 B：finish_streaming 异步化

`finish_streaming` 只是关闭流式动画，对用户体感无影响，改成 fire-and-forget。

**改动位置**：`app/infrastructure/feishu/card_streamer.py:206`

```diff
-        if not finish_streaming_fn(card_id, sequence):
-            logger_obj.warning(f"⚠️ 流式关闭失败 card_id={card_id}，卡片可能处于持续流式状态")
+        from ..application.post_reply_jobs import background_executor
+        background_executor.submit(finish_streaming_fn, card_id, sequence)
```

**预期收益**：减少 ~500ms 阻塞。

---

## 🔴 瓶颈 #2：call_ai_summarize 同步阻塞

**影响**：可额外增加 0.2~4.3s，最差情况把 3.4s 拉到 7.7s（+127%）。

**位置**：`app/application/reply_service.py:112`

```python
raw_reply = stream_reply_fn(...)           # 流式完成
clean_reply = normalize_reply_text_fn(...)  # 毫秒级
summary_info = call_ai_summarize_fn(...)    # ← 同步阻塞 166~4287ms
return {"reply_text": clean_reply, "summary": summary_info}
```

**根因**：这次 AI 调用只服务于后续的语音匹配（提取 intent/emotion/theme），**不影响用户看到的文字回复**，却阻塞在热路径上，还会延长用户锁的持有时间。

### 优化方案：将 summarize 移出热路径

**改动位置**：`app/application/reply_service.py:111-113`

```diff
     raw_reply = stream_reply_fn(open_id, ai_iterator, first_chunk=first_chunk, card_id=card_id)
     clean_reply = normalize_reply_text_fn(raw_reply)
-    if summary_info is None:
-        summary_info = call_ai_summarize_fn(user_text, clean_reply)

     logger_obj.info(...)
-    return {"reply_text": clean_reply, "summary": summary_info}
+    return {"reply_text": clean_reply, "summary": None}
```

**无需额外改动**：`async_voice_reply` → `match_voice_file_with_diagnostics` 中已有在 `pre_extracted_summary` 为空时自动调用 `call_ai_summarize_fn` 的逻辑（`voice_matcher.py:257-264`），所以语音匹配不受影响。

**预期收益**：generate_reply 减少 166~4287ms，典型减少 300~500ms。

---

## 🔴 瓶颈 #3：用户级串行锁粒度过粗

**影响**：连发消息时第 N 条需等前 N-1 条全部处理完，延迟线性叠加。

**位置**：`app/application/chat_orchestrator.py:70`

```python
with _get_user_logic_lock(open_id):
    # 从这里到函数结束，持锁 2.8~9.6s
    ...
    reply_result = generate_reply_fn(...)
    ...
    save_message_fn(...)
    background_executor_obj.submit(async_reflect_fn, ...)    # ← 不需要在锁内
    background_executor_obj.submit(async_voice_reply_fn, ...) # ← 不需要在锁内
```

**根因**：锁的初衷是防并发写入导致 history 错乱，合理。但两个 `submit` 和之前的 `call_ai_summarize`（瓶颈 #2）都在锁范围内，不涉及状态竞争。

### 优化方案：缩小锁范围

**改动位置**：`app/application/chat_orchestrator.py:70-122`

```python
def core_logic(data: dict, *, deps=None) -> None:
    open_id, user_text = parse_message_fn(data)
    if not open_id or not user_text:
        return

    if user_text.strip().startswith("/"):
        with _get_user_logic_lock(open_id):
            handle_command_fn(open_id, user_text.strip())
        return

    # 只在真正需要串行的部分持锁
    with _get_user_logic_lock(open_id):
        conversation = get_active_conversation_fn(open_id)
        conversation_id = str(conversation.get("id") or "")
        conversation_mode = str(conversation.get("mode") or "normal")
        history = get_recent_history_fn(open_id, limit=12, ...)
        save_message_fn(open_id, "user", user_text, ...)

        reply_result = generate_reply_fn(open_id, user_text, history)
        reply, summary_info = _normalize_reply_result(reply_result)
        if len(reply) > _MAX_MESSAGE_LENGTH:
            reply = reply[:_MAX_MESSAGE_LENGTH]
        save_message_fn(open_id, "assistant", reply, ...)
    # ← 锁在此释放，后台任务无需持锁

    background_executor_obj.submit(async_reflect_fn, ...)
    background_executor_obj.submit(async_voice_reply_fn, ...)
```

**预期收益**：连发消息场景下第 2 条延迟减少 1~5s。

---

## 📋 优化优先级

| 优先级 | 改动 | 代码量 | 预期收益 | 风险 |
|-------|------|--------|---------|------|
| **P0** | summarize 移出热路径 | 删 2 行 | 减 0.2~4.3s | 极低 |
| **P0** | finish_streaming 异步化 | 改 1 行 | 减 ~0.5s | 极低 |
| **P1** | 卡片预创建池 | 新增 ~30 行 | 减 0.4~1.5s | 低 |
| **P1** | 缩小用户锁范围 | 改 ~10 行 | 连发减 1~5s | 中 |

**推荐顺序**：先做 P0（共 3 行改动），典型耗时从 ~3.5s → ~2.5s，最差从 9.6s → ~3.5s。确认稳定后再做 P1。

---

## 附录：不是瓶颈的部分

| 环节 | 耗时 | 说明 |
|------|------|------|
| build_messages（上下文组装） | 4~59ms | 已做并行 Future 检索，性能良好 |
| Webhook 处理 + 去重 | <5ms | 立即返回 200，非阻塞 |
| prompt_builder | <1ms | 基于文件 mtime 缓存，几乎零开销 |
| 反思引擎 | 1.5~3.0s | 已在后台线程池异步执行，不阻塞用户 |
| 本地向量检索 (ChromaDB) | <50ms | FastEmbed 本地 CPU 推理，首次加载后很快 |
