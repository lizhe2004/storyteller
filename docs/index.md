# Storyteller 文档

这里是当前行为文档的入口。代码、测试和运行时行为优先于历史设计记录；`docs/reference/tts/` 是厂商原始资料，不能直接视为项目已经实现的能力。

## 第一次使用

- [首次使用指南](getting-started.md)：安装、最小配置、第一次生成、剧本预览和 Web 启动
- [配置参考](configuration.md)：环境变量、默认值和配置优先级
- [CLI 参考](cli.md)：`generate`、断点续作、音色和音效命令

## 日常使用

- [Web 使用](web.md)：登录、故事生成和浏览器端操作
- [音色匹配](voice-matching.md)：角色、候选音色和匹配回退
- [音色管理](voice-management.md)：目录筛选、启用状态、年龄和试听
- [音效](sound-effects.md)：提示词、缓存和混音

## 理解内部机制

- [架构](architecture.md)：模块边界、项目状态和数据流
- [故事生成](story-generation.md)：剧本、配音、缓存和断点续作
- [流式 TTS](streaming-tts.md)：实时合成、调度和降级
- [API 总览](api/overview.md)
- [WebSocket API](api/websocket.md)

## 部署与排障

- [Docker 部署](deployment-docker.md)：Compose、数据持久化、升级和备份
- [运维与排障](operations.md)
- [TTS 厂商参考资料](reference/tts/)：阿里云、火山引擎和 Qwen 的原始接口资料
- [Provider 总览](providers/overview.md)

## 开发贡献

- [开发指南](development.md)
- [Provider 接入](providers/overview.md)
- [测试与验证](development.md#测试)

主题文档会随着后续实现核对逐步补齐；在此之前，README 和已有的 Docker/TTS 文档仍是可直接使用的入口。
