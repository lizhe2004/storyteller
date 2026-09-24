# 音效与背景音乐

## 剧本中的声音 cue

开启音效后，LLM 可以在 Script 顶层生成 `background_music`，也可以在有文本的 narration/dialogue line 上生成 `sound_effects`。音效 cue 至少包含 `name`、`type`、`description` 和 `prompt`；effect 还需要在当前文本中逐字出现的 `anchor`。系统不会把只有声音、没有文本的独立 line 当作可朗读台词。

`effect` 表示短促事件，`ambient` 表示持续环境声，`music` 表示背景音乐。音效 prompt 只描述声音本身，不应包含人声、台词或歌词；声音必须能从同一行文本中的动作/环境得到依据。

## 生成、缓存和混音

Pipeline 先拼接台词片段，再按 cue 生成或查找声音，最后混入最终故事。相同的模型、规范化后的 prompt 和音频格式会得到相同 fingerprint，命中全局 `SoundLibrary` 时不重复调用 Provider。新声音会写入全局目录和 `index.json`，项目原始生成片段保留在项目的 `sounds/` 目录，便于排查。

系统会检查生成音频是否可读且不是近乎静音；不合格文件不会加入全局库，最多重试三次。effect 会按触发位置和短时长限制，ambient/music 通常覆盖所属 line；混音时声音受 line 时长和相邻 line 边界约束。

## CLI

```bash
storyteller generate "雨夜里的小镇" --with-sfx --sound-provider volcengine
storyteller make-sound "远处持续的雨声，无人声" --kind ambient --tags 雨夜,环境
storyteller list-sounds 雨夜 --kind ambient
```

`--with-sfx` 需要独立的音效 Provider 配置；音效 key 不等于 TTS key。`make-sound` 直接写入全局音效库，`list-sounds` 按名称、描述、prompt 和标签检索。

