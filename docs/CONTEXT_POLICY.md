# 上下文、图片与工具策略

先启用记忆，再选择开启 `context_policy_enabled`。完整精确白名单：

```text
send_message_to_user
get_group_message_history
search_memes
llm_view_feed
llm_publish_feed
future_task
astr_kb_search
companion_memory_search
companion_memory_save
companion_archive_search
companion_image_recall
```

外部工具须已有相应插件；不自动安装。其他工具默认不提供给模型。历史社交 shell 记录可保留，但未来 shell 执行仍禁止。白名单不是 OS 沙箱，不过滤渠道原生 tools 或其他旁路插件，禁用插件会移除过滤。

`companion_memory_save` 只接受当前可信用户的非敏感原话，默认写当前 private，不允许访客写正式条目。是否调用由现有聊天推理决定，不保证捕捉所有重要信息。手动 /fmem 保留。

图片所属轮之后完成 N 轮交流后，下次请求才摘除，默认 N=10。支持 base64、`/AstrBot/data` 内本地图片和受限 QQ CDN；PNG/JPEG/GIF/WebP，单图最多约 20MB，下载有超时。拒绝其他主机、私有地址及非标准端口。未支持的 Windows 原生路径等来源会保留原图并告警。

原文先持久化，再深拷贝整理。档案或图片落地失败时保留原上下文；维护工具仍过滤。已完成技术调用与结果成对移除，当前在途调用不拆开。隐藏推理退出请求，但可能仍在本地原始档案中，不进入普通原文搜索。

默认历史估算预算 12000，优先保留最近 12 轮；年轻图片和巨大当前输入可能超限。旧历史用原文摘录交接，不是完整摘要。该预算不含所有人格、当前输入和工具 schema，不是计费硬限。插件不自动修改全局压缩、步数、模型、人格或 TTS。

档案无自动删除。遗忘正式记忆不擦除原文及备份；当前没有通用档案擦除命令。需要完整擦除时先停写、核验作用域和备份，不直接删共用数据库。
