# Feishu AI Companion 实时观察系统设计

> 最后整理：2026-04-23
> 状态：第一阶段已落地（文字版 MVP，已接入显式系统状态，图片/视频预留扩展位）

## 一、目标与边界

这份文档只解决一件事：

- 让用户在不进入正常聊天流的前提下，也能通过“观察视角”知道Companion此刻大概在做什么

第一阶段明确只做文字版，但设计上必须为后续 `jpg / gif / mp4` 留出统一状态源和媒体扩展位。

### 第一阶段目标

1. 新增 `/observe` 命令，返回一段第三人称的“实时画面白描”
2. 新增只读接口 `/presence`，返回当前观察快照的结构化 JSON
3. 观察文本与接口都复用同一份 snapshot，而不是每个入口各自现编
4. 不把 observation prompt 混进主聊天 prompt，不增加主聊天链的不稳定性

### 第一阶段非目标

- 不做图片生成
- 不做视频生成
- 不做持续推流或真直播
- 不把“观察系统”做成真实 OS 级任务监控

这意味着第一阶段是“拟态实时观察”，不是“系统内部真实进程监视器”。

## 二、体验原则

### 1. 观察视角

- 始终使用第三人称
- 像隐形摄像机或冷静旁白，不用Companion第一人称
- 不直接解释心理活动，优先用动作、表情、小习惯表达

### 2. 人设原则

- Companion仍然是傲娇、嘴硬心软的剧组化妆师
- 画面必须有生活气，但不能像“剧情模式”一样飘
- 轻微傲娇可以有，但不能过度戏剧化

### 3. 稳定性原则

- 同一时间桶内的观察结果应尽量稳定，不能每刷新一次就换一个场景
- “实时”优先来自结构化 snapshot，再由 AI 渲染成文字
- AI 失败时必须有模板兜底，而不是直接报错

## 三、总体方案

第一阶段采用“两层结构”：

1. `Observation Snapshot`
   先用规则、已有状态和少量检索，决定“她现在大概处于什么状态”
2. `Narration Render`
   再把 snapshot 渲染成第三人称画面白描

这两层拆开后，未来的图片和视频都可以直接消费同一份 snapshot，而不用重新发明一套状态来源。

```text
/observe 或 /presence
  -> application.observation_service
     -> 读取 / 生成 presence_snapshot
        -> domain.observation_rules 计算基础场景
        -> weather / bionic_state / recent_chat / long_term_memory 补上下文
        -> AI 或模板渲染 observation_text
  -> /observe 返回文字
  -> /presence 返回 JSON

未来媒体 worker
  -> application.observation_media_service
     -> 创建媒体占位任务
     -> 写入 media_status=pending
     -> 复用同一份 media_prompt
     -> 完成后写回 media_key 或 failed
```

## 四、第一阶段范围

### 1. 用户入口

- 飞书命令：`/observe`
- HTTP 只读接口：`GET /presence`

### 2. 输出形式

- `/observe`：文字消息
- `/presence`：结构化 JSON

### 3. 暂不做的展示

- 飞书观察卡片
- 飞书图片/视频消息
- 网页前端

这些能力都只保留数据结构与接口扩展位，不在第一阶段落地。

## 五、领域层设计

新增文件：

- `app/domain/observation_rules.py`

它只负责“规则判断”，不碰数据库、不发网络请求、不调 AI。

### 1. 基础行程槽位

建议先使用 6 段基础时间槽：

| 时间段 | `routine_slot` | 场景基调 |
|:---|:---|:---|
| `00:00-07:00` | `sleeping` | 深夜休息、睡姿凌乱、床头杂物 |
| `07:00-09:00` | `morning_rush` | 早场慌乱、通勤、化妆箱、吐司咖啡 |
| `09:00-14:00` | `set_busy` | 片场高压工作、补妆、盯妆、手忙脚乱 |
| `14:00-17:00` | `afternoon_gap` | 下午疲惫、保姆车、咖啡、短暂发呆 |
| `17:00-21:00` | `after_work` | 收工、便利店、便当、回家路上 |
| `21:00-00:00` | `night_alone` | 洗澡后、沙发、面膜、小红书、游戏 |

### 2. 意外生成器

第一阶段保留意外机制，但必须“可重复、可解释”，不要用每次请求都不同的纯随机。

建议：

- 按 5 分钟或 10 分钟为一个时间桶
- 用 `user_id + 日期 + 时间桶 + routine_slot` 计算稳定 seed
- 在同一时间桶内，意外事件固定不变

这样可以避免：

- 用户连点两次 `/observe`，她一会儿打翻拿铁，一会儿又在地铁口发呆

### 3. 意外触发规则

第一阶段只做 3 类：

- 天气联动意外
  例：下雨时从“片场外短暂停留”偏向“躲雨、鞋边溅湿、心情烦躁”
- 情绪联动意外
  例：`current_mood=生气` 时，把“喝咖啡”改成“咬扁吸管”
- 生活小事故
  例：粉扑掉地、睫毛膏滚走、外卖送错

### 4. 状态优先级

观察文本不应只靠时间表决定。优先级建议如下：

1. 显式系统状态
   当前接入：`replying / media_rendering / reflecting / proactive / reminder`
2. 刚刚互动过
   近 5 分钟内聊过天，画面必须体现“刚放下手机”或“屏幕还亮着”
3. 运行时情绪
   来自 `bionic_state.current_mood`
4. 基础行程 + 意外
5. 默认兜底空闲状态

当前已接入：

- `replying`
- `media_rendering`
- `reflecting`
- `proactive`
- `reminder`

也就是说，第一阶段已经不只是“按时间表猜她在干嘛”，而是会优先反映主回复、反思、提醒、主动消息和未来媒体生成这类真实运行中的系统动作。

## 六、应用层设计

新增文件：

- `app/application/observation_service.py`
- `app/application/observation_media_service.py`

`observation_service.py` 是第一阶段的核心编排层；`observation_media_service.py` 目前只做媒体任务占位，不接真实图片/GIF/视频 API。

### 1. 当前对外入口

- `get_or_create_observation_snapshot(user_id: str, *, force_refresh: bool = False) -> dict`
- `render_observation_text(snapshot: dict) -> tuple[str, str]`
- `build_presence_payload(explicit_user_id: str | None = None, *, force_refresh: bool = False) -> dict`
- `build_observation_media_task(user_id: str, media_type: str = "image", *, force_refresh: bool = True) -> dict`
- `complete_observation_media_task(user_id: str, *, state_token: str | None = None, media_type: str = "image", media_key: str = "", success: bool = False) -> dict`

### 1.1 媒体占位任务

第一阶段的媒体任务只做“状态闭环”：

- 创建任务时把 `jpg / jpeg / png` 归一为 `image`，`mp4` 归一为 `video`
- 写入 `media_status=pending`
- 暂存并返回 snapshot 里的 `media_prompt`
- 短时写入 `media_rendering` 显式状态
- 完成任务时写回 `ready + media_key`，失败时写回 `failed`
- 清理本次任务持有的 `media_rendering` token

它的价值不是现在生成图片，而是提前固定未来 worker 的状态契约。

### 2. 上下文来源

第一阶段只使用现有项目里已经稳定存在的来源：

1. 当前时间
   来自本地时区时间 helper
2. 当前天气
   来自 `app/weather.py`
3. 运行时情绪
   来自 `bionic_state.current_mood / mood_intensity`
4. 最近一次交互时间
   来自 `chat_history` / `bionic_state.last_interaction_at`
5. 最近一小段聊天提示
   不需要完整历史，只需要“刚聊过手机还亮着”这一类简短 hint
6. 一条长期记忆摘要
   可先从 active bionic memories 里取 1 条，不必上复杂向量检索

### 3. 第一阶段不建议直接接入的来源

- 主聊天链的流式中间态
- 复杂多轮向量召回
- 高频外部 API 拼接
- 图片识别或视频分析

这些来源要么耦合太深，要么稳定性和成本不适合第一版。

### 4. 缓存策略

第一阶段必须缓存 snapshot。

建议：

- `OBSERVATION_CACHE_SECONDS = 180`
- 3 分钟内默认复用现有 snapshot
- `/observe refresh` 或 `/presence?refresh=1` 可强制刷新

缓存的目的：

- 保证同一时间段内观察结果稳定
- 降低天气查询和 AI 调用频率
- 为未来图片/视频生成复用同一底图状态

## 七、持久化设计

新增文件：

- `app/infrastructure/persistence/sqlite_observation_repo.py`

新增表：

- `presence_snapshot`

### 推荐表结构

```sql
CREATE TABLE IF NOT EXISTS presence_snapshot (
    user_id TEXT PRIMARY KEY,
    snapshot_version INTEGER DEFAULT 1,
    state_source TEXT DEFAULT 'routine',
    routine_slot TEXT DEFAULT '',
    routine_label TEXT DEFAULT '',
    weather_summary TEXT DEFAULT '',
    accident_code TEXT DEFAULT '',
    accident_text TEXT DEFAULT '',
    mood TEXT DEFAULT '平静',
    mood_intensity REAL DEFAULT 0.5,
    recent_chat_hint TEXT DEFAULT '',
    memory_hint TEXT DEFAULT '',
    observation_text TEXT DEFAULT '',
    media_type TEXT DEFAULT 'text',
    media_status TEXT DEFAULT 'none',
    media_prompt TEXT DEFAULT '',
    media_key TEXT DEFAULT '',
    generated_by TEXT DEFAULT 'ai',
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_reason TEXT DEFAULT ''
)
```

### 字段说明

- `state_source`
  当前观察主来源，如 `routine / recent_chat / replying / media_rendering / reminder`
- `routine_slot`
  时间槽位机器值，如 `set_busy`
- `routine_label`
  时间槽位展示值，如“剧组高压工作期”
- `observation_text`
  最终给 `/observe` 发送的文字
- `media_type`
  默认是 `text`；媒体占位任务可写为 `image / gif / video`，但第一阶段不生成真实媒体
- `media_status`
  当前占位任务会使用 `pending / ready / failed`
- `media_prompt`
  未来给生图/视频 API 的提示词；第一阶段先生成并暴露给占位任务
- `media_key`
  未来媒体资源标识，如飞书 `image_key` 或 `file_key`

这样第一阶段虽然只返回文字，但已经提前准备好了媒体扩展位。

## 八、命令与接口设计

### 1. `/observe`

#### 行为

- 默认读取当前有效 snapshot
- 若 snapshot 过期，则重新生成
- 第一阶段只发送一段文字，不发卡片

#### 文案要求

- 第三人称
- 30-70 字优先
- 单段输出
- 禁止出现“系统正在推测”“可能”“似乎在生成中”这类技术味表述

#### 失败兜底

即使 AI 失败，也必须能返回模板化结果，例如：

```text
傍晚的便利店灯光有点冷，Companion拎着便当站在货架前，手机还攥在手里，像是刚看完消息又故意把屏幕按灭了。
```

### 2. `/presence`

#### 路由

- `GET /presence`

#### 鉴权

- `PRESENCE_AUTH_TOKEN`

当前实现的鉴权方式参照 `/health`：

- `Authorization: Bearer <token>`
- 或 `X-Presence-Token: <token>`

补充说明：

- 若未配置 `PRESENCE_AUTH_TOKEN`，`/presence` 会返回 `503 disabled`
- 若未显式传 `user_id`，当前实现会回退到 `ADMIN_OPEN_ID`
- `refresh=1/true/yes/on/refresh` 都会触发强制刷新

#### 第一阶段返回

```json
{
  "status": "ok",
  "snapshot": {
    "state_source": "recent_chat",
    "routine_slot": "afternoon_gap",
    "routine_label": "下午茶与摸鱼",
    "weather_summary": "阴转小雨",
    "accident_text": "她把冰美式放到手边后又改成了热拿铁",
    "observation_text": "保姆车窗边的光线有点灰，Companion刚把手机扣在腿上，指尖还无意识蹭着壳边，像是把你的消息来回看了两遍。",
    "media": {
      "type": "text",
      "status": "none",
      "prompt": "时间：2026-04-23 14:35；场景：下午茶与摸鱼；天气：阴转小雨；动作细节：保姆车窗边的光线有点灰...",
      "key": null
    },
    "generated_at": "2026-04-23T14:35:10+08:00",
    "expires_at": "2026-04-23T14:38:10+08:00"
  }
}
```

#### 用途

- 之后做网页小组件
- 之后做移动端只读页
- 之后给图片/视频 worker 拉取同一份 snapshot

## 九、Prompt 设计

第一阶段的 AI 只负责“把 snapshot 写得有画面感”，不负责决定事实。

### System Prompt 目标

- 第三人称
- 纯画面白描
- 少解释，多动作
- 保持傲娇但不过火
- 为未来图片/视频提示词留一致画面基调

### 推荐 Prompt 骨架

```text
你是一个隐形摄像机，正在客观描述“Companion”此刻的画面。

【结构化状态】
- 当前时间：{current_time}
- 基础行程：{routine_label}
- 天气：{weather_summary}
- 情绪：{mood}
- 突发意外：{accident_text}
- 最近聊天提示：{recent_chat_hint}
- 长期记忆提示：{memory_hint}

【任务】
请把这些状态写成一段 30-70 字的第三人称画面白描。

要求：
1. 不能出现“我”
2. 不能解释心理活动，优先写动作、表情、物件和环境
3. 如果刚聊过天，必须有手机相关的细节
4. 只输出最终文本，不要引号，不要解释
```

### Fallback 策略

AI 失败时，使用模板拼接：

- `routine_label`
- `weather_summary`
- `recent_chat_hint`
- `mood`

先保证“有结果”，再保证“有文采”。

## 十、和未来图片 / 视频的衔接方式

第一阶段不做真实图片和视频，但数据结构与占位服务已经支持以下升级路径：

### 第二阶段：图片

- 调用 `build_observation_media_task(user_id, "image")`
- 拿到同源 `media_prompt`
- 异步调用图片 API
- 成功后调用 `complete_observation_media_task(..., success=True, media_key=image_key)`
- 失败后调用 `complete_observation_media_task(..., success=False)`

### 第三阶段：GIF / MP4

- 继续复用同一份 snapshot
- 把 `media_prompt` 交给动画或视频 worker
- 完成后写回 `media_type=gif/video` 与 `media_key`

### 为什么必须先做 snapshot

如果没有统一 snapshot：

- 文字是一个场景
- 图片是另一个场景
- 视频又是第三个场景

用户会明显感觉“她一会儿在片场，一会儿在沙发，一会儿又在便利店”，违和感很强。

## 十一、实现顺序

建议按下面顺序做，风险最低：

1. `domain/observation_rules.py`
   先把时间槽位、意外规则和稳定 seed 算法写好
2. `sqlite_observation_repo.py` + `presence_snapshot` 表
   先落缓存容器
3. `application/observation_service.py`
   组装上下文、生成 snapshot、渲染文字
4. `command_service.py`
   接入 `/observe`
5. `main.py`
   接入 `/presence`
6. `verify.py`
   补最小离线验证
7. `observation_media_service.py`
   补媒体任务占位骨架，但不接真实媒体 API
8. 文档同步
   更新 `README / ARCHITECTURE / MODULES / CHANGELOG / DEPLOYMENT`

## 十二、第一阶段验收标准

满足以下条件，才算第一阶段完成：

1. `/observe` 能稳定返回文字，不依赖主聊天链
2. 同一时间桶内重复调用，输出不会剧烈漂移
3. `/presence` 能返回与 `/observe` 同源的 snapshot
4. AI 不可用时仍有模板兜底
5. 数据结构中已包含未来图片/视频字段，并已有媒体任务占位状态闭环，但当前不触发真实媒体生成
6. 不影响现有 `/status`、`/help`、回复主链和 scheduler 任务

## 十三、当前建议

第一阶段最重要的不是“把观察写得像诗”，而是：

- 先建立稳定的 snapshot
- 再用 AI 渲染成好看的文字

只要这一步做对，后面的卡片、JPG、GIF、MP4 都会变得顺理成章。
