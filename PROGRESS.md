# Storyteller 项目进度

## 当前阶段：MVP 实现完成（mock 链路已验证），待对接真实火山引擎

### 已完成
- [x] Brainstorming（需求 + 设计文档）
- [x] 实现计划（15 个任务）
- [x] Task 1-15 全部实现
- [x] 140 个测试全部通过
- [x] 包可编辑安装（pip install -e .）
- [x] mock provider 端到端冒烟测试通过

### 冒烟测试结论
- CLI 参数模式 / 交互式向导均可用
- 完整链路：剧本生成 → 声音匹配 → 分段 TTS → 拼接 → 输出 mp3
- 真实运行修复了 2 个单测未覆盖的问题：
  - .env 从 CWD 加载（find_dotenv usecwd）
  - 完成日志重复打印

### 待办
- [ ] 对接真实火山引擎 LLM（Doubao/Ark）验证
- [ ] 对接真实火山引擎 TTS 验证（鉴权方式、音色ID、请求格式待按真实账号确认）
- [ ] Claude Code 技能 /storyteller（skills/ 目录尚未创建）
- [ ] 手动选择声音的交互（目前自动匹配为主）
- [ ] 背景音乐/音效（数据模型已预留，逻辑未实现）

---

## 关键命令

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行测试
pytest

# 冒烟测试（mock，无需 key）
# 在任意目录放 .env（内容见 .env.example，provider type 设为 mock）
storyteller generate "故事主题"
```

---

*最后更新：2026-09-10*
