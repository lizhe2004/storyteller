from storyteller.core.config import Config


def test_web_defaults():
    cfg = Config()
    assert cfg.get("web.passwords") == []
    assert cfg.get("web.host") == "127.0.0.1"
    assert cfg.get("web.port") == 8000
    assert cfg.get("web.concurrency") == 2


def test_web_env(monkeypatch):
    monkeypatch.setenv("STORYTELLER_WEB_PASSWORDS", " abc, 123 ,, ")
    monkeypatch.setenv("STORYTELLER_WEB_PORT", "9000")
    cfg = Config.from_env(env_file="/nonexistent/.env")
    assert cfg.get("web.passwords") == ["abc", "123"]
    assert cfg.get("web.port") == 9000
