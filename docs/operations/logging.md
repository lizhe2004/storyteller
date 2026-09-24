# 日志与观测

## 位置

默认日志文件是 `<data_dir>/logs/storyteller.log`，CLI 默认数据目录为 `./.storyteller`；容器 Compose 将数据目录挂载到 `/data`，因此日志通常在宿主机 `docker-data/logs/storyteller.log`。容器运行日志仍可用：

```bash
docker compose logs -f storyteller
```

## 关联一次任务

优先用 `job_id`（Web streaming job）或 `project_id`（落盘项目）过滤，再结合 `session_id`、`line_id`、`provider`、`model` 和 `voice_id`。日志使用 `event=... key=value` 字段，不要把 API key、密码或完整敏感配置复制到 issue。

## 关键事件

角色匹配阶段关注 `voice_matching_character_candidates`、`voice_matching_prompt`、`voice_matching_llm_response`；LLM 关注 `llm_request_started/completed`；底层流式 TTS 关注 `tts_session_queued`、`tts_session_started`、`tts_provider_session_started`、`tts_first_audio_received`、`tts_session_finished`；项目关注 `project_saved`、音频片段和脚本导出事件。

搜索示例：

```bash
rg 'job_id=job_xxx|project_id=proj_xxx' .storyteller/logs/storyteller.log
rg 'voice_matching_prompt|voice_matching_llm_response' .storyteller/logs/storyteller.log
rg 'tts_session_started|tts_session_finished|tts_provider_session_started' .storyteller/logs/storyteller.log
```

