# tests/conftest.py
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def _isolate_env_and_cwd(tmp_path, monkeypatch):
    """Keep tests independent of the developer's local .env.

    Config.from_env() calls load_dotenv, which mutates os.environ and
    discovers a .env by walking up from the current working directory.
    Run each test in an empty directory with all STORYTELLER_* vars
    stripped; monkeypatch restores both afterwards.
    """
    for key in list(os.environ):
        if key.startswith("STORYTELLER_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
