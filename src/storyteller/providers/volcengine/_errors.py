from __future__ import annotations

import json

_MAX_BODY_CHARS = 300


def http_error_detail(exc):
    """Describe a failed request, including Volcengine's error body.

    ``raise_for_status`` only reports the status line (e.g. ``400 Bad
    Request``), which hides the actual cause such as ``AccountOverdueError``.
    Ark returns ``{"error": {"code", "message"}}`` while the speech APIs
    return ``{"code", "message"}``; anything else falls back to a truncated
    raw body.
    """
    detail = str(exc)
    response = getattr(exc, "response", None)
    if response is None:
        return detail
    body = _response_body(response)
    if body:
        detail = "{} - {}".format(detail, body)
    return detail


def _response_body(response):
    try:
        text = response.text
    except Exception:  # noqa: BLE001 - body is best-effort diagnostics
        return ""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        error = data.get("error")
        source = error if isinstance(error, dict) else data
        code = source.get("code")
        message = source.get("message")
        if code is not None or message:
            return "{}: {}".format(code, message or "unknown")
    if len(text) > _MAX_BODY_CHARS:
        text = text[:_MAX_BODY_CHARS] + "..."
    return text
