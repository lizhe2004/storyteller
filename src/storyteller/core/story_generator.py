from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from partialjson.json_parser import JSONParser

from .exceptions import LLMError
from .llm import LLMProvider
from .models import Character, Script, ScriptLine, SoundEffect
from .utils import generate_id


logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = (
    "你是一位专业的广播剧编剧，作品面向一般听众，会被制作成只有声音、"
    "没有画面的音频故事或广播剧。请根据用户给定的故事主题，创作一个多角色的"
    "音频故事剧本，题材、语气和受众年龄随主题自然变化。\n\n"
    "要求：\n"
    "1. 剧本包含旁白和至少2个对话角色。characters 数组里必须始终包含一个"
    "专门的旁白角色（id 用 \"narrator\"，name 用 \"旁白\"），"
    "所有 narration 行都由它叙述。\n"
    "2. 严格以JSON格式输出，不要包含任何其他文字。格式如下：\n"
    '{\n'
    '  "title": "故事标题",\n'
    '  "opening": "开场白",\n'
    '  "characters": [\n'
    '    {"id": "narrator", "name": "旁白", "description": "故事旁白，叙述场景、动作和说话人"},\n'
    '    {"id": "角色id", "name": "角色名", "description": "角色性格/年龄/性别描述", '
    '"gender": "male|female", "age": "child|teen|young_adult|middle_aged|senior", '
    '"voice_preferences": [{"type": "音色类别", "weight": 0.7}]}\n'
    '  ],\n'
    '  "lines": [\n'
    '    {"line_id": "1", "line_type": "narration", "text": "旁白内容"},\n'
    '    {"line_id": "2", "line_type": "dialogue", "character_id": "角色id", "text": "台词", "direction": "这句台词怎么演"}\n'
    '  ]\n'
    '}\n'
    "3. 旁白的 line_type 为 narration，对话的 line_type 为 dialogue，"
    "对话必须提供 character_id。\n"
    "4. 每个角色必须单独给出 gender 和 age 字段；gender 只能是 male 或 female，"
    "age 只能是 child、teen、young_adult、middle_aged、senior。角色描述也请包含年龄、性别、性格等信息。\n"
    "5. 每个角色同时给出 voice_preferences 音色偏好数组，数组元素只有 type 和 weight 两个字段；"
    "type 必须从以下音色类别中选择：体育解说、儿童陪伴、初期催收提醒客服、动漫配音、"
    "医院社区引导型客服、古风有声书、商务汇报、娱乐搞笑、引导新手型客服、情感陪伴、"
    "新品推荐型客服、新闻播报、日常对话、智能助手、智能客服、有声书配音、有声阅读、"
    "标准通用型客服、核保理赔型客服、深夜电台、理财咨询型客服、理财顾问型客服、"
    "电商直播、监察回访型客服、知识分享、社交互动、社交陪伴、角色扮演、讲解引导型客服、"
    "账单提醒型客服。weight 是大于0的数字，所有权重加起来为1。"
    "最多给出5个最相关类别，按偏好强弱排序。\n\n"
    "声音媒介规则（听众看不到画面、角色名和说话人标签，只能靠耳朵）：\n"
    "5. 开场第一段旁白必须交代清楚时间、地点、主角是谁以及当下的处境，"
    "让听众在第一句对话前就进入故事场景。\n"
    "6. 每个角色第一次开口说话之前，旁白必须先用名字点名引出"
    "（例如“小兔子着急地说：”“这时，小松鼠跳了过来”），"
    "或在紧邻的旁白里明确介绍这个角色；新角色登场时同样如此。\n"
    "7. 不要让听众靠声音去猜是谁在说话。连续几句对话来回切换时，"
    "用旁白穿插说话人、动作或神态；对话开头少用没有指代的代词。\n"
    "8. 台词尽量自包含信息，角色名应在故事前半段就让听众听到，"
    "而不是到结尾才出现。\n"
    "9. 场景或地点转换时，用旁白交代，避免无铺垫的硬转场。\n\n"
    "演法指令 direction（用于语音合成的“导演说戏”，只写对话行）：\n"
    "10. 每句对话都要给出 direction，用一句简短自然语言描述这句台词"
    "的语气、情绪和说话状态，贴合角色与剧情，例如"
    "“又急又慌，带着哭腔”“压低声音像在讲秘密”“开心得跳起来”。\n"
    "11. direction 是给配音的提示，不是台词本身：不要写台词内容，"
    "不加引号，不超过20个字，避免“开心/难过”这类笼统词，尽量具体可演。\n"
    "12. 旁白行不要写 direction。\n"
    "13. 按以下顺序生成：标题、等待期故事开场白、角色信息、正文台词。"
    "优先尽快输出等待期故事开场白；它用于在正式角色音色匹配期间播放，"
    "控制在15～35个汉字以内，不属于正文台词，也不会进入最终故事音频。"
    "生成过程中允许系统按已经产生的文字增量合成语音，因此不要改写已经输出的开头。\n"
)


_SOUND_PROMPT = (
    "\n音效与背景音乐（可选，宁缺毋滥，整个短篇通常只给0-1条背景音乐和"
    "少数几个关键音效）：\n"
    "13. 可以在顶层给一个贯穿全剧的背景音乐 background_music，"
    "格式 {\"name\":\"名称\",\"type\":\"music\","
    "\"description\":\"这是什么音乐\",\"prompt\":\"给声音生成模型的描述\"}。\n"
    "14. 可以在某一行（必须是有 text 的旁白或对话行）里给 sound_effects 数组，元素格式 "
    "{\"name\":\"名称\",\"type\":\"effect 或 ambient\","
    "\"description\":\"这是什么声音\",\"prompt\":\"给声音生成模型的描述\","
    "\"anchor\":\"触发该声音的、本行里逐字出现的短语\"}。"
    "effect 是短促音效（如敲门、打雷、肚子叫），ambient 是持续环境声（如树林鸟鸣、集市嘈杂）。"
    "音效就写在触发它的那一（几）行上；严禁创建只有音效、没有 text 的独立行，"
    "line_type 只能是 narration 或 dialogue。\n"
    "15. prompt 只描述声音或音乐本身（乐器、节奏、情绪、环境），"
    "严禁包含任何人声、台词、说话或歌词；要自包含、简短具体。\n"
    "16. 写 prompt 必须让人一听就知道声源：写清「什么东西/谁」+「在做什么动作」+"
    "「声音质感与节奏、响几声」+（需要时）远近/空间，不要用不相干的声音打比方。\n"
    "17. anchor 仅 effect 必填、ambient 不填：必须是本行 text 里**逐字出现**的短句，"
    "正是这个声音发生的地方（如 text 里的“肚子咕咕叫了起来”）。"
    "一行有先后两个音效时，各自锚定对应的短语，不要都写句首。\n"
    "18. **声音必须在剧本里有据可依**：音效只能给本行 text 已经明确写到的"
    "动作、物体或环境声。听众看不到画面，如果一句台词里根本没有提到拔剑，"
    "就不要在这句台词上挂剑声——需要这个声音，就先在旁白里把动作写出来，"
    "再把音效挂到那句旁白上。严禁给台词配画外声音。\n"
    "19. 背景音乐描述整体情绪基调；没有合适的声音就直接省略对应字段，"
    "不要硬加。\n"
    "prompt 正反例：\n"
    "  肚子叫 ✔“人肚子饿时咕咕叫的声音，低沉冒泡，两三声，近景，无人声”；"
    "✘“咕噜咕噜的水声”（错：那是水声不是肚子叫）\n"
    "  脚步 ✔“沉稳的成年男人脚步声，布鞋踩在泥地上，一步一步走近，五六步，无人声”\n"
    "  卷帘门 ✔“金属卷帘门被拉下的哗啦声，持续两三秒后哐当到底，无人声”\n"
    "  水桶入水 ✔“木桶探入溪水再提起的泼溅水声，两三次，无人声”；"
    "✘“水花溅起声”（太笼统）\n"
    "示例片段：\n"
    '  顶层："background_music": {"name":"冒险主题曲","type":"music",'
    '"description":"轻快温馨的管弦乐","prompt":"轻快温暖的管弦乐，'
    '木管与拨弦，适合故事冒险场景，无人声"}\n'
    '  行内："sound_effects": [{"name":"肚子咕噜","type":"effect",'
    '"description":"肚子饿的咕咕声","prompt":"人肚子饿时咕咕叫的声音，'
    '低沉冒泡，两三声，近景，无人声","anchor":"肚子咕咕叫了起来"}]\n'
)


class StoryGenerator:
    """Turns a topic into a Script by prompting an LLM.

    Owns the prompt-building and response-parsing business logic. Knows
    nothing about which LLM provider is used.
    """

    def __init__(self, llm, system_prompt=None, sound_prompt=None):
        self.llm = llm
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.sound_prompt = sound_prompt if sound_prompt is not None else _SOUND_PROMPT

    def generate_script(
        self,
        topic,
        length="medium",
        complexity="simple",
        with_sound=False,
        **kwargs,
    ):
        system_content = self.system_prompt
        if with_sound:
            system_content = system_content + self.sound_prompt
        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": self._build_user_prompt(
                    topic, length, complexity
                ),
            },
        ]
        try:
            response = self.llm.chat(messages, **kwargs)
        except Exception as exc:
            raise LLMError("LLM call failed: {}".format(exc)) from exc
        return self._parse_response(response, topic)

    def generate_script_stream(
        self,
        topic,
        length="medium",
        complexity="simple",
        with_sound=False,
        on_preview=None,
        on_opening_delta: Optional[Callable[[str], None]] = None,
        on_opening_complete: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        """Generate a script while reporting partial JSON snapshots.

        ``on_preview`` receives speculative dictionaries produced by
        ``partialjson``. They are for display only. The returned ``Script``
        is parsed from the complete response and is the only authoritative
        value for downstream processing.

        ``on_opening_delta`` reports each new suffix of the opening field.
        ``on_opening_complete`` fires once, as soon as a non-opening key
        (``characters``/``lines``) appears in the stream: the opening is
        ordered first in the prompt, so that is when it is known in full and a
        realtime TTS session may stop accepting more text.
        """
        system_content = self.system_prompt
        if with_sound:
            system_content = system_content + self.sound_prompt
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": self._build_user_prompt(topic, length, complexity)},
        ]
        chunks = []
        last_preview = None
        last_opening_text = ""
        opening_protocol_error = False
        opening_complete_fired = False
        try:
            for chunk in self.llm.chat_stream(messages, **kwargs):
                if not chunk:
                    continue
                chunks.append(str(chunk))
                if on_preview is None and on_opening_delta is None and on_opening_complete is None:
                    continue
                try:
                    preview = JSONParser().parse("".join(chunks))
                except (TypeError, ValueError, SyntaxError):
                    continue
                if isinstance(preview, dict):
                    opening = str(preview.get("opening") or "")
                    if opening and not opening_protocol_error:
                        if opening.startswith(last_opening_text) and len(opening) > len(last_opening_text):
                            if on_opening_delta is not None:
                                on_opening_delta(opening[len(last_opening_text):])
                            last_opening_text = opening
                        elif opening != last_opening_text:
                            logger.warning("opening protocol error: already-sent prefix was rewritten")
                            opening_protocol_error = True
                    if not opening_complete_fired and on_opening_complete is not None:
                        if "characters" in preview or "lines" in preview:
                            on_opening_complete()
                            opening_complete_fired = True
                    snapshot = _script_preview_from_json(preview)
                    if on_preview is not None and snapshot != last_preview:
                        on_preview(snapshot)
                        last_preview = snapshot
        except Exception as exc:
            raise LLMError("LLM streaming call failed: {}".format(exc)) from exc
        response = "".join(chunks)
        return self._parse_response(response, topic)

    def refine_script(self, script, feedback, **kwargs):
        """Regenerate a script given feedback (reserved for later)."""
        raise NotImplementedError("refine_script not implemented")

    # ----- internals -----
    def _build_user_prompt(self, topic, length, complexity):
        return (
            "请围绕以下主题创作一个故事剧本：{}\n\n"
            "故事长度：{}\n"
            "剧本复杂度：{}"
        ).format(topic, length, complexity)

    def _parse_response(self, response, topic):
        data = _extract_json(response)
        if data is None:
            raise LLMError(
                "LLM returned unparseable content: {}".format(
                    _truncate(response, 200)
                )
            )
        return _script_from_json(data, topic)


_VALID_SOUND_TYPES = ("effect", "ambient", "music")


def _sound_from_llm(raw, fallback_type):
    """Build a not-yet-synthesized SoundEffect from an LLM sound cue.

    Returns None when there is no usable generation prompt. The cue has no
    local file yet: source_type is "builtin" and source_path stays None
    until the pipeline materializes it through the SoundLibrary.
    """
    if not isinstance(raw, dict):
        return None
    prompt = str(raw.get("prompt") or "").strip()
    if not prompt:
        return None
    sound_type = str(raw.get("type") or fallback_type).strip()
    if sound_type not in _VALID_SOUND_TYPES:
        sound_type = fallback_type
    name = str(raw.get("name") or prompt[:12]).strip()
    description = str(raw.get("description") or "").strip()
    anchor_raw = str(raw.get("anchor") or "").strip()
    anchor = anchor_raw or None
    tags_raw = raw.get("tags") or []
    tags = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []
    return SoundEffect(
        effect_id=generate_id("sfx_"),
        name=name,
        type=sound_type,
        source_path=None,
        source_type="builtin",
        prompt=prompt,
        description=description,
        tags=tags,
        anchor=anchor,
    )


def _extract_json(text):
    """Extract a JSON object from LLM output.

    Handles responses wrapped in markdown code fences (```json ... ```)
    or with surrounding prose.
    """
    if not text:
        return None
    text = text.strip()

    # Try parsing directly first.
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    # Strip code fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except (ValueError, TypeError):
            pass

    # Find the first {...} block as a last resort.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            pass

    return None


def _script_preview_from_json(data):
    """Return a UI-safe, best-effort snapshot of a partial script object."""
    characters = []
    for raw in data.get("characters") or []:
        if not isinstance(raw, dict):
            continue
        characters.append({
            "id": str(raw.get("id") or ""),
            "name": str(raw.get("name") or ""),
            "description": str(raw.get("description") or ""),
        })
    lines = []
    for raw in data.get("lines") or []:
        if not isinstance(raw, dict):
            continue
        lines.append({
            "line_id": str(raw.get("line_id") or len(lines) + 1),
            "line_type": str(raw.get("line_type") or "narration"),
            "character_id": raw.get("character_id"),
            "text": str(raw.get("text") or ""),
        })
    return {
        "title": str(data.get("title") or ""),
        "opening": str(data.get("opening") or ""),
        "characters": characters,
        "lines": lines,
    }


def _script_from_json(data, topic):
    characters = []
    char_lookup = {}
    for idx, raw_char in enumerate(data.get("characters") or []):
        char = Character(
            id=str(raw_char.get("id") or "char_{}".format(idx)),
            name=str(raw_char.get("name") or "角色{}".format(idx + 1)),
            description=str(raw_char.get("description") or ""),
            gender=_character_gender(raw_char.get("gender")),
            age=_character_age(raw_char.get("age")),
            voice_preferences=_voice_preferences_from_llm(
                raw_char.get("voice_preferences")
            ),
        )
        characters.append(char)
        char_lookup[char.id] = char

    lines = []
    pending_sounds = []
    for raw_line in data.get("lines") or []:
        raw_type = str(raw_line.get("line_type") or "narration").strip()
        text = str(raw_line.get("text") or "").strip()
        char_id = raw_line.get("character_id")
        own_sounds = [
            s
            for s in (
                _sound_from_llm(raw, "effect")
                for raw in (raw_line.get("sound_effects") or [])
            )
            if s is not None
        ]
        own_bgm = _sound_from_llm(raw_line.get("background_music"), "music")

        # The model sometimes emits a standalone sound-only "line"
        # (line_type "sound_effects", empty text). That is not a spoken
        # line: defer its cues onto the next real line so they are mixed at
        # the right moment without a wasted TTS call on an empty string.
        sound_marker = raw_type.lower() in (
            "sound_effects", "sfx", "sound_effect", "sound",
        )
        if sound_marker or not text:
            pending_sounds.extend(own_sounds)
            if own_bgm is not None:
                pending_sounds.append(own_bgm)
            continue

        metadata = {}
        direction = raw_line.get("direction")
        if direction:
            metadata["direction"] = str(direction).strip()
        line_type = "dialogue" if raw_type == "dialogue" else "narration"
        cues = _cues_for_line(pending_sounds + own_sounds, text)
        pending_sounds = []
        lines.append(
            ScriptLine(
                line_id=str(raw_line.get("line_id") or generate_id("l_")),
                line_type=line_type,
                character_id=str(char_id) if char_id else None,
                text=text,
                sound_effects=cues,
                background_music=own_bgm,
                metadata=metadata,
            )
        )

    # A trailing sound-only marker has no later line to attach to: keep its
    # beds/music on the last line, and drop any effect whose anchor is absent
    # from that line (same evidence rule as above).
    if pending_sounds and lines:
        lines[-1].sound_effects.extend(
            _cues_for_line(pending_sounds, lines[-1].text)
        )

    has_narration = any(line.line_type == "narration" for line in lines)
    if has_narration and not _has_narrator(characters):
        # The LLM often omits a narrator character even though it emits
        # narration lines. Inject one so voice matching assigns a narrator
        # timbre instead of the first dialogue character's voice.
        narrator_id = (
            "narrator" if "narrator" not in char_lookup else generate_id("narrator_")
        )
        narrator = Character(
            id=narrator_id,
            name="旁白",
            description="故事旁白，负责叙述时间地点、场景、动作和说话人",
            gender=None,
            age=None,
            voice_preferences=[
                {"type": "有声阅读", "weight": 0.7},
                {"type": "有声书配音", "weight": 0.2},
                {"type": "深夜电台", "weight": 0.1},
            ],
        )
        characters.insert(0, narrator)
        char_lookup[narrator_id] = narrator

    top_bgm = _sound_from_llm(data.get("background_music"), "music")

    return Script(
        script_id=generate_id("script_"),
        title=str(data.get("title") or "未命名故事"),
        topic=topic,
        characters=characters,
        lines=lines,
        background_music=top_bgm,
        metadata={
            "length": data.get("length"),
            "complexity": data.get("complexity"),
        },
    )


_NARRATOR_KEYWORDS = ("旁白", "narrator", "说书", "叙述")


def _cues_for_line(cues, text):
    """Keep only cues the spoken line actually accounts for.

    A punctual effect without an anchor phrase that occurs verbatim in the
    line text describes a sound the listener gets no narration for — it
    would play out of nowhere — so drop the whole cue. Ambient beds and
    music carry no anchor and always start at the line head.
    """
    kept = []
    for cue in cues:
        if cue.type == "effect" and (not cue.anchor or cue.anchor not in text):
            continue
        kept.append(cue)
    return kept


def _has_narrator(characters):
    for char in characters:
        text = "{} {}".format(char.id, char.name).lower()
        if any(kw in text for kw in _NARRATOR_KEYWORDS):
            return True
    return False


def _voice_preferences_from_llm(raw):
    """Keep a small, normalized preference list from an LLM response."""
    if not isinstance(raw, list):
        return []
    preferences = []
    by_type = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        preference_type = str(item.get("type") or "").strip()
        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            continue
        if not preference_type or weight <= 0:
            continue
        if preference_type in by_type:
            by_type[preference_type]["weight"] += weight
        elif len(preferences) < 5:
            entry = {"type": preference_type, "weight": weight}
            preferences.append(entry)
            by_type[preference_type] = entry
    total = sum(item["weight"] for item in preferences)
    if not total:
        return []
    for item in preferences:
        item["weight"] = round(item["weight"] / total, 6)
    return preferences


def _character_gender(raw):
    value = str(raw or "").strip()
    return value if value in ("male", "female") else None


def _character_age(raw):
    value = str(raw or "").strip()
    return value if value in (
        "child", "teen", "young_adult", "middle_aged", "senior"
    ) else None


def _truncate(text, limit):
    text = text or ""
    return text[:limit] + ("..." if len(text) > limit else "")
