# AstrBot Family Memory · 轻量家庭记忆

为 AstrBot 增加可持久化、可查看和可纠正的长期记忆，适合一个或两个 QQ Agent 的私聊场景。核心使用 **Python 标准库、Markdown、SQLite FTS5**，无需向量数据库、Embedding 服务或额外常驻模型。

**当前版本：0.1.8，首个脱敏公开版。** 基于私人部署的 0.1.7 整理；公开版不携带任何联系人、聊天内容、数据库、身份密钥或人格提示词。接口适配基于 AstrBot 4.29.1 / Python 3.12；元数据声明 `<5`，不代表已经测试所有后续版本。推荐先在独立测试实例验收。

## 功能与边界

- 按 Agent、可信发送者身份和命名空间检查读写权限，普通访客相互隔离。
- 支持私人记忆、显式授权的家庭域，以及默认关闭的 owner/peer 私有域互读。
- 关键词 / 中文二元组 FTS5、标签与有限跳数关系图谱检索，按预算注入相关片段。
- 手动保存、搜索、纠正、遗忘和合并；来源引用、版本、遗忘摘要与冲突候选可追溯。
- Markdown 条目可读，SQLite 保存索引、来源、关系和状态；关闭后重新打开仍可检索。
- 可选自动提取，必须指定现有 Provider 并设置调用上限；默认关闭、每日上限为 0。
- 可选 Bot-to-Bot 结束语停止保护，只匹配显式配置的完整会话 ID。
- 记忆处理失败或超时会跳过记忆环节，普通聊天继续；不改聊天模型、原人格或 TTS 配置。

**不承诺净 Token 节省，也不保存完整聊天档案。** 插件会增加少量检索上下文；只有配合独立原始消息归档与合理的短期上下文窗口，才可能降低总输入。`sources` 是有上限的来源缓存，不能用作永不丢失的聊天记录。默认的 `injection_budget=600` 按 UTF-8 字节估算，**不是 600 个计费 Token**。

本版有两个固定的内部 Agent 键 `xiaoman` 和 `elder_sister`，并非任意数量 Agent 的通用路由器；历史字段名仅表示路由角色，与你的机器人名字或人格无关。默认只处理可核实身份的**私聊**，群聊不支持。

## 安装

1. 备份 AstrBot 持久化数据和现有插件配置。
2. 在 AstrBot WebUI 的插件管理中，通过仓库地址安装：
   `https://github.com/terringzhang/astrbot_plugin_family_memory`
3. 保持插件配置 `enabled=false`，先填写下节身份信息。
4. 保存配置后通过 WebUI 重载本插件，再启用 `enabled` 并重载。
5. 用测试私聊保存和查询一条合成记忆，确认隔离，再用于日常聊天。

也可将源码放到 `data/plugins/astrbot_plugin_family_memory/`，确保 `main.py`、`metadata.yaml` 和 `schema.sql` 位于该目录根层。Docker 用户应持久化 `/AstrBot/data`。插件不需要读取 OneBot access_token，不需要挂载 QQ 协议端配置。

## 身份配置：先配置，再启用

以 [`config.template.json`](config.template.json) 和 [`_conf_schema.json`](_conf_schema.json) 为准。**不发布真实账号，也不要直接复制别人的身份映射。**

| 字段 | 含义 |
| --- | --- |
| `xiaoman_platform` | OneBot 侧 AstrBot 平台实例 ID；示例默认 `default`，必须与你的实例一致 |
| `xiaoman_self_id` | 该机器人的真实 QQ/self_id；公开版为空，必须填写 |
| `owner_qq_ids` | 该侧已核实主人的发送者 QQ ID 列表，值使用字符串 |
| `sister_binding` | 第二位 Agent 在 OneBot 侧作为联系人的身份：`qq_id`、`approved`、`evidence_ref` |
| `elder_platform` | 第二侧 QQ 官方平台实例 ID；示例 `qq_official` 只是占位，需要替换 |
| `elder_self_id` | 第二侧可选严格 self_id 校验；不要误填 AppID |
| `elder_owner_openids` | 第二侧已核实主人的 OpenID 列表 |
| `elder_peer_binding` | 第一位 Agent 在第二侧的可信 OpenID 绑定：`openid`、`approved`、`evidence_ref` |
| `elder_private_mutual_read` | 默认 `false`；显式允许第二侧 owner/peer 互读，仍不能互改、互删 |

单机器人使用时，只配置第一侧，第二侧使用一个不存在且不与第一侧相同的平台 ID。不要用昵称、模型自述或相似文本猜测 QQ 与 OpenID 对应关系。`evidence_ref` 是你本地保存的核验记录引用，不是密钥；**程序要求其非空，但不会替你核实证据真实性**。

身份映射错误会影响访问权限。更换平台 ID、发送者 ID、身份密钥或角色分类，可能生成不同命名空间；插件不会自动搬移旧访客记录。修改前先备份，参见 [配置与隔离](docs/CONFIGURATION.md)。

## 用法

在同一条私聊消息中发送完整指令：

```text
/fmem remember private 我喜欢蓝色纸鹤
/fmem search 纸鹤
/fmem correct <完整记忆ID> 我现在更喜欢绿色纸鹤
/fmem forget <完整记忆ID>
/fmem merge <ID1>,<ID2>
```

第一侧已核实主人或可信 peer 可主动共享某条信息：

```text
/fmem remember family 我们一起完成了纸灯笼
```

私人内容不会因这条指令变成全库共享。普通访客只能维护自己的记忆；第二侧没有同名的家庭域写入能力。家庭域有编辑权的成员能维护家庭条目，适合共同信息，不适合个人秘密。

默认情况下，普通聊天只进入有限的来源缓存。**自动提取关闭时，不会把所有聊天自动转换成长期条目。** 可以使用上述手动指令；需要自动化时再查看 [可选自动提取与费用](docs/CONFIGURATION.md#可选自动提取与费用)。

## 可选互聊停止保护

设置 `botchat_guard_enabled=true`，填写双方精确的 `botchat_peer_umos`。完整 UMO 以自己实例的 `/sid` 输出为准。它是独立的停止保护，不是自动互聊调度器，也不会主动发送 QQ 消息。

初始状态为暂停。已配置主人可在自己的聊天里使用：

```text
/botchat status
/botchat resume
/botchat pause
```

指定互聊会话收到“晚安”“下次再聊”“不聊了”等结束语会暂停；模型输出结束语时最多允许该次最终回复，随后阻止迟到回复。暂停状态持久化。规则是启发式匹配，可能误判或漏判；已发送片段、绕过 AstrBot 回复钩子的外部工具不受完整保护。即使 `enabled=false`，单独开启 guard 仍会工作；禁用整个插件才会移除它。

## 存储、备份与恢复

默认相对 AstrBot 数据目录：

```text
plugin_data/astrbot_plugin_family_memory/agent_memory/
  .identity-key                 # 身份 HMAC 和条目作用域签名，必须备份
  .forgotten.json               # 持久遗忘摘要，必须备份
  agents/<agent>/<namespace>/episodes/<id>.md
  index/memory.sqlite3          # 来源缓存、索引、图谱与状态
  botchat_state.json            # 可选互聊暂停状态
```

这是**同一存储根和同一 SQLite 文件内的逻辑权限隔离**，不是物理隔离，也不是静态加密。拥有文件读取权限、容器命令工具、root 或宿主机权限的人仍可能读取全部记忆。HMAC 化路径不是匿名化保证。详见 [安全边界](SECURITY.md)。

最稳妥的备份方式：停止本插件且确认没有仍在运行的写入任务，备份整个上述目录及 `config/astrbot_plugin_family_memory_config.json`；再重载插件。不要只复制正在写入的 SQLite 主文件，WAL 可能尚未合并。恢复时同样先停插件，保留现状副本，再恢复完整目录与匹配配置。不要覆盖原 AstrBot 聊天数据库或人格配置。

`forget` 会使条目退出当前检索并更新遗忘记录，**不会自动擦除历史备份**。敏感资料应另行制定备份保留和删除策略。

## 开发与测试

核心无额外 pip 依赖，适配器运行时由 AstrBot 提供相关模块。需要 Python 3.12 与支持 FTS5 的 SQLite；推荐 Linux。源码目录名保持为 `astrbot_plugin_family_memory`。

```sh
cd astrbot_plugin_family_memory
python -B tests/run_tests.py
python -B tests/benchmark.py
```

单元测试使用临时目录、虚构身份与 AstrBot API doubles，不连接 QQ、不使用真实模型或 TTS。测试通过不代表已在你的 QQ 平台、模型渠道或每个 AstrBot 版本上完成验收。查看 [测试与验收](docs/TESTING.md)。

## 常见问题

- **`missing_stable_source_identity`**：适配器未提供稳定 message_id；插件拒绝用消息正文哈希猜测来源，应检查适配器元数据。
- **`memory_timeout` / 服务暂不可用**：检查存储延迟、插件初始化与负载；默认 hook 预算 80ms、主动命令单步预算 1.5s。超时的线程可能仍在完成任务，先查询确认，再决定是否重试。
- **只能主人唤醒**：先排查 AstrBot 自身白名单、唤醒条件和模型错误。插件不会替代平台访问控制；可选 guard 只阻止配置的互聊会话。
- **长期条目为 0**：来源缓存与长期记忆不是同一层；默认自动提取关闭，先用手动记忆指令验收。
- **不相关内容也被召回**：提高 `minimum_score`、降低 `top_k`；这是词法/关系检索，不是 Embedding 语义检索。

## 贡献与许可证

欢迎提交合成场景、失败原因码和最小复现。不要提交数据库、原始聊天、账号、API Key、OpenID、`.identity-key` 或私有环境报告。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

以 [MIT License](LICENSE) 发布。AstrBot 及其他平台属于各自项目，遵循各自许可证与使用约定。
