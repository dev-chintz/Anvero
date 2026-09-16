import time
from collections import defaultdict

from app.core.security_logger import SecurityLogger


class RateLimiter:
    """In-memory rate limiter for login attempts using sliding window."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed. Returns False if rate limit exceeded."""
        now = time.time()
        cutoff = now - self.window_seconds

        attempts = self.attempts[key]
        attempts[:] = [t for t in attempts if t > cutoff]

        if len(attempts) >= self.max_attempts:
            SecurityLogger.rate_limit_hit(key, len(attempts))
            return False

        attempts.append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining attempts for key."""
        now = time.time()
        cutoff = now - self.window_seconds
        attempts = [t for t in self.attempts[key] if t > cutoff]
        return max(0, self.max_attempts - len(attempts))
