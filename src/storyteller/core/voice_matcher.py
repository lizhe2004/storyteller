from __future__ import annotations

import re

from .exceptions import ProviderError
from .models import VoiceConfig

_NARRATOR_KEYWORDS = ("旁白", "narrator", "说书", "叙述")
_NUMERIC_AGE = re.compile(r"(\d{1,2})\s*岁")
# Bare "孩子" is intentionally excluded: an adult described as "哄孩子"
# / "像个孩子" must not be mistaken for a child character.
_CHILD_WORDS = (
    "儿童", "小孩", "小孩子", "小朋友", "孩童",
    "男童", "女童", "小男孩", "小女孩", "婴儿", "宝宝",
    "幼年", "幼儿", "幼童", "幼崽",
)
_TEEN_WORDS = ("少年", "少女")
_SENIOR_WORDS = (
    "婆婆", "奶奶", "爷爷", "外公", "外婆", "老人", "老太太",
    "老爷爷", "老奶奶", "祖父", "祖母", "老翁", "老妇",
    "老年", "年迈", "高龄",
)
_MIDDLE_AGED_WORDS = (
    "妈妈", "爸爸", "阿姨", "叔叔", "姑姑", "婶婶", "舅舅",
    "伯父", "伯母", "大叔", "大婶", "中年",
)
# Kinship titles and pronouns disambiguate gender when the description
# never uses 男/女 (e.g. "企鹅妈妈，温柔耐心").
_FEMALE_WORDS = (
    "女", "妈妈", "妈", "阿姨", "姐姐", "奶奶", "外婆", "婆婆",
    "妹妹", "姑姑", "婶婶", "姑娘", "公主", "女王", "少女", "她",
)
_MALE_WORDS = (
    "男", "爸爸", "爸", "叔叔", "哥哥", "爷爷", "外公", "弟弟",
    "舅舅", "伯父", "先生", "王子", "少年", "他",
)

_AGE_LABELS = {
    "child": "儿童",
    "teen": "少年",
    "young_adult": "青年",
    "middle_aged": "中年",
    "senior": "老年",
}
_TYPE_LABELS = {
    "narrator": "旁白",
    "child": "儿童",
    "female": "女声",
    "male": "男声",
}
_GROUP_ORDER = ("narrator", "child", "female", "male")

_LLM_SYSTEM_PROMPT = (
    "你是一位经验丰富的广播剧配音导演。请根据每个角色的设定，"
    "从给定的候选音色中挑选最贴切的一个。\n"
    "规则：\n"
    "1. 每个角色必须且只能选择一个候选音色，用候选前面的序号表示。\n"
    "2. 旁白角色只能从【旁白】组中选择。\n"
    "3. 严格遵守性别：女性角色不可选男声，男性角色不可选女声。\n"
    "4. 年龄和气质要贴合：例如慈祥的老婆婆要避免年轻御姐音，"
    "优先中年/老年、语气温和缓慢的音色；孩子选儿童音色。\n"
    "5. 结合音色的名称、分类和描述里的语气、风格来判断，"
    "不要只看性别。\n"
    "6. 不同角色尽量选择不同的音色，序号不可重复。\n"
    "7. 只输出 JSON，不要任何额外文字，格式：\n"
    '{"assignments":[{"character_id":"角色id","voice_index":序号}]}'
)

_LLM_CLASSIFY_SYSTEM_PROMPT = (
    "你是配音选角助理。请只根据每个角色的名字和设定描述，判断其"
    "性别和年龄段，用于挑选配音音色。\n"
    "年龄段取值只能是：child(儿童，约0-12岁)、teen(少年，13-17岁)、"
    "young_adult(青年，18-45岁)、middle_aged(中年，46-59岁)、"
    "senior(老年，60岁以上)。\n"
    "注意：儿童故事里写成“男孩/女孩”的角色通常是 child；"
    "出现婆婆/奶奶/爷爷等是 senior；妈妈/爸爸/阿姨/叔叔多为 middle_aged。"
    "gender 只能是 male 或 female。\n"
    "只输出 JSON，不要任何额外文字，格式：\n"
    '{"characters":[{"character_id":"角色id","gender":"male|female",'
    '"age":"child|teen|young_adult|middle_aged|senior"}]}'
)

_AGE_BANDS = ("child", "teen", "young_adult", "middle_aged", "senior")
_GENDERS = ("male", "female")


def _infer_voice_type(description):
    """Guess a voice_type from a character description.

    voice_type is one of: narrator, child, male, female. A child-age band
    (driven by _infer_age) yields child; otherwise gender comes from
    explicit words, kinship titles, or pronouns, defaulting male. Age is
    the authority for childhood so an adult "哄孩子" is not misread.
    """
    desc = description or ""
    if _infer_age(desc) == "child":
        return "child"
    if any(word in desc for word in _FEMALE_WORDS):
        return "female"
    if any(word in desc for word in _MALE_WORDS):
        return "male"
    return "male"


def _infer_age(description):
    """Guess an age band from a character description.

    Returns one of child/teen/young_adult/middle_aged/senior. Used as a
    soft hint for semantic matching within a gender-constrained pool.
    """
    desc = description or ""
    match = _NUMERIC_AGE.search(desc)
    if match:
        years = int(match.group(1))
        if years <= 12:
            return "child"
        if years <= 17:
            return "teen"
        if years <= 45:
            return "young_adult"
        if years <= 59:
            return "middle_aged"
        return "senior"
    if any(word in desc for word in _SENIOR_WORDS):
        return "senior"
    if any(word in desc for word in _MIDDLE_AGED_WORDS):
        return "middle_aged"
    if any(word in desc for word in _TEEN_WORDS):
        return "teen"
    if any(word in desc for word in _CHILD_WORDS):
        return "child"
    return "young_adult"


def _type_preference(wanted_type):
    """Fallback order of voice types.

    Dialogue characters should keep to character voices: narrator voices
    are the last resort, so a missing female/male voice never silently
    becomes a narrator timbre.
    """
    if wanted_type == "narrator":
        return ["narrator", "female", "male", "child"]
    if wanted_type == "child":
        return ["child", "female", "male", "narrator"]
    if wanted_type == "female":
        return ["female", "child", "male", "narrator"]
    return ["male", "child", "female", "narrator"]


def _is_narrator(character):
    text = "{} {}".format(character.id, character.name).lower()
    return any(kw in text for kw in _NARRATOR_KEYWORDS)


class VoiceMatcher:
    """Assigns a VoiceConfig to every character in a script.

    mode="llm" asks the LLM to semantically pick voices using each
    candidate's name/age/category/description, constrained to the inferred
    gender/age/narrator type; any character the LLM cannot validly assign
    falls back to deterministic rule matching. mode="rule" skips the LLM.
    """

    def __init__(self, registry, llm=None, mode="rule"):
        self.registry = registry
        self.llm = llm
        self.mode = mode

    def match_voices(
        self,
        script,
        allowed_providers=None,
        allowed_voice_ids=None,
        default_provider=None,
    ):
        if not script.characters:
            return script

        if allowed_providers is None:
            allowed_providers = self.registry.list_tts_names()

        voices = self.registry.list_tts_voices(
            allowed_providers, allowed_voice_ids=allowed_voice_ids
        )
        if not voices:
            raise ProviderError(
                "No TTS voices available for providers: {}".format(
                    ", ".join(allowed_providers)
                )
            )

        by_type = {}
        for voice in voices:
            by_type.setdefault(voice.voice_type, []).append(voice)

        narrators = [c for c in script.characters if _is_narrator(c)]
        others = [c for c in script.characters if not _is_narrator(c)]
        ordered = narrators + others

        wanted = {c.id: ("narrator", None) for c in narrators}
        classified = {}
        if self.mode == "llm" and self.llm is not None and others:
            classified = self._classify_characters(others)
        for character in others:
            text = "{} {}".format(character.name, character.description)
            if character.id in classified:
                gender, age = classified[character.id]
                vtype = "child" if age == "child" else gender
            else:
                # Rule fallback for characters the LLM call did not resolve.
                vtype, age = _infer_voice_type(text), _infer_age(text)
            wanted[character.id] = (vtype, age)

        used_ids = set()
        llm_picks = {}
        if self.mode == "llm" and self.llm is not None:
            llm_picks = self._safe_llm_assign(
                ordered, wanted, by_type
            )
            for voice in llm_picks.values():
                used_ids.add(voice.voice_id)

        for character in ordered:
            if character.id in llm_picks:
                character.voice_config = llm_picks[character.id]
                continue
            wanted_type = wanted[character.id][0]
            chosen = self._rule_pick(
                by_type, wanted_type, used_ids, default_provider
            )
            character.voice_config = chosen
            used_ids.add(chosen.voice_id)

        return script

    def _classify_characters(self, characters):
        """LLM call #1: decide gender + age band per character.

        Returns {character_id: (gender, age)}. Only valid entries are
        included; the method never raises (call/parse failures yield {}),
        so unresolved characters fall back to keyword rules.
        """
        char_lines = [
            '- character_id={} 「{}」：{}'.format(
                c.id, c.name, c.description or "-"
            )
            for c in characters
        ]
        user_content = (
            "待判定角色：\n{}\n\n请判断每个角色的性别和年龄段，"
            "按规定只输出 JSON。"
        ).format("\n".join(char_lines))
        messages = [
            {"role": "system", "content": _LLM_CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        try:
            response = self.llm.chat(messages, temperature=0.0)
        except Exception:
            return {}

        from .story_generator import _extract_json

        data = _extract_json(response)
        if not isinstance(data, dict):
            return {}
        items = data.get("characters")
        if not isinstance(items, list):
            return {}

        result = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("character_id")
            gender = item.get("gender")
            age = item.get("age")
            if cid not in {c.id for c in characters}:
                continue
            if gender not in _GENDERS or age not in _AGE_BANDS:
                continue
            result[str(cid)] = (gender, age)
        return result

    def _safe_llm_assign(self, ordered, wanted, by_type):
        """Return {character_id: VoiceConfig} for valid LLM picks.

        Any failure (call error, unparseable JSON, out-of-range index,
        gender mismatch, duplicate) drops the affected character so the
        caller fills it with rule matching; the method never raises.
        """
        try:
            candidates, response = self._request_llm(
                ordered, wanted, by_type
            )
        except Exception:
            return {}

        from .story_generator import _extract_json

        data = _extract_json(response)
        if not isinstance(data, dict):
            return {}
        items = data.get("assignments")
        if not isinstance(items, list):
            return {}

        picks = {}
        used_index = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            char_id = item.get("character_id")
            index = item.get("voice_index")
            if char_id is None or char_id not in wanted:
                continue
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            if not 1 <= index <= len(candidates):
                continue
            if index in used_index:
                continue
            voice = candidates[index - 1]
            # Hard constraint: narrator/child/gender type must agree.
            if voice.voice_type != wanted[char_id][0]:
                continue
            picks[str(char_id)] = voice
            used_index.add(index)
        return picks

    def _request_llm(self, ordered, wanted, by_type):
        needed = []
        for character in ordered:
            vtype = wanted[character.id][0]
            if vtype not in needed:
                needed.append(vtype)
        group_order = [t for t in _GROUP_ORDER if t in needed]

        candidates = []
        lines = []
        for vtype in group_order:
            lines.append("【{}】".format(_TYPE_LABELS.get(vtype, vtype)))
            for voice in by_type.get(vtype, []):
                candidates.append(voice)
                index = len(candidates)
                lines.append(
                    "[{}] {} | {} | {} | {}".format(
                        index,
                        voice.name or voice.voice_id,
                        _AGE_LABELS.get(voice.age, voice.age or "-"),
                        voice.category or "-",
                        voice.description or "-",
                    )
                )

        char_lines = []
        for character in ordered:
            vtype, age = wanted[character.id]
            char_lines.append(
                "- character_id={} 「{}」：{} ｜ 需要声线={} 年龄={}".format(
                    character.id,
                    character.name,
                    character.description or "-",
                    _TYPE_LABELS.get(vtype, vtype),
                    _AGE_LABELS.get(age, age or "-"),
                )
            )

        user_content = (
            "候选音色列表：\n{}\n\n"
            "待分配角色：\n{}\n\n"
            "请为每个角色选择一个候选序号，按规定只输出 JSON。"
        ).format("\n".join(lines), "\n".join(char_lines))
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        response = self.llm.chat(messages, temperature=0.0)
        return candidates, response

    def _rule_pick(self, by_type, wanted_type, used_ids, default_provider):
        """Deterministic selection used at init and as LLM fallback."""
        candidates = [
            voice
            for vtype in _type_preference(wanted_type)
            for voice in by_type.get(vtype, [])
        ]

        for voice in candidates:
            if voice.voice_id in used_ids:
                continue
            if (
                default_provider
                and voice.provider != default_provider
                and _any_available(by_type, used_ids, default_provider)
            ):
                continue
            return voice

        # Nothing unused: reuse the first candidate.
        return candidates[0] if candidates else _flatten(by_type)[0]


def _flatten(by_type):
    result = []
    for voices in by_type.values():
        result.extend(voices)
    return result


def _any_available(by_type, used_ids, provider):
    return any(
        v.provider == provider and v.voice_id not in used_ids
        for v in _flatten(by_type)
    )
