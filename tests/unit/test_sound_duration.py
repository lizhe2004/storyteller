"""Target-duration helpers for prompt-controlled sound generation.

seed-audio has no duration parameter: the desired length is appended to
text_prompt in natural language. Targets derive from the owning line's real
TTS duration (ambient fills the line; a punctual effect gets the window from
its anchor offset to the line's end).
"""

from storyteller.core.pipeline import (
    EFFECT_MAX_DURATION_SEC,
    MAX_SOUND_DURATION_SEC,
    MIN_SOUND_DURATION_SEC,
    build_sound_prompt,
    sound_duration_seconds,
)


def test_effect_uses_window_after_anchor_offset():
    # 10s line, anchor spoken at 4s -> 6s remain; grace widens to 8 but the
    # 6s effect cap binds.
    assert sound_duration_seconds("effect", 10.0, 4.0) == 6


def test_effect_near_line_end_gets_grace_tail():
    # 11.9s line, anchor fires at 10.9s: only 1s remains inside the line;
    # the 2s mix-time grace widens the generation target to ~3s.
    assert sound_duration_seconds("effect", 11.9, 10.9) == 3
    assert sound_duration_seconds("effect", 8.0, 7.5) == 3


def test_ambient_fills_whole_line_ignoring_offset():
    assert sound_duration_seconds("ambient", 10.0, 0.0) == 10
    assert sound_duration_seconds("music", 10.0, 0.0) == 10


def test_effect_without_anchor_uses_full_line_capped():
    assert sound_duration_seconds("effect", 8.0, 0.0) == 6
    assert sound_duration_seconds("effect", 23.3, 2.0) == 6


def test_seconds_round_to_nearest_whole_second():
    assert sound_duration_seconds("ambient", 7.6, 0.0) == 8
    assert sound_duration_seconds("ambient", 7.4, 0.0) == 7


def test_short_lines_clamp_to_minimum():
    assert sound_duration_seconds("effect", 0.1, 0.075) == MIN_SOUND_DURATION_SEC
    assert sound_duration_seconds("ambient", 0.1, 0.0) == MIN_SOUND_DURATION_SEC


def test_long_stories_cap_at_api_limit():
    assert sound_duration_seconds("music", 200.0, 0.0) == MAX_SOUND_DURATION_SEC


def test_missing_line_duration_yields_no_constraint():
    assert sound_duration_seconds("ambient", 0.0, 0.0) is None
    assert sound_duration_seconds("effect", None, 0.0) is None


def test_effect_directive_is_an_upper_bound():
    prompt = build_sound_prompt("一声炸雷，无人声", "effect", 10.0, 4.0)
    assert prompt.startswith("一声炸雷，无人声")
    assert "时长不超过6秒" in prompt


def test_ambient_directive_requests_sustained_length():
    prompt = build_sound_prompt("舒缓的下雨声，无人声", "ambient", 8.0, 0.0)
    assert "持续约8秒" in prompt


def test_no_constraint_returns_prompt_unchanged():
    assert build_sound_prompt("随便多长", "ambient", 0.0, 0.0) == "随便多长"
