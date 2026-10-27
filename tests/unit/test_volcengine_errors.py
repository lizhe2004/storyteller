import requests

from storyteller.providers.volcengine._errors import http_error_detail


class _Response:
    def __init__(self, text):
        self.text = text


def _error(text):
    return requests.HTTPError("400 Client Error", response=_Response(text))


def test_ark_error_shape():
    exc = _error('{"error":{"code":"InvalidEndpoint.ClosedEndpoint","message":"closed"}}')
    assert http_error_detail(exc) == (
        "400 Client Error - InvalidEndpoint.ClosedEndpoint: closed")


def test_speech_error_shape():
    exc = _error('{"code":45000001,"message":"quota exceeded"}')
    assert http_error_detail(exc) == "400 Client Error - 45000001: quota exceeded"


def test_non_json_body_is_truncated():
    detail = http_error_detail(_error("x" * 1000))
    assert detail.startswith("400 Client Error - xxx")
    assert detail.endswith("...")
    assert len(detail) < 400


def test_without_response_falls_back_to_exception_text():
    assert http_error_detail(requests.ConnectionError("boom")) == "boom"


def test_empty_body_is_omitted():
    assert http_error_detail(_error("  ")) == "400 Client Error"
