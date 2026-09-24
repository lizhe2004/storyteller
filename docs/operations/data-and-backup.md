# 数据目录与备份

默认根目录为 `.storyteller`；主要子目录如下：

```text
.storyteller/
  stories/       项目状态、剧本、逐句片段、最终音频、项目音效
  sounds/        全局音效库文件和 index.json
  config/
    settings.json        Web runtime settings
    history.json         设置变更历史
    voice-overrides.json 音色年龄/启用覆盖
  logs/storyteller.log
```

Docker Compose 用 `docker-data/` 对应容器 `/data`。备份时应停止服务并归档整个 data root；至少要同时保留 `stories`、`config`、全局 `sounds` 和日志。恢复后保持同一 data root 配置，项目引用会通过内部稳定 `project_id` 解析日期标题目录。

敏感设置可能包含密码哈希、secret 和 provider 配置，备份文件应限制权限，不要提交 Git 或公开上传。删除 `config` 会丢失 Web 设置覆盖、历史和音色人工覆盖；删除 `sounds` 只会使全局音效缓存失效，后续任务可能重新生成。

