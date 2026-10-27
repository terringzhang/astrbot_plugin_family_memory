# 配置、隔离与资源预算

配置完整字段由根目录 `_conf_schema.json` 定义，`config.template.json` 包含相同的默认值。不要把占位平台名称当作实际平台 ID。

## 命名空间

身份键由持久 `.identity-key` 对平台与发送者 ID 做 HMAC 派生；内部路由标签为 `bot1`（第一侧）与 `bot2`（第二侧）。每次搜索先限定 Agent 和可读域，写入则另行检查写权限。

| 身份 | 默认可读 | 可写 |
| --- | --- | --- |
| 第一侧 owner / 已核实 peer | 自己的 private + 第一侧 family | 自己的 private + family |
| 第一侧普通访客 | 自己的 visitor | 自己的 visitor |
| 第二侧 owner | private-owner + 同一 owner 的旧 private | 自己的 private-owner |
| 第二侧已核实 peer | 自己的 private-peer | 自己的 private-peer |
| 第二侧普通访客 | 自己的 visitor | 自己的 visitor |

第二侧 `bot2_private_mutual_read=true` 且 peer 绑定获准后，owner 可额外读 peer 私有域，peer 可读已配置 owner 的新旧私有域；不产生跨 Agent 共享，也不授予互改/互删能力。这个开关默认关闭，开启前须获得相关人的知情同意。

`approved=true`、对应 ID 和非空 `evidence_ref` 是绑定条件。它们表示操作者完成核验，程序不会自动验证记录。角色变更不重分类旧 sources；不要擅自改库或交换身份。

## 资源控制

- `top_k=3`、`graph_hops=2`、`minimum_score=0.22`：召回数量、图谱跳数和最低评分。
- `injection_budget=600`：默认 UTF-8 字节估算；不是供应商 Token 账单，也不包含请求包装开销。
- `hook_timeout_seconds=0.08`、`command_timeout_seconds=1.5`：单次操作等待预算。超时不会强行杀死后台线程。
- `cache_seconds=30`：检索缓存；原文、条目状态与作用域仍会校验。
- `pending_source_limit=500`：每命名空间待处理来源缓存目标上限；已有记忆引用与进行中批次可能保留相关来源，因此不是数据库总行数硬上限。
- `max_namespaces=256`、`max_memories=1000`、`max_database_mb=64`：保守准入限制，达到上限不删除旧条目；主库大小限制不等于包含 WAL、Markdown 和备份的磁盘总配额。

先用独立原始聊天归档保障可恢复性，再考虑缩短主模型上下文。不开启 context_policy_enabled 时不整理历史；开启后会修改 Provider 历史并先归档原文，但不自动修改全局压缩设置、persona、聊天 Provider 或 TTS。详见 CONTEXT_POLICY.md。

## 可选自动提取与费用

默认：`allow_llm_extraction=false`、`summary_provider_id=""`、`max_summary_calls_per_day=0`，不会额外调用提取模型。

要开启须同时配置已有 Provider ID、`allow_llm_extraction=true`、正数每日调用上限；推荐先在合成对话中测试。`summary_rounds=20` 与 `min_summary_interval_seconds=600` 控制批次节奏；调用预算按 UTC 日统计。

提取候选必须引用 user 来源，text 必须是被引用原文中的摘录，低置信度、假设或玩笑候选进入待确认状态。它不是全面的事实验证器、自动人格学习器，也不会自动把 Markdown 本子或所有历史聊天导入。

Provider 可能收费；每日调用次数限制不是金额、Token 或供应商内部重试次数的硬上限。没有价格账单时，不提供费用保证。费用与限流仍须由 Provider 管理。模型提取失败会延后批次，不会切换主聊天模型。

## 配置修改与恢复

关闭记忆引擎后重载插件，确认没有未完成写入，再复制整个存储根和配置。`.identity-key` 不能丢失或随意重建；否则旧身份路径与签名无法直接对应。恢复前先保留当前目录，恢复后用合成记忆验证搜索、隔离、纠正、删除和重载后的持久性。

备份目录不要置于自动同步扫描的 episodes 子目录内。不要让多个活跃插件实例写入同一存储根。
