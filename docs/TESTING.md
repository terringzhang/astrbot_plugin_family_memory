# 测试与验收

从命名为 astrbot_plugin_family_memory 的源码目录运行 `python -B tests/run_tests.py`。测试只使用临时目录、虚构身份和 AstrBot API doubles，无外部聊天模型、QQ 或 TTS 调用。

覆盖身份与访客隔离、owner/peer 互读的边界和撤销、跨 Agent 隔离、来源与引用验证、共享授权、隐私拒绝、持久化、纠正/合并/遗忘、索引修复、缓存失效、Token 预算估算、假模型提取预算、hook 行为和互聊停止标记。

测试中的假模型不是自然语言质量验收；close/reopen 也不等于完整生产环境重启。`tests/benchmark.py` 是本机合成基准，结果取决于设备和临时磁盘，不是延迟服务承诺。

安装者应在隔离实例检查：真实适配器 message_id、self_id、平台 ID 与完整 UMO；保存/搜索；新会话与插件重载后召回；无关查询不注入；不同身份无法越权；原聊天模型、人格和 TTS 正常；guard 暂停与恢复。不要向未经同意的真实联系人发送验收消息。
