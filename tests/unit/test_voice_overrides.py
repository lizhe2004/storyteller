import json

from storyteller.core.models import VoiceConfig
from storyteller.core.voice_overrides import VoiceOverrideStore, voice_key


def test_voice_key_includes_provider_model_and_voice_id():
    voice = VoiceConfig(provider="aliyun", model="model-a", voice_id="v1")

    assert voice_key(voice) == "aliyun|model-a|v1"


def test_voice_key_uses_unknown_for_missing_model():
    voice = VoiceConfig(provider="mock", voice_id="v1")

    assert voice_key(voice) == "mock|unknown|v1"


def test_store_normalizes_and_persists_age_override(tmp_path):
    path = tmp_path / "config" / "voice-overrides.json"
    store = VoiceOverrideStore(path)

    assert store.get_age("aliyun|model-a|v1") is None
    assert store.set_age(
        "aliyun|model-a|v1", ["senior", "child", "child", "teen"]
    ) == ["child", "teen", "senior"]

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["aliyun|model-a|v1"]["age"] == ["child", "teen", "senior"]
    assert store.get_age("aliyun|model-a|v1") == ["child", "teen", "senior"]
    assert list(path.parent.glob("*.tmp")) == []


def test_store_keeps_provider_and_model_overrides_isolated(tmp_path):
    store = VoiceOverrideStore(tmp_path / "overrides.json")
    store.set_age("aliyun|model-a|v1", ["child"])
    store.set_age("volcengine|model-a|v1", ["senior"])

    assert store.get_age("aliyun|model-a|v1") == ["child"]
    assert store.get_age("volcengine|model-a|v1") == ["senior"]


def test_apply_returns_copies_without_mutating_provider_voices(tmp_path):
    store = VoiceOverrideStore(tmp_path / "overrides.json")
    store.set_age("aliyun|model-a|v1", ["teen"])
    original = VoiceConfig(
        provider="aliyun", model="model-a", voice_id="v1", age=["child"]
    )

    applied = store.apply([original])

    assert applied[0].age == ["teen"]
    assert applied[0] is not original
    assert original.age == ["child"]


def test_store_defaults_voices_to_enabled_and_persists_disabled_state(tmp_path):
    store = VoiceOverrideStore(tmp_path / "overrides.json")
    key = "aliyun|model-a|v1"

    assert store.is_enabled(key) is True
    assert store.set_enabled(key, False) is False
    assert store.is_enabled(key) is False
    assert json.loads((tmp_path / "overrides.json").read_text())[key]["enabled"] is False
