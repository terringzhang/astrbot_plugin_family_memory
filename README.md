# AstrBot Family Memory · 轻量家庭记忆

为一个或两个 Bot 提供可追溯长期记忆、可选语义检索、本地聊天档案和上下文整理。内部路由统一为 **`bot1`、`bot2`**，不携带任何人的账号、人格、聊天或生产配置。

**版本 0.2.1；验证基线 AstrBot 4.29.1 / Python 3.12。** 记忆、自动提取、Embedding、归档整理、权重衰减、共享和互聊保护默认关闭。元数据 `<5` 不代表测试过所有后续版本。

> **已有 0.1.x 数据先读 [升级说明](docs/UPGRADE.md)。** 本版更换路由和配置键，不是直接覆盖旧数据的无缝升级；不支持的旧路由在写入前拒绝，不自动迁移或清空。

## 0.2.1 新增

历史对话语义召回、最早会话覆盖信息、调试/错例标签隔离，以及敏感内容逐条授权。详见 [历史检索与隐私](docs/HISTORY_PRIVACY.md)。默认开关与身份隔离保持保守；不包含生产聊天、人格或凭据。

## 功能

- Markdown 正式记忆 + SQLite FTS5 来源、索引、图谱与版本状态。
- 按 Bot、可信发送者和命名空间限制权限；访客互相隔离。
- `/fmem` 保存、搜索、纠正、合并、遗忘，可追溯来源与遗忘标记。
- 可选现有 Embedding Provider 增量索引，失败保留词法检索。
- 可选“用进废退”：不使用则降权，明确重提可强化，不删除原文。
- 可选完整 Message JSON 档案；技术参数和返回不进入普通原文搜索。
- 可选图片期限：之后完成 10 轮交流后移出上下文，先落地再换成图片编号。
- 可选日常工具白名单，保留明确的社交、陪伴和受限记忆工具。
- 可选互聊结束语停止保护，不主动创建互聊或发送测试。

**不保证无限无损记忆或固定比例的 Token 节省。** 原始档案、正式记忆和有上限的 `sources` 证据缓存是不同层。核心使用标准库；运行适配器依赖 AstrBot 已提供的 API 和 MCP 类型。

## 安装与第一次启用

1. 更新前备份源码、配置和完整插件数据。推荐独立测试实例。
2. 从 `https://github.com/terringzhang/astrbot_plugin_family_memory` 安装，确认 `metadata.yaml` 是 **0.2.1**。若主分支尚未合入本版，使用对应 PR 分支，不能把旧版当成本版。
3. 保持 `enabled=false`，按下表和 [模板](config.template.json) 填写平台及可信身份。
4. 保存并重载，启用 `enabled=true`，先验收两位测试用户的保存、查询与隔离。
5. 各项可选功能逐项开启。Embedding 可能收费，完整档案涉及隐私和磁盘增长。

手动安装时目录名保持 `astrbot_plugin_family_memory`，插件文件位于该目录根层。Docker 应持久化 `/AstrBot/data`。不需要 OneBot Token，也不需要挂载 QQ 协议端配置。

## 身份配置

| 字段 | 含义 |
|---|---|
| `bot1_platform` | bot1 平台实例 ID，默认占位 `default` |
| `bot1_self_id` | bot1 真实 self_id，公开默认空，空值拒绝匹配 |
| `bot1_owner_ids` | bot1 入口经核实的主人发送者 ID 列表 |
| `bot1_peer_binding` | bot2 在 bot1 联系人中的身份：`qq_id`、`approved`、`evidence_ref` |
| `bot2_platform` | bot2 平台实例 ID，`qq_official` 只是占位 |
| `bot2_self_id` | bot2 可选严格 self_id 校验，不猜测 AppID 对应关系 |
| `bot2_owner_openids` | bot2 入口经核实的主人 OpenID 列表 |
| `bot2_peer_binding` | bot1 在 bot2 入口中的身份：`openid`、`approved`、`evidence_ref` |
| `bot2_private_mutual_read` | 默认关闭，明确同意后允许 bot2 owner/peer 互读，不可互改互删 |

标签不是人格名，仅支持两个路由和可核实身份的私聊，不支持任意数量 Agent 或群聊记忆。单 Bot 使用时，另一平台设为未使用且不同的 ID。不要按昵称、相似文本或模型自述绑定身份。程序要求 `evidence_ref` 非空，但不会替你核验其真实性。

bot1 的可信 owner/peer 可读写 bot1 `family`；bot2 不自动获得该域。访客始终独立。详见 [配置与权限](docs/CONFIGURATION.md)。

## 命令

```text
/fmem remember private 我喜欢蓝色纸鹤
/fmem search 纸鹤
/fmem correct <完整记忆ID> 我现在更喜欢绿色纸鹤
/fmem forget <完整记忆ID>
/fmem merge <ID1>,<ID2>
```

bot1 可信 owner/peer 可明确共享：

```text
/fmem remember family 我们一起完成了纸灯笼
```

### 常见误用：一条消息只发一条命令

**不要整块粘贴多条 `/fmem remember`。** 整块会被视为一条正文，命令前缀也可能进入记忆。每次单独发送完整一行，收到“记忆已保存”再发下一条。误存后用 `/fmem forget <ID>` 保留遗忘标记，再逐条重建；不要直接删数据库文件。

默认普通聊天只进有限来源缓存，不会自动全部变成正式条目。独立 LLM 提取默认关闭、每日预算为 0。上下文模式还允许现有聊天模型按需调用 `companion_memory_save`，只保存当前可信用户明确、非敏感的原话，默认只进当前 private。它不是另一次提取请求，也不保证捕捉每个重要话题。

## 可选向量检索

先在 AstrBot 验证 Embedding Provider，再配置：

```json
{"embedding_enabled": true, "embedding_provider_id": "your_existing_provider_id"}
```

仅新增或正文变化的正式有效条目需要重索引，不向量化全部聊天或 sources。默认 1800 秒增量扫描，每批最多 16 条；查询最多等待 0.6 秒，超时先走词法。已有请求不会因为等待超时被立即重复提交。

每日 500 次、200000 UTF-8 字节是保护预算，**字节不是计费 Token，调用次数不是金额硬上限**。先确认价格与外部数据处理政策。参见 [Embedding](docs/EMBEDDING.md)。

## 可选档案、图片期限与上下文整理

完成备份并启用记忆后，可设置：

```json
{
  "context_policy_enabled": true,
  "activation_enabled": true,
  "image_keep_rounds": 10,
  "context_estimate_budget": 12000,
  "context_recent_rounds": 12
}
```

- 先归档原始 Message JSON，再精简；首次启用本地保存可识别私聊的历史，不批量导入长期记忆、不调用模型。以后收发和 Agent 完成钩子继续留档。
- 图片按其后完成的交流轮次计时，不计工具循环。base64、允许目录内本地图片或受限 QQ CDN 先落地，再到期摘除。失败则保留图片并告警；一般压缩不会提前丢弃年轻图片。
- 已完成维护工具调用及返回成对移出；正常社交历史保留。历史隐藏推理不再发送，但可能仍在受限档案中。
- 超限时保留近期完整轮次，用旧原文摘录交接，**不是完整语义摘要**。更多细节使用 `companion_archive_search`，图片使用 `companion_image_recall`，均检查身份权限。
- 12000 是历史的本地估算预算，不包含全部人格、工具 schema 和当前输入，也不是供应商 Token 硬限；年轻图片或巨大当前输入可能超限。

此模式改变后续请求和有效会话历史，原文先保存到独立档案。不自动修改 AstrBot 模型、人格、TTS、全局权限、原生压缩设置或强制定时 `/new`。可根据自己的模型规格另外设置原生压缩后备和工具步数。

### 日常工具白名单

仅保留明确的消息发送、历史、表情、现有空间查看/发布、提醒、知识库和本插件的受限记忆/档案工具，完整名称见 [上下文策略](docs/CONTEXT_POLICY.md)。外部工具必须已安装且可用，本插件不替代社交插件。

终端、代码、任意文件读写、浏览器执行和未知工具不提供给模型。过滤针对 AstrBot FunctionTool，**不是操作系统沙箱，不会禁用渠道原生工具**。禁用/卸载插件会移除过滤，应同时审查 AstrBot 自身权限。

## 用进废退

激活强度随未使用时间衰减；明确回忆语境和足够原词重合可强化，每条一天最多一次。重要事实和关系保留底值，纠错、遗忘和权限检查优先。自动检索或注入本身不强化。

这是本地可解释的启发式，不是训练神经网络。调整权重不改正文 digest，不触发向量重建。详见 [架构](docs/ARCHITECTURE.md)。

## 可选互聊结束保护

设置 `botchat_guard_enabled=true` 和双方 `/sid` 的完整 `botchat_peer_umos`。初始暂停，可信 owner 使用 `/botchat status`、`/botchat resume`、`/botchat pause`。结束语暂停并持久化，不主动开启互聊。

规则可能误判或漏判，已发送片段和绕过回复钩子的外部工具不受完整保护。不要当作平台间的全局断路器。

## 存储与恢复

```text
plugin_data/astrbot_plugin_family_memory/
  agent_memory/
    .identity-key
    .forgotten.json
    agents/<bot1|bot2>/<namespace>/episodes/<id>.md
    index/memory.sqlite3
    index/embedding.sqlite3         # 可选
    botchat_state.json              # 可选
  conversation_archive/            # 可选
    archive.sqlite3
    images/<agent>/<actor>/<id>.<ext>
```

共享 SQLite 中的**查询隔离不是物理隔离或静态加密**。容器 root、宿主权限和任意文件读取可能看到全部资料。档案可能包含敏感原文、技术输出和隐藏推理；0600 权限仍需配合受控宿主和备份。

停止插件且确认写入任务退出后，备份整个插件数据根、源码和插件配置。不要只拷贝正在写入的 SQLite 主文件，WAL 可能未合并。恢复前保留当前完整副本，再恢复匹配的代码、配置和数据，不覆盖 AstrBot 聊天库或人格。

降权不删除；`forget` 只使正式条目退出召回，**不会擦除档案和备份**。原文档案不代表最新事实。没有自动磁盘清理或通用档案擦除聊天命令，请监控增长并制定保留策略。详见 [安全边界](SECURITY.md)。

## 开发与贡献

```sh
cd astrbot_plugin_family_memory
python -B tests/run_tests.py
python -B tests/benchmark.py
```

测试仅用合成身份、临时目录和 Provider doubles，不连接 QQ 或真实模型。不是所有平台、TTS、跨模型质量或账单节省的验收证明。见 [测试说明](docs/TESTING.md)。

请勿提交账号、OpenID、聊天、人格、本子、数据库、密钥或私人部署报告。欢迎最小复现和合成测试。采用 [MIT](LICENSE)，见 [贡献指南](CONTRIBUTING.md)。
