from __future__ import annotations

import re
import random
import logging
from time import perf_counter

from .exceptions import ProviderError
from .models import VoiceConfig
from .observability import log_event, timed_event

logger = logging.getLogger(__name__)

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
_GENDER_LABELS = {"male": "男", "female": "女"}
_AGE_RANK = {"child": 0, "teen": 1, "young_adult": 2,
             "middle_aged": 3, "senior": 4}
_GENDER_ORDER = {"female": 0, "male": 1}
NARRATION_CATEGORIES = {"有声阅读"}


def is_narration_voice(voice):
    """True for reading/narration-suited voices (soft signal, not a type)."""
    return voice.category in NARRATION_CATEGORIES


_LLM_SYSTEM_PROMPT = (
    "你是一位经验丰富的广播剧配音导演。请根据每个角色的设定，"
    "从给定的候选音色中挑选最贴切的一个。\n"
    "规则：\n"
    "1. 每个角色必须且只能选择一个候选音色，用候选前面的序号表示。\n"
    "2. 严格遵守性别：女性角色不可选男声，男性角色不可选女声；"
    "标注为旁白的角色无性别限制。\n"
    "3. 旁白角色优先选择「有声阅读」类、语气平稳连贯的音色；"
    "儿童故事也可以根据气质选择温暖的年轻音色或儿童音色。\n"
    "4. 年龄和气质要贴合：例如慈祥的老婆婆要避免年轻御姐音，"
    "优先中年/老年、语气温和缓慢的音色；孩子选儿童年龄段音色。\n"
    "5. 结合音色的名称、分类和描述里的语气、风格来判断，不要只看性别。\n"
    "6. 不同角色尽量选择不同的音色，序号不可重复。\n"
    "7. 只输出 JSON，不要任何额外文字，格式：\n"
    '{"assignments":[{"character_id":"角色id","voice_index":序号}]}'
)

_AGE_BANDS = ("child", "teen", "young_adult", "middle_aged", "senior")
_GENDERS = ("male", "female")


def _infer_gender(description):
    """Guess male/female from explicit words, kinship titles, pronouns.

    Defaults to male. Childhood no longer collapses gender: a child still
    has its own gender (age is tracked separately).
    """
    desc = description or ""
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


def _is_narrator(character):
    text = "{} {}".format(character.id, character.name).lower()
    return any(kw in text for kw in _NARRATOR_KEYWORDS)


def _age_distance(a, b):
    return abs(_AGE_RANK.get(a, 2) - _AGE_RANK.get(b, 2))


def _gender_pool(voices, gender):
    """Hard gender preference, falling back to neutral then any voice."""
    exact = [v for v in voices if v.gender == gender]
    if exact:
        return exact
    neutral = [v for v in voices if not v.gender]
    if neutral:
        return neutral
    return list(voices)


def _voice_sort_key(voice, age, narrator):
    if narrator:
        # Narration-suited voices first; ties by age then stable id.
        return (
            0 if is_narration_voice(voice) else 1,
            _AGE_RANK.get(voice.age, 9),
            voice.voice_id,
        )
    # Dialogue: reading voices are the last resort; otherwise nearest age.
    return (
        1 if is_narration_voice(voice) else 0,
        _age_distance(voice.age, age),
        _AGE_RANK.get(voice.age, 9),
        voice.voice_id,
    )


def _sample_voice_candidates(voices, gender, age, preferences,
                             limit=10, rng=None):
    """Sample a diverse, preference-weighted candidate pool for one role."""
    if not voices or limit <= 0:
        return []
    rng = rng or random
    eligible = _gender_pool(voices, gender) if gender is not None else list(voices)
    if age is not None:
        same_age = [voice for voice in eligible if voice.age == age]
        if same_age:
            eligible = same_age
    if len(eligible) <= limit:
        return list(eligible)

    preferences = [
        item for item in (preferences or [])
        if isinstance(item, dict) and item.get("type")
        and float(item.get("weight", 0) or 0) > 0
    ]
    preferred_types = {item["type"] for item in preferences}
    matched = {
        item["type"]: [voice for voice in eligible
                       if voice.category == item["type"]]
        for item in preferences
    }
    matched = {key: pool for key, pool in matched.items() if pool}
    fallback = [voice for voice in eligible
                if voice.category not in preferred_types]

    selected = []
    if fallback:
        selected.append(rng.choice(fallback))

    preferred_slots = min(limit - len(selected), sum(map(len, matched.values())))
    weights = {item["type"]: float(item["weight"]) for item in preferences}
    weight_total = sum(weights.get(key, 0.0) for key in matched)
    if preferred_slots and matched and weight_total:
        raw = {
            key: preferred_slots * weights.get(key, 0.0) / weight_total
            for key in matched
        }
        quotas = {key: int(value) for key, value in raw.items()}
        remaining = preferred_slots - sum(quotas.values())
        for key in sorted(raw, key=lambda item: raw[item] - quotas[item], reverse=True):
            if remaining <= 0:
                break
            if quotas[key] < len(matched[key]):
                quotas[key] += 1
                remaining -= 1
        for key, quota in quotas.items():
            selected.extend(rng.sample(matched[key], min(quota, len(matched[key]))))

    selected_ids = {voice.voice_id for voice in selected}
    remaining_pool = [voice for voice in eligible
                      if voice.voice_id not in selected_ids]
    if len(selected) < limit and remaining_pool:
        selected.extend(rng.sample(
            remaining_pool, min(limit - len(selected), len(remaining_pool))
        ))
    return selected[:limit]


class VoiceMatcher:
    """Assigns a VoiceConfig to every character in a script.

    mode="llm" asks the LLM to semantically pick voices using each
    candidate's name/age/category/description, matching by gender/age with
    a soft preference for 有声阅读 (narration-suited) voices on narrator
    characters; any character the LLM cannot validly assign falls back to
    deterministic rule matching. mode="rule" skips the LLM.
    """

    def __init__(self, registry, llm=None, mode="rule", log_context=None):
        self.registry = registry
        self.llm = llm
        self.mode = mode
        self.log_context = log_context or {}

    def match_voices(
        self,
        script,
        allowed_providers=None,
        allowed_voice_ids=None,
        default_provider=None,
    ):
        started = perf_counter()
        log_event(
            logger, logging.INFO, "voice_matching_started",
            context=self.log_context,
            character_count=len(script.characters), mode=self.mode,
        )
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

        narrators = [c for c in script.characters if _is_narrator(c)]
        others = [c for c in script.characters if not _is_narrator(c)]
        ordered = narrators + others

        # wanted[char_id] = (gender_or_None, age_or_None); narrator is (None, None).
        wanted = {c.id: (None, None) for c in narrators}
        for character in others:
            text = "{} {}".format(character.name, character.description)
            gender = character.gender if character.gender in _GENDERS else _infer_gender(text)
            age = character.age if character.age in _AGE_BANDS else _infer_age(text)
            wanted[character.id] = (gender, age)

        used_ids = set()
        llm_picks = {}
        if self.mode == "llm" and self.llm is not None:
            llm_picks = self._safe_llm_assign(ordered, wanted, voices)
            for voice in llm_picks.values():
                used_ids.add(voice.voice_id)

        for character in ordered:
            if character.id in llm_picks:
                character.voice_config = llm_picks[character.id]
                continue
            gender, age = wanted[character.id]
            chosen = self._rule_pick(
                voices, used_ids, default_provider,
                gender=gender, age=age, narrator=gender is None,
            )
            character.voice_config = chosen
            used_ids.add(chosen.voice_id)

        log_event(
            logger, logging.INFO, "voice_matching_completed",
            context=self.log_context,
            character_count=len(script.characters), mode=self.mode,
            duration_ms=int((perf_counter() - started) * 1000),
        )
        return script

    def _safe_llm_assign(self, ordered, wanted, voices):
        """Return {character_id: VoiceConfig} for valid LLM picks.

        Any failure (call error, unparseable JSON, out-of-range index,
        gender mismatch, duplicate) drops the affected character so the
        caller fills it with rule matching; the method never raises.
        """
        try:
            candidates, response = self._request_llm(ordered, wanted, voices)
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
            want_gender = wanted[char_id][0]
            voice = candidates[index - 1]
            # Hard constraint for dialogue only: gender must agree.
            # Narrators (want_gender is None) have no gender restriction.
            if want_gender is not None and voice.gender != want_gender:
                continue
            picks[str(char_id)] = voice
            used_index.add(index)
        return picks

    def _request_llm(self, ordered, wanted, voices):
        by_id = {}
        for character in ordered:
            gender, age = wanted[character.id]
            for voice in _sample_voice_candidates(
                voices, gender, age, character.voice_preferences
            ):
                by_id[voice.voice_id] = voice
        candidates = sorted(
            by_id.values(),
            key=lambda v: (
                0 if is_narration_voice(v) else 1,
                _GENDER_ORDER.get(v.gender, 9),
                _AGE_RANK.get(v.age, 9),
                v.voice_id,
            ),
        )
        lines = []
        for voice in candidates:
            index = len(lines) + 1
            gender_label = _GENDER_LABELS.get(voice.gender, "中性")
            lines.append(
                "[{}] {} | {} | {} | {} | {}".format(
                    index,
                    voice.name or voice.voice_id,
                    gender_label,
                    _AGE_LABELS.get(voice.age, voice.age or "-"),
                    voice.category or "-",
                    voice.description or "-",
                )
            )

        char_lines = []
        for character in ordered:
            gender, age = wanted[character.id]
            if gender is None:
                need = "旁白（无性别限制，优先有声阅读类）"
            else:
                need = "{}声，年龄={}".format(
                    _GENDER_LABELS.get(gender, gender),
                    _AGE_LABELS.get(age, age or "-"),
                )
            char_lines.append(
                "- character_id={} 「{}」：{} ｜ {}".format(
                    character.id,
                    character.name,
                    character.description or "-",
                    need,
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
        with timed_event(
            logger,
            "llm_request",
            context=self.log_context,
            provider=type(self.llm).__name__,
            candidate_count=len(candidates),
            character_count=len(ordered),
        ):
            response = self.llm.chat(
                messages,
                temperature=0.0,
            )
        return candidates, response

    def _rule_pick(self, voices, used_ids, default_provider,
                   *, gender, age, narrator):
        """Deterministic selection used at init and as LLM fallback."""
        pool = list(voices) if narrator else _gender_pool(voices, gender)
        ranked = sorted(pool, key=lambda v: _voice_sort_key(v, age, narrator))
        unused = [v for v in ranked if v.voice_id not in used_ids]
        if default_provider:
            on_default = [v for v in unused if v.provider == default_provider]
            if on_default:
                return on_default[0]
        if unused:
            return unused[0]
        # Every pool voice is already used: reuse the highest-ranked one.
        return ranked[0]
