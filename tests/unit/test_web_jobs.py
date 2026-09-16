import threading
from queue import Empty

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.runtime_settings import RuntimeSettingsStore
from storyteller.web.jobs import Job, JobManager, JobParams
from storyteller.web import streaming
from storyteller.web.streaming import StreamOrchestrator


def _queued_audio(job):
    frames = []
    while True:
        try:
            item = job.queue.get_nowait()
        except Empty:
            return frames
        if "_bytes" in item:
            frames.append(item["_bytes"])


def test_ordered_audio_publisher_releases_committed_phases_in_story_order():
    """Direct producer writes would emit notice/line frames before opening."""
    publisher_type = getattr(streaming, "_OrderedAudioPublisher", None)
    assert publisher_type is not None
    job = Job(JobParams(topic="ordered"))
    publisher = publisher_type(job, ["opening", "start_notice", ("line", 1)])
    opening = publisher.lease("opening")
    notice = publisher.lease("start_notice")
    line = publisher.lease(("line", 1))

    notice.publish(b"NN")
    line.publish(b"LL")
    opening.publish(b"OO")
    opening.commit()
    assert _queued_audio(job) == [b"OO"]

    notice.commit()
    assert _queued_audio(job) == [b"NN"]
    line.commit()
    assert _queued_audio(job) == [b"LL"]


def test_ordered_audio_publisher_discards_aborted_lease_and_late_frames():
    """A realtime line failure must not leak partial frames into its fallback."""
    publisher_type = getattr(streaming, "_OrderedAudioPublisher", None)
    assert publisher_type is not None
    job = Job(JobParams(topic="fallback"))
    publisher = publisher_type(job, [("line", 1)])
    realtime = publisher.lease(("line", 1))
    realtime.publish(b"RR")
    realtime.abort()

    with pytest.raises(TTSError):
        realtime.publish(b"XX")
    fallback = publisher.lease(("line", 1))
    fallback.publish(b"FF")
    fallback.commit()

    assert _queued_audio(job) == [b"FF"]


def test_ordered_audio_publisher_streams_live_line_frames_after_prior_phases():
    publisher_type = getattr(streaming, "_OrderedAudioPublisher", None)
    assert publisher_type is not None
    job = Job(JobParams(topic="live-line"))
    publisher = publisher_type(job, ["opening", "start_notice"])
    publisher.add_phase(("line", 1), live=True)
    opening = publisher.lease("opening")
    notice = publisher.lease("start_notice")
    line = publisher.lease(("line", 1))

    opening.commit()
    notice.commit()
    line.publish(b"L1")

    assert _queued_audio(job) == [b"L1"]


def test_ordered_audio_publisher_cancellation_rejects_late_producer_frames():
    """Cancellation must not let a reader thread publish after the job is terminal."""
    publisher_type = getattr(streaming, "_OrderedAudioPublisher", None)
    assert publisher_type is not None
    job = Job(JobParams(topic="cancel"))
    publisher = publisher_type(job, ["opening"])
    opening = publisher.lease("opening")
    publisher.cancel()

    with pytest.raises(TTSError):
        opening.publish(b"XX")
    assert _queued_audio(job) == []


def test_jobs_execute_with_the_snapshot_bound_at_submission(tmp_path):
    config = Config()
    config.set("web.host", "old.example.test")
    store = RuntimeSettingsStore(tmp_path, config)
    manager = JobManager(concurrency=2)
    release = threading.Event()
    completed = threading.Event()
    observed = {}

    def record_config(job):
        release.wait(timeout=2)
        observed[job.params.topic] = (
            job.config_snapshot.to_config().get("web.host")
        )
        if len(observed) == 2:
            completed.set()

    job_a = manager.create(JobParams(topic="A"))
    manager.submit(job_a, record_config, store.snapshot())
    store.update({"web": {"host": "new.example.test"}})
    job_b = manager.create(JobParams(topic="B"))
    manager.submit(job_b, record_config, store.snapshot())
    release.set()

    assert completed.wait(timeout=2)
    assert observed == {
        "A": "old.example.test",
        "B": "new.example.test",
    }


def test_submit_without_snapshot_keeps_existing_target_contract():
    manager = JobManager(concurrency=1)
    completed = threading.Event()
    observed = []
    job = manager.create(JobParams(topic="compatible"))

    def record_job(received_job):
        observed.append(received_job)
        completed.set()

    manager.submit(job, record_job)

    assert completed.wait(timeout=2)
    assert observed == [job]
    assert job.config_snapshot is None


def test_streaming_worker_builds_task_config_from_job_snapshot(
    tmp_path, monkeypatch
):
    global_config = Config()
    global_config.set("data_dir", str(tmp_path))
    global_config.set("web.host", "global.example.test")
    store = RuntimeSettingsStore(tmp_path, global_config)
    snapshot = store.update(
        {"web": {"host": "snapshot.example.test"}}
    )
    job = JobManager().create(JobParams(topic="snapshot"))
    job.config_snapshot = snapshot
    observed = []

    monkeypatch.setattr(
        StreamOrchestrator,
        "_run",
        lambda self, received_job: observed.append(
            (received_job, self.config.get("web.host"))
        ),
    )

    StreamOrchestrator(global_config, registry=object()).run(job)

    assert observed == [(job, "snapshot.example.test")]
