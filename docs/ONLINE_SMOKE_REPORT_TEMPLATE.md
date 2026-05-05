# Companion线上冒烟记录模板

> 用途：每次部署或重启后，把真实飞书链路跑一遍并留下记录。
> 建议文件名：`docs/smoke-reports/YYYY-MM-DD.md`，也可以直接复制本模板到运维笔记里。

## 一、基本信息

| 项目 | 记录 |
|:---|:---|
| 日期 |  |
| 执行人 |  |
| 分支 / commit |  |
| 部署方式 | `pm2 restart feishu-companion-web` + `pm2 restart feishu-companion-scheduler` / 其他： |
| 服务器 |  |
| 备注 |  |

## 二、部署前检查

```bash
git status --short
python3 scripts/verify.py --offline
python3 -m ruff check app scripts
python3 -m pytest scripts/test_persona_consistency_smoke.py scripts/test_webhook_entrypoint_smoke.py
```

| 检查项 | 结果 | 备注 |
|:---|:---:|:---|
| 工作区状态已确认 | [ ] |  |
| 离线验证通过 | [ ] |  |
| Ruff 通过 | [ ] |  |
| Smoke tests 通过 | [ ] |  |

## 三、部署后健康检查

```bash
pm2 status
pm2 logs feishu-companion-web --lines 100
pm2 logs feishu-companion-scheduler --lines 100
curl http://localhost:8081/health
curl -H "Authorization: Bearer $HEALTH_AUTH_TOKEN" http://localhost:8081/health
```

| 检查项 | 结果 | 备注 |
|:---|:---:|:---|
| `feishu-companion-web` online | [ ] |  |
| `feishu-companion-scheduler` online | [ ] |  |
| Web / scheduler 启动日志无持续 traceback | [ ] |  |
| 公开 `/health` 返回脱敏摘要 | [ ] |  |
| 授权 `/health` 返回完整详情 | [ ] |  |
| `components.ai_engine=true` | [ ] |  |
| `components.voice_db=true` | [ ] |  |
| `assets.prompt_ok=true` | [ ] |  |
| `assets.voice_lib_ok=true` | [ ] |  |
| `assets.card_image_ok=true` | [ ] |  |
| AI provider 熔断状态可解释 | [ ] |  |
| 最近 5 分钟无不可解释 error | [ ] |  |

当前 health 摘要：

```text
status=
provider=
model=
recent_errors=
recent_warnings=
ai_circuit=
```

## 四、飞书手动冒烟

| 步骤 | 操作 | 期望结果 | 结果 | 备注 |
|:---:|:---|:---|:---:|:---|
| 1 | 点快捷指令打开 `/help` | 命令中心卡片正常出现 | [ ] |  |
| 2 | 点“状态看板” | 状态卡片正常出现 | [ ] |  |
| 3 | 点“回复模式” | 模式卡片正常出现，可切换 | [ ] |  |
| 4 | 点“切换模型” | 模型卡片正常显示当前 provider | [ ] |  |
| 5 | 点“对话管理” | 可看到当前对话和操作按钮 | [ ] |  |
| 6 | 新建临时对话 | 新对话不混入日常历史 | [ ] |  |
| 7 | 切回日常聊天 | 默认对话恢复正常 | [ ] |  |
| 8 | 点“剧情模式” | 剧情卡片正常出现 | [ ] |  |
| 9 | 进入剧情并发一句剧情消息 | 剧情设定只影响当前会话 | [ ] |  |
| 10 | 退出剧情 | 回到日常聊天 | [ ] |  |
| 11 | 点“记忆审核” | 能列出候选或显示无候选 | [ ] |  |
| 12 | 发送“现在几点” | 直接返回本地时间，不走联网 | [ ] |  |
| 13 | 发送“你记得我昨天说了什么吗” | 优先基于真实聊天回看 | [ ] |  |
| 14 | 发送一张图片或表情包 | 文字回复正常，语音链路无报错 | [ ] |  |
| 15 | 点“清空上下文”但不确认 | 危险操作有二次确认 | [ ] |  |

## 五、观察日志

```bash
pm2 logs feishu-companion-web --lines 200
pm2 logs feishu-companion-scheduler --lines 200
```

重点搜索：

- `Core Logic Error`
- `AI 流式错误`
- `fallback_exhausted`
- `卡片更新异常`
- `仿生记忆反思失败`
- `剧情对话跳过现实仿生记忆反思`
- `上下文命中概览`

| 日志观察项 | 结果 | 备注 |
|:---|:---:|:---|
| 无持续 Core Logic Error | [ ] |  |
| 无持续卡片更新失败 | [ ] |  |
| AI fallback 可解释 | [ ] |  |
| 剧情反思跳过日志出现 | [ ] |  |
| 上下文命中符合预期 | [ ] |  |

## 六、结论

本次冒烟结论：

- [ ] 通过，可以继续运行
- [ ] 有降级但可接受，继续观察
- [ ] 不通过，需要回滚或修复

需要跟进的问题：

1. 
2. 
3. 
