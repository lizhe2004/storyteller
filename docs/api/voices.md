# Voices API

Voices API 提供音色目录筛选、本地年龄/启用状态覆盖和故事分句试听。所有端点都需要有效的 `storyteller_session` cookie；未登录统一返回：

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"detail":"未登录"}
```

先登录并保存 cookie。示例中的密码和 key 都是占位值：

```bash
curl -i -c /tmp/storyteller-cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"password":"replace-me"}' \
  http://127.0.0.1:8000/api/auth
```

登录成功是 `204 No Content`。后续每个示例都用 `-b /tmp/storyteller-cookies.txt` 发送该会话。`voice_key` 格式为 `provider|model|voice_id`，缺少模型时 model 段为 `unknown`；放入 URL path 前必须整体编码。

## 列出和筛选音色

```http
GET /api/voices
```

查询参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | 全部 | provider 注册名精确匹配 |
| `model` | 全部 | catalog 模型精确匹配 |
| `gender` | 全部 | catalog 性别精确匹配 |
| `age` | 全部 | 枚举必须存在于音色年龄数组 |
| `status` | `all` | `all`、`enabled` 或 `disabled`；空字符串也按全部处理 |
| `page` | `1` | 小于 1 时按 1 处理 |
| `page_size` | `50` | 限制到 1–200 |

`category`、`tags`、`description` 会返回，但不是查询参数。

认证请求示例：

```bash
curl -sS -b /tmp/storyteller-cookies.txt \
  'http://127.0.0.1:8000/api/voices?provider=mock&gender=female&age=young_adult&status=enabled&page=1&page_size=50'
```

`200 OK` 响应示例：

```json
{
  "voices": [
    {
      "key": "mock|unknown|narrator_01",
      "provider": "mock",
      "model": null,
      "voice_id": "narrator_01",
      "name": "少儿故事",
      "gender": "female",
      "age": ["young_adult"],
      "category": "有声阅读",
      "description": "语调活泼亲切，适配儿童故事的治愈旁白女声",
      "tags": [],
      "clip_count": 2,
      "has_clips": true,
      "enabled": true
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50,
  "filters": {
    "providers": ["mock"],
    "models": [],
    "genders": ["female", "male"],
    "ages": ["child", "teen", "young_adult", "middle_aged"]
  }
}
```

`filters` 从过滤前的完整目录生成。目录包含已禁用音色；`status` 只控制本次结果。

端点错误：

- `status=archived` → `400 {"detail":"无效的音色状态"}`；
- `page` 或 `page_size` 不是整数 → FastAPI `422` 校验响应；
- 未知 provider/model 等普通筛选值不是错误，返回空 `voices` 和 `total: 0`；
- 无会话 → 上述 `401`。

## 修改年龄或启用状态

```http
PATCH /api/voices/{voice_key}
Content-Type: application/json
```

请求对象至少包含 `age` 或 `enabled`，也可同时提交。其他字段当前会被忽略；如果对象只有其他字段，仍按缺少可修改字段处理：

```bash
curl -sS -b /tmp/storyteller-cookies.txt \
  -X PATCH \
  -H 'Content-Type: application/json' \
  -d '{"age":["child","teen"],"enabled":false}' \
  'http://127.0.0.1:8000/api/voices/mock%7Cunknown%7Cnarrator_01'
```

`age` 是由以下枚举组成的数组：`child`、`teen`、`young_adult`、`middle_aged`、`senior`。空数组合法；重复值会因规范化后长度改变而被拒绝。`enabled` 必须是 JSON 布尔值，不能用字符串 `"false"`。

`200 OK` 返回更新后的完整 voice 对象：

```json
{
  "key": "mock|unknown|narrator_01",
  "provider": "mock",
  "model": null,
  "voice_id": "narrator_01",
  "name": "少儿故事",
  "gender": "female",
  "age": ["child", "teen"],
  "category": "有声阅读",
  "description": "语调活泼亲切，适配儿童故事的治愈旁白女声",
  "tags": [],
  "clip_count": 2,
  "has_clips": true,
  "enabled": false
}
```

修改写入 `<data_dir>/config/voice-overrides.json`。端点错误：

- key 不在当前 catalog → `404 {"detail":"音色不存在"}`；
- 非法 JSON → `400 {"detail":"请求体必须是 JSON"}`；
- JSON 顶层不是对象 → `400 {"detail":"请求体必须是 JSON 对象"}`；
- `age` 不是字符串数组 → `400 {"detail":"age 必须是年龄枚举数组"}`；
- 未知或重复年龄 → `400 {"detail":"包含无效年龄"}`；
- `enabled` 不是布尔值 → `400 {"detail":"enabled 必须是布尔值"}`；
- 两个字段都缺少 → `400 {"detail":"必须提供 age 或 enabled"}`；
- 无会话 → `401`。

两个字段的处理当前不是事务：服务端先校验并写入 `age`，再校验 `enabled`。因此不要在同一请求中把合法 `age` 与非法 `enabled` 混用；这种请求虽返回 400，年龄修改已经落盘。官方页面分开提交两个字段，不会触发这一组合边界。

## 列出试听片段

```http
GET /api/voices/{voice_key}/clips
```

认证请求示例：

```bash
curl -sS -b /tmp/storyteller-cookies.txt \
  'http://127.0.0.1:8000/api/voices/mock%7Cunknown%7Cnarrator_01/clips'
```

`200 OK` 响应示例：

```json
{
  "clips": [
    {
      "clip_id": "proj_abc:line-1",
      "project_id": "proj_abc",
      "story_title": "测试故事",
      "character_name": "旁白",
      "text": "一段旁白",
      "created_at": "2026-09-24T10:30:00+08:00",
      "duration_ms": null,
      "audio_url_id": "proj_abc:line-1"
    }
  ]
}
```

没有片段时仍返回 `200 {"clips":[]}`。只有项目目录内实际存在的 MP3 才会列出；损坏项目和缺失文件被跳过。

端点错误：未知 voice key → `404 {"detail":"音色不存在"}`；无会话 → `401`。

## 下载或播放片段音频

```http
GET /api/voices/{voice_key}/clips/{clip_id}/audio
```

`clip_id` 来自片段列表，也必须 URL 编码：

```bash
curl -b /tmp/storyteller-cookies.txt \
  -o /tmp/storyteller-voice-clip.mp3 \
  'http://127.0.0.1:8000/api/voices/mock%7Cunknown%7Cnarrator_01/clips/proj_abc%3Aline-1/audio'
```

成功响应是音频字节而不是 JSON：

```http
HTTP/1.1 200 OK
Content-Type: audio/mpeg
```

浏览器播放可直接把同一 URL 放入已登录同源页面的 `<audio controls>`；cookie 会随同源请求发送。

端点错误：

- voice key 不存在 → `404 {"detail":"音色不存在"}`；
- clip id 不存在、对应文件缺失，或 id 含 `/`、`\` → `404`；普通缺失片段由 handler 返回 `{"detail":"音频片段不存在"}`，含斜杠的路径也可能先由路由层返回通用 404；
- 无会话 → `401`。

## 状态与匹配的关系

列表 API 为管理目的加载启用和禁用音色。匹配器使用 registry 的默认列表，自动排除 `enabled: false` 的音色；年龄 override 也在候选池建立前应用。修改只影响后续列表/匹配调用，不会删除旧项目片段，也不会改写已经保存的角色分配。完整行为见[角色与音色匹配](../voice-matching.md)和[Web 音色管理](../voice-management.md)。
