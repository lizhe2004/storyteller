import json

from storyteller.providers.gemini.llm import GeminiAudioAnalyzer, normalize_voice_analysis, normalize_voice_summary


def test_normalize_gemini_audio_result_maps_age_and_bounds_confidence():
    result = normalize_voice_analysis({"observed_gender": "Female", "observed_age": "adult", "timbre": "温柔", "confidence": 2})
    assert result["observed_gender"] == "female"
    assert result["observed_age"] == "young_adult"
    assert result["timbre"] == ["温柔"]
    assert result["confidence"] == 1.0


def test_normalize_gemini_audio_result_maps_qualitative_confidence():
    result = normalize_voice_analysis({"confidence": "high"})
    assert result["confidence"] == 0.9


def test_analyzer_defaults_use_current_free_quota_models():
    analyzer = GeminiAudioAnalyzer(api_key="test-key")

    assert analyzer.model_sample == "gemini-3.5-flash-lite"
    assert analyzer.model_summary == "gemini-3.5-flash"


def test_normalize_accepts_chinese_gender_and_age_labels():
    result = normalize_voice_analysis({"observed_gender": "女", "observed_age": "青年"})

    assert result["observed_gender"] == "female"
    assert result["observed_age"] == "young_adult"


def test_normalize_translates_common_timbre_labels_to_chinese():
    result = normalize_voice_analysis({"timbre": ["warm", "gentle", "clear and bright"]})

    assert result["timbre"] == ["温暖", "温柔", "清晰明亮"]


def test_normalize_voice_summary_wraps_numeric_match_scores():
    result = normalize_voice_summary({"catalog_match": 0.8, "role_match": "invalid"})

    assert result["catalog_match"]["overall"] == 0.8
    assert result["role_match"]["overall"] == 0.0
