import logging

from storyteller.core.utils import setup_logging


def test_setup_logging_writes_readable_file_log(tmp_path):
    setup_logging("info", log_dir=tmp_path)
    logger = logging.getLogger("test.logging")

    logger.info("event=voice_matching_started job_id=job_1")

    contents = (tmp_path / "storyteller.log").read_text(encoding="utf-8")
    assert "INFO" in contents
    assert "test.logging" in contents
    assert "event=voice_matching_started" in contents
    assert "job_id=job_1" in contents


def test_setup_logging_is_idempotent_for_same_log_dir(tmp_path):
    setup_logging("info", log_dir=tmp_path)
    setup_logging("info", log_dir=tmp_path)
    logger = logging.getLogger("test.idempotent")

    logger.info("event=once")

    contents = (tmp_path / "storyteller.log").read_text(encoding="utf-8")
    assert contents.count("event=once") == 1
