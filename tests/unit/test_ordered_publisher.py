import pytest

from storyteller.core.exceptions import TTSError
from storyteller.web.streaming import _OrderedAudioPublisher


class _NeverCanceled:
    def is_set(self):
        return False


class FakeJob:
    def __init__(self):
        self.cancel_event = _NeverCanceled()
        self.frames = []

    def emit_bytes(self, data):
        self.frames.append(bytes(data))


def make(phases=("opening", "start_notice"), **kwargs):
    job = FakeJob()
    return job, _OrderedAudioPublisher(job, list(phases), **kwargs)


def test_head_phase_streams_each_frame_before_commit():
    job, pub = make()
    lease = pub.lease("opening")
    lease.publish(b"\x01\x00")
    assert job.frames == [b"\x01\x00"]  # already on the wire, not buffered
    lease.publish(b"\x02\x00")
    assert job.frames == [b"\x01\x00", b"\x02\x00"]
    lease.commit()


def test_head_phase_is_not_capped_at_64_frames():
    # A multi-second realtime opening/line emits hundreds of small packets.
    job, pub = make()
    lease = pub.lease("opening")
    for i in range(500):
        lease.publish(bytes((i % 251,)) + b"\x00")
    lease.commit()
    assert len(job.frames) == 500


def test_buffered_notice_stays_silent_until_commit_even_after_head_releases():
    # The start notice (like formal lines) is all-or-nothing: it must not leak
    # frames before commit, so a realtime failure can still swap in whole-file TTS.
    job, pub = make()
    notice = pub.lease("start_notice")
    notice.publish(b"\x09\x00")          # buffered: head not released yet
    assert job.frames == []
    pub.skip("opening")
    assert job.frames == []              # still buffered until the notice commits
    notice.publish(b"\x0a\x00")
    assert job.frames == []
    notice.commit()
    assert job.frames == [b"\x09\x00", b"\x0a\x00"]


def test_buffered_phase_holds_more_than_64_packets_and_emits_atomically():
    # A long formal line is one clip of PCM; the old 64-packet cap must not apply.
    job, pub = make(phases=("line",), live_phases=("opening",))
    lease = pub.lease("line")
    for i in range(300):
        lease.publish(bytes((i % 251,)) + b"\x00")
    assert job.frames == []
    lease.commit()
    assert len(job.frames) == 300


def test_abort_before_first_byte_allows_a_fresh_fallback_lease():
    # Models the opening HTTP fallback: the realtime lease aborts with zero
    # bytes, then a new lease synthesizes and streams the fallback in order.
    job, pub = make()
    realtime = pub.lease("opening")
    realtime.abort()
    assert job.frames == []
    fallback = pub.lease("opening")
    fallback.publish(b"\x07\x00")
    assert job.frames == [b"\x07\x00"]
    fallback.commit()


def test_skip_after_partial_streaming_releases_without_dropping_sent_frames():
    job, pub = make()
    lease = pub.lease("opening")
    lease.publish(b"\x03\x00")
    lease.abort()                       # cannot unsend the already-played byte
    pub.skip("opening")
    notice = pub.lease("start_notice")
    notice.publish(b"\x04\x00")
    notice.commit()
    assert job.frames == [b"\x03\x00", b"\x04\x00"]


def test_committed_phase_cannot_be_reopened_and_stale_frames_are_rejected():
    _, pub = make()
    lease = pub.lease("opening")
    lease.commit()
    with pytest.raises(TTSError):
        pub.lease("opening")
    with pytest.raises(TTSError):
        lease.publish(b"\x05\x00")
