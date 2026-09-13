from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "storyteller_session"


def check_password(password, passwords):
    given = (password or "").encode("utf-8")
    return any(hmac.compare_digest(given, p.encode("utf-8")) for p in (passwords or []))


class TokenIssuer:
    def __init__(self, secret=None, ttl_days=30):
        self.ephemeral = not secret
        self._serializer = URLSafeTimedSerializer(secret or secrets.token_hex(32), salt="storyteller-web")
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
