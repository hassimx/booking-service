import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"pbkdf2_sha256:{ITERATIONS}:{salt}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split(":")
        new_digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(new_digest.hex(), digest)


# keeps failed logins in memory, so it resets on restart and is per process
class LoginLimiter:
    def __init__(self, max_failures: int = 5, window_seconds: int = 600):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.failures = defaultdict(deque)

    def _forget_old(self, key: str) -> deque:
        attempts = self.failures[key]
        while attempts and time.monotonic() - attempts[0] > self.window_seconds:
            attempts.popleft()
        return attempts

    def is_blocked(self, key: str) -> bool:
        return len(self._forget_old(key)) >= self.max_failures

    def add_failure(self, key: str) -> None:
        self._forget_old(key).append(time.monotonic())

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self.failures.clear()
        else:
            self.failures.pop(key, None)


login_limiter = LoginLimiter()
