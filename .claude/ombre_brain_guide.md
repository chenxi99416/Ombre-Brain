# Ombre Brain 工具参考

详细使用说明已迁移到 docs/CLAUDE_PROMPT.md，那是完整版。

这里只留快速索引：

## 主连接器 /mcp（高频）
- `breath()` — 浮现记忆 / 关键词检索
- `hold(content)` — 存单条记忆，`feel=True` 存第一人称感受，`pinned=True` 钉为核心
- `grow(content)` — 长内容自动拆分归档
- `dream()` — 消化最近记忆，自省用
- `trace(bucket_id)` — 修改元数据 / resolved / delete

## 副连接器 /mcp-extra（按需）
- `anchor(bucket_id)` / `release(bucket_id)` — 设/解坐标系，上限24条
- `pulse()` — 系统自检
- `plan(content)` — 登记承诺待办
- `letter_write()` / `letter_read()` — 永久信件
- `I(content)` — 积累自我认知

## 选择指南
- 一句话的事 → hold
- 一大段内容 → grow
- 待办承诺 → plan（不要用hold）
- 永久信件 → letter
- 关于"我是谁" → I
- 先hold再anchor → 坐标系
