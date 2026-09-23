from urllib.parse import quote

from fastapi.testclient import TestClient

from storyteller.core.config import Config
from storyteller.core.models import Script, ScriptLine, VoiceConfig
from storyteller.core.project import ProjectManager
from storyteller.web.app import create_app
from storyteller.core.voice_overrides import voice_key


def _app(tmp_path):
    cfg = Config()
    cfg.set("web.passwords", ["pw"])
    cfg.set("web.secret", "test-secret")
    cfg.set("web.rate_limit_per_min", 0)
    cfg.set("data_dir", str(tmp_path))
    cfg.set("project_dir", str(tmp_path / "stories"))
    cfg.set("tts.providers", ["mock"])
    cfg.set("tts.provider_config.mock", {"type": "mock"})
    return create_app(cfg)


def _login(client):
    assert client.post("/api/auth", json={"password": "pw"}).status_code == 204


def _make_clip(tmp_path):
    manager = ProjectManager(tmp_path / "stories")
    state = manager.create_project(topic="测试故事")
    state.script = Script(
        script_id="script-1",
        title="测试故事",
        topic="测试",
        lines=[ScriptLine(
            line_id="line-1",
            line_type="narration",
            text="一段旁白",
            voice_config=VoiceConfig(
                provider="mock", voice_id="narrator_01", name="少儿故事"
            ),
        )],
    )
    manager.save_project(state)
    audio = manager.resolve_project_dir(state.project_id) / "audio" / "line-1.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"fake mp3")
    return state


def test_voice_management_requires_authentication_and_lists_filters(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/voices").status_code == 401
        _login(client)
        response = client.get("/api/voices", params={"provider": "mock", "gender": "female", "age": "young_adult"})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["page_size"] == 50
        assert all(item["provider"] == "mock" for item in body["voices"])


def test_voice_management_updates_age_and_returns_clips(tmp_path):
    state = _make_clip(tmp_path)
    key = voice_key(VoiceConfig(provider="mock", voice_id="narrator_01"))
    encoded_key = quote(key, safe="")
    with TestClient(_app(tmp_path)) as client:
        _login(client)
        update = client.patch("/api/voices/{}".format(encoded_key), json={"age": ["child", "teen"]})
        assert update.status_code == 200
        assert update.json()["age"] == ["child", "teen"]
        assert (tmp_path / "config" / "voice-overrides.json").is_file()

        clips = client.get("/api/voices/{}/clips".format(encoded_key))
        assert clips.status_code == 200
        assert clips.json()["clips"][0]["text"] == "一段旁白"

        audio = client.get("/api/voices/{}/clips/{}:line-1/audio".format(encoded_key, state.project_id))
        assert audio.status_code == 200
        assert audio.headers["content-type"].startswith("audio/mpeg")


def test_voice_management_rejects_invalid_age_unknown_voice_and_unsafe_clip(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        _login(client)
        key = quote("mock|unknown|narrator_01", safe="")
        assert client.patch("/api/voices/{}".format(key), json={"age": ["adult"]}).status_code == 400
        assert client.patch("/api/voices/no-such", json={"age": ["child"]}).status_code == 404
        assert client.get("/api/voices/{}/clips/%2E%2E%2Faudio".format(key)).status_code == 404
