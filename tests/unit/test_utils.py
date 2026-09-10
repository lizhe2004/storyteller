import logging

from storyteller.core.utils import generate_id, setup_logging


def test_generate_id_returns_string():
    gid = generate_id()
    assert isinstance(gid, str)
    assert len(gid) > 0


def test_generate_ids_are_unique():
    ids = {generate_id() for _ in range(100)}
    assert len(ids) == 100


def test_generate_id_with_prefix():
    gid = generate_id("proj_")
    assert gid.startswith("proj_")


def test_generate_id_default_length():
    gid = generate_id()
    # 12 hex chars
    assert len(gid) == 12


def test_setup_logging_sets_level():
    setup_logging("debug")
    assert logging.getLogger().level == logging.DEBUG
    setup_logging("info")
    assert logging.getLogger().level == logging.INFO
