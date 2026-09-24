# Storyteller 文档

这里是当前行为文档的入口。代码、测试和运行时行为优先于历史设计记录；`docs/reference/tts/` 是厂商原始资料，不能直接视为项目已经实现的能力。

## 第一次使用

- [首次使用指南](getting-started.md)：安装、最小配置、第一次生成、剧本预览和 Web 启动

## 日常使用

- [配置参考](configuration.md)：环境变量、Provider、目录、调度器和 Web runtime settings
- [CLI 参考](cli.md)：生成、续作、音色、音效、Web 和交互式向导
- [Web 使用指南](web.md)：登录、生成、播放、历史故事、音色管理和设置页面
- [音色管理](voice-management.md)：筛选、年龄数组、启用状态、试听片段与本地持久化
- [API 总览](api/overview.md)：认证、资源分组、错误格式和 WebSocket 入口
- [Settings API](api/settings.md)：运行时设置、历史、重置、连接测试和模型列表
- [Voices API](api/voices.md)：音色列表、PATCH override 和试听音频

## 理解内部机制

- [角色与音色匹配](voice-matching.md)：角色元数据、候选池、LLM/rule 回退和日志
- Web 的详细操作和 API 入口见 [Web 使用指南](web.md) 与 [API 总览](api/overview.md)

## 部署与排障

- [Docker 部署](deployment-docker.md)：Compose、数据持久化、升级和备份
- [TTS 厂商参考资料](reference/tts/)：阿里云、火山引擎和 Qwen 的原始接口资料
- [配置参考](configuration.md)：Provider 配置与排障的当前事实来源

## 开发贡献

- README 的开发与测试入口，以及现有测试目录

主题文档会随着后续实现核对逐步补齐；在此之前，README 和已有的 Docker/TTS 文档仍是可直接使用的入口。
