# Companion稳定性巡检清单

> 最后整理：2026-04-22

这份清单用于日常确认Companion是否稳定运行。它不替代 `scripts/verify.py`，而是把“代码没坏”和“线上真的好用”分开检查。

部署后需要留下记录时，可以复制 [ONLINE_SMOKE_REPORT_TEMPLATE.md](ONLINE_SMOKE_REPORT_TEMPLATE.md)。

## 一、每次改代码后

### 1. 本地快速验证

```bash
python3 scripts/verify.py --offline
python3 -m ruff check app scripts
python3 -m pytest scripts/test_persona_consistency_smoke.py scripts/test_webhook_entrypoint_smoke.py
```

通过标准：

- `scripts/verify.py --offline` 显示 `12/12 通过`
- `ruff` 显示 `All checks passed!`
- pytest 显示全部通过

### 2. 重点看这些能力有没有被打碎

- 架构守卫：旧 facade 未回流。
- Webhook：坏密文返回 `400`。
- 命令卡片：`/help`、`/chat`、`/story`、`/memory audit` 可离线构建。
- 多重对话：不同 conversation 不串上下文。
- 剧情模式：剧情设定只注入当前会话，回复后不写现实仿生记忆。
- 人设边界：私人生活问句不触发 knowledge/web。
- 时间问句：现在几点/今天几号不走 AI 和联网。

## 二、每次部署后

### 1. 进程状态

```bash
pm2 status
pm2 logs feishu-companion-web --lines 100
pm2 logs feishu-companion-scheduler --lines 100
```

通过标准：

- `feishu-companion-web` 与 `feishu-companion-scheduler` 都为 `online`
- 启动日志出现运行时资产检查
- 没有持续重复的 traceback

### 2. 健康检查

公开摘要：

```bash
curl http://localhost:8081/health
```

授权详情：

```bash
curl -H "Authorization: Bearer $HEALTH_AUTH_TOKEN" http://localhost:8081/health
```

通过标准：

- `status` 是 `healthy` 或可解释的 `degraded`
- `components.ai_engine=true`
- `components.voice_db=true`
- `assets.prompt_ok=true`
- `assets.voice_lib_ok=true`
- `assets.card_image_ok=true`
- `ai_circuit.providers.<provider>.state` 为 `closed`，或 `open/half_open/half_open_ready` 有明确 provider 故障背景
- `observability.recent_degradations.by_severity.error` 为空或可解释

说明：

- 未带 token 的 `/health` 会返回脱敏摘要，不暴露服务器路径和近期观测 details。
- 配置 `HEALTH_AUTH_TOKEN` 后，带 `Authorization: Bearer <token>` 或 `X-Health-Token: <token>` 才能看到完整详情。
- `ai_circuit` 用来确认主模型是否被临时熔断；打开期间请求会直接走备用 provider。
- `feishu_api=false` 常见于 token 缓存未预热，不等价于主链不可用。

## 三、线上手动冒烟

在飞书里按顺序做：

1. 点击快捷指令打开 `/help`。
2. 点击“状态看板”，确认卡片能出现。
3. 点击“回复模式”，切换一次轻聊/普通，再切回常用模式。
4. 点击“切换模型”，确认当前模型卡片能显示。
5. 点击“对话管理”，新建一个临时对话，再切回日常聊天。
6. 点击“剧情模式”，进入剧情后发一句剧情消息，再退出剧情。
7. 点击“记忆审核”，确认卡片能列出候选或显示无候选。
8. 发一句“现在几点”，确认直接返回本地时间。
9. 发一句“你记得我昨天说了什么吗”，确认回答优先基于真实聊天回看。
10. 发一张图片或表情包，确认文字回复和语音链路没有报错。

通过标准：

- 卡片按钮没有卡死。
- 文本回复不出现大段系统说明。
- 剧情模式不会污染日常对话。
- `/clear` 只清上下文，不删除历史记录。
- 危险操作“重新开始”有二次确认。

## 四、每周一次

### 1. 备份检查

```bash
ls -lh backups | tail
```

确认：

- 最近 7 天有备份文件。
- 备份文件大小不是 0。
- 备份目录没有异常暴涨。

### 2. 冷恢复演练

建议在临时目录或测试环境做：

```bash
cp backups/<backup_file>.db /tmp/companion_restore_test.db
DB_PATH=/tmp/companion_restore_test.db MEMORY_PATH=/tmp/companion_restore_memory python3 scripts/verify.py --offline
```

通过标准：

- SQLite 能打开。
- 迁移逻辑不会报错。
- 离线验证能跑完。

### 3. 记忆审核

在飞书里打开：

```text
/memory audit
```

重点看：

- 是否有明星客户、私人行程、临场地点被误记。
- 是否有剧情内容进入现实仿生记忆。
- 是否有重复或过期的关系判断。

## 五、每月一次

### 1. 依赖与运行环境

```bash
python3 --version
python3 -m ruff check app scripts
python3 scripts/verify.py --offline
```

确认：

- Python 版本仍在项目支持范围。
- 依赖升级后没有导入失败。
- `uv.lock` / `requirements.txt` 没有明显漂移。

### 2. 提示词回归

手动测几类高频场景：

- 想念：“想死你了”
- 压力：“今天工作有点撑不住”
- 技术：“这个 Python 报错帮我看看”
- 回忆：“你记得我昨天说了什么吗”
- 吃醋/亲密：“你是不是不想我”
- 剧情：“我抬头看见你站在楼下”

通过标准：

- 不说教。
- 不把口语思念误判成自伤。
- 不把外部事实说成Companion自己的经历。
- 技术问题可以自然讨论，但不破坏角色感。

## 六、需要立刻处理的信号

- `/health.status=unhealthy`
- `components.ai_engine=false`
- `assets.prompt_ok=false`
- 最近 5 分钟 `recent_degradations.by_severity.error >= 1`
- webhook 连续返回 `400/403`
- 卡片长期停在“思考中”
- 语音上传连续失败
- 同一用户连续消息出现上下文串话
- 剧情内容进入现实记忆
- `/clear` 后历史聊天记录消失

## 七、不建议轻易做的事

- 不要在没有备份的情况下运行 `/reset`。
- 不要把 `.env`、SQLite 数据库、音频库、图片素材提交到 Git。
- 不要为了新增小功能继续拆大架构；优先保持当前模块化单体。
- 不要让 knowledge/web 层直接进入Companion自我经历。
- 不要让剧情对话写入现实仿生记忆。
