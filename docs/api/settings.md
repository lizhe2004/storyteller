# Settings API

所有路径都有 `/api/settings` 前缀，并通过 `require_login` 要求有效 `storyteller_session`。下面的 JSON 使用占位符；不要把真实 API key、密码或 secret 写入文档、shell 历史或工单。

## 读取当前设置

```http
GET /api/settings
```

响应包含 `web`、`llm`、`tts`、`sound`、`sources`、`provider_schemas`、`config_error` 和 `data_dir`。敏感值不会返回原文，例如：

```json
{
  "web": {
    "passwords": {"configured": true, "count": 1, "masked": "********"},
    "secret": {"configured": true, "masked": "********CRET"},
    "token_ttl_days": 30,
    "host": "127.0.0.1",
    "port": 8000,
    "concurrency": 2,
    "rate_limit_per_min": 10,
    "filler_voice": null
  },
  "llm": {"providers": ["openai"], "default_provider": "openai", "provider_config": {"openai": {"type": "openai_compatible", "api_key": {"configured": true, "masked": "********KEY"}, "model": "story-model"}}},
  "tts": {"providers": ["aliyun"], "default_provider": null, "provider_config": {}},
  "sound": {"enabled": false, "providers": [], "provider_config": {}, "dir": null},
  "sources": {"web": {"host": "default"}},
  "config_error": null
}
```

`sources` 的叶子值是 `admin`、`environment` 或 `default`，表示后台覆盖、环境配置或程序默认值。`provider_schemas` 描述每种 provider 类型允许的表单字段；它不是凭据回显。

## 部分保存

```http
PATCH /api/settings
Content-Type: application/json
```

只提交需要改变的组和字段，未提交的值保持不变：

```json
{
  "web": {"concurrency": 3, "rate_limit_per_min": 20},
  "llm": {
    "providers": ["writer"],
    "default_provider": "writer",
    "provider_config": {
      "writer": {
        "type": "openai_compatible",
        "api_key": "<NEW_API_KEY>",
        "base_url": "https://llm.example/v1",
        "model": "story-model"
      }
    }
  },
  "tts": {"providers": ["aliyun", "volcengine"], "provider_config": {"aliyun": {"workspace_id": "<WORKSPACE_ID>", "models": "model-a,model-b"}}},
  "sound": {"enabled": false, "providers": []}
}
```

字段由严格 schema 校验，未知字段返回 422。LLM `providers` 必须恰好一个；TTS 没有 default provider；音效最多一个 provider，启用音效时必须至少配置一个 provider。允许的 provider 配置字段是 `type`、`api_key`、`model`、`models`、`endpoint`、`base_url`、`resource_id` 和 `workspace_id`，具体表单字段以 `provider_schemas` 为准。

成功响应：

```json
{
  "version": "<UUID>",
  "updated_at": "2026-09-24T12:00:00Z",
  "effective_for": "new_jobs",
  "message": "保存成功；配置对新任务生效，运行中任务不受影响",
  "settings": {"...": "与 GET /api/settings 相同的脱敏设置对象"}
}
```

后台覆盖持久化到 `data_dir/config/settings.json`。运行中任务使用创建时的配置快照。

## 设置历史

```http
GET /api/settings/history
```

响应按最新优先返回最多 100 条：

```json
{
  "history": [
    {"version": "<UUID>", "updated_at": "2026-09-24T12:00:00Z", "operation": "update", "changed_paths": ["web.concurrency", "llm.provider_config.writer.model"]}
  ]
}
```

历史文件是 `data_dir/config/history.json`。它记录路径和操作，不记录敏感值。

## 恢复环境变量/默认值

```http
POST /api/settings/reset
Content-Type: application/json
```

```json
{"paths": ["web.concurrency", "llm.provider_config.writer.model", "tts.provider_config.aliyun.workspace_id"]}
```

允许重置的直接路径包括 `web.passwords`、`web.secret`、`web.token_ttl_days`、`web.concurrency`、`web.rate_limit_per_min`、`web.filler_voice`，LLM/TTS 的 `providers` 和 `default_provider`，音效的 `enabled`、`dir`、`providers`，以及 provider 配置的 `type`、`api_key`、`model`、`models`、`endpoint`、`base_url`、`resource_id`、`workspace_id`。不在白名单中的路径返回 422。成功响应与 PATCH 相同，`operation` 为 `reset`。

## Provider 连接测试

```http
POST /api/settings/test/llm
POST /api/settings/test/tts
Content-Type: application/json
```

请求：

```json
{
  "provider": "<PROVIDER_NAME>",
  "config": {"type": "openai_compatible", "api_key": "<API_KEY>", "base_url": "https://example.invalid/v1", "model": "<MODEL_ID>"},
  "timeout_seconds": 10,
  "voice_id": "<OPTIONAL_TTS_VOICE_ID>"
}
```

`config` 会与当前 provider 配置合并用于本次测试，不会因为测试自动保存设置；空的 `api_key` 不会覆盖已保存值。LLM 测试发送最小聊天请求；TTS 测试列出音色并合成短测试音频，指定 `voice_id` 时会先校验音色。

成功返回 `{"ok":true,"provider":"<PROVIDER_NAME>","message":"连接成功"}`。超时返回 504；provider、网络或合成失败返回 502；没有音色或 voice ID 不存在也会归入连接测试失败。请求的 `timeout_seconds` 必须大于 0 且不超过 30。

## 拉取模型列表

```http
POST /api/settings/models/llm
POST /api/settings/models/tts
Content-Type: application/json
```

请求体与连接测试相同，但不需要 `voice_id`：

```json
{"provider":"<PROVIDER_NAME>","config":{"api_key":"<API_KEY>","model":"<MODEL_ID>"},"timeout_seconds":10}
```

成功返回：

```json
{"ok":true,"provider":"<PROVIDER_NAME>","models":[{"id":"model-a","retiring":false},{"id":"model-b","retiring":true}]}
```

provider 不支持模型发现返回 422，超时返回 504，其他发现失败返回 502。模型列表按钮只把结果放入当前设置草稿；仍需保存设置才会持久化候选模型。

## 相关非 Settings 入口

`GET /api/config/options` 返回 `lengths`、`complexities`、`tts_providers`、`sound_enabled`、`llm_models` 和 `audio_models`，供放映室下拉框使用；它不会返回 API key。认证、故事、音色和 WebSocket 入口见 [API 总览](overview.md)。
