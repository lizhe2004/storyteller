# 故事生成流程

## CLI 同步流程

`generate` 创建项目后按以下步骤继续；`continue` 会读取已有 `project.json`，跳过已完成阶段和已经存在的逐句音频：

1. LLM 根据主题、篇幅和复杂度生成 `title`、`opening`、`characters` 和 `lines`。
2. 保存剧本并按标题重命名项目目录。
3. 从角色性别、年龄、偏好和音色目录生成候选池，分配一个 `voice_config`。
4. 对每条 line 选择 line 级、角色级或旁白级音色，调用同步 TTS 写入项目音频片段。
5. 按 line 顺序拼接片段生成 `story.<format>`。
6. 开启音效时生成/复用音效和背景音乐，再将其混入最终音频。
7. 保存 `completed` 状态；失败的单句会记录错误并继续处理其他片段，若一条片段都未成功则任务失败。

`--dry-run` 只执行剧本生成和 `story.script.json` 导出，不做音色匹配或 TTS。`continue` 以已有项目状态为入口，已存在的标准片段路径会被缓存跳过。

## Web 流式流程

Web 客户端通过 `/ws` 发送主题和模型选择。服务端先发布 `ready`，再流式生成 opening、剧本预览、角色匹配和正文 line；每条 line 根据匹配音色打开一个流式 TTS session，发布文本/音频事件，最后落盘项目和最终 MP3。详细消息字段见 [WebSocket API](api/websocket.md)。

Web 的 streaming job 和项目持久化是两层状态：WebSocket 连接断开不等于删除项目；内存中仍存在的 job 可以由协议客户端使用 `job_id` 手动重连，已经落盘的结果应从故事书架读取。

## 状态和断点续作

常见项目状态包括 `topic_collected`、`script_generated`、`voice_configured`、`generating_audio`、`audio_generated`、`post_processing` 和 `completed`。这些状态用于恢复和 UI 展示；不同入口不会保证每个中间状态都持久化到相同时间点。

剧本和 voice_config 会重新导出到 `story.script.json`。逐句音频使用 line id 的稳定文件名；恢复时优先复用标准路径，兼容旧的绝对路径片段并迁移到当前项目目录。

## 音色和 direction

角色信息由剧本生成阶段确定，后续匹配不能忽略剧本提供的性别和年龄。每条 line 的 `direction` 是独立的语音表现指令；TTS 调用同时可以携带最近旁白/对白作为 context。line 级 voice override 优先于角色音色，未命中时 dialogue 使用角色音色，其他情况回退到旁白音色。

