from __future__ import annotations

import hmac
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "storyteller_session"


def require_login(request: Request):
    """Reject requests without a valid Web session cookie."""
    if not request.app.state.issuer.verify(
        request.cookies.get(SESSION_COOKIE)
    ):
        raise HTTPException(status_code=401, detail="未登录")


def check_password(password, passwords):
    given = (password or "").encode("utf-8")
    for stored in passwords or []:
        if stored.startswith("pbkdf2_sha256$"):
            try:
                _, iterations, salt, expected = stored.split("$", 3)
                actual = hashlib.pbkdf2_hmac(
                    "sha256", given, bytes.fromhex(salt), int(iterations)
                ).hex()
                if hmac.compare_digest(actual, expected):
                    return True
            except (ValueError, TypeError):
                continue
        elif hmac.compare_digest(given, stored.encode("utf-8")):
            # Environment-provided passwords remain compatible.
            return True
    return False


def hash_password(password):
    salt = secrets.token_bytes(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, salt.hex(), digest.hex()
    )


class TokenIssuer:
    def __init__(self, secret=None, ttl_days=30, fallback_secret=None):
        self.ephemeral = not secret
        # Without a configured secret the signing key is ephemeral, but it
        # must stay stable for the app's lifetime so runtime config reloads
        # do not invalidate every session.
        self._serializer = URLSafeTimedSerializer(
            secret or fallback_secret or secrets.token_hex(32),
            salt="storyteller-web",
        )
        self.ttl_seconds = int(ttl_days) * 86400

    def issue(self):
        return self._serializer.dumps({"v": 1})

    def verify(self, token):
        try:
            self._serializer.loads(token, max_age=self.ttl_seconds)
            return bool(token)
        except (BadSignature, SignatureExpired, TypeError):
            return False


class RateLimiter:
    def __init__(self, per_minute=10):
        self.per_minute = int(per_minute)
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def reconfigure(self, per_minute):
        with self._lock:
            self.per_minute = int(per_minute)

    def allow(self, key):
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
