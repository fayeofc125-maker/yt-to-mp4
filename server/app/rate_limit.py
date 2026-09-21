"""Submission rate limiting with local and Redis-backed adapters."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0
    scope: str | None = None


class RateLimiter(Protocol):
    def check_and_consume(self, client: str) -> RateLimitDecision: ...


@dataclass
class LocalRateLimiter:
    client_max: int = 10
    client_window: int = 3600
    global_max: int = 100
    global_window: int = 60
    clock: Callable[[], float] = time.time
    _client_buckets: dict[str, tuple[float, int]] = field(default_factory=dict)
    _global_bucket: tuple[float, int] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check_and_consume(self, client: str) -> RateLimitDecision:
        now = float(self.clock())
        with self._lock:
            global_start, global_count = self._active_bucket(
                self._global_bucket, self.global_window, now
            )
            client_start, client_count = self._active_bucket(
                self._client_buckets.get(client), self.client_window, now
            )
            global_retry = self._retry_after(global_start, self.global_window, now)
            client_retry = self._retry_after(client_start, self.client_window, now)
            if global_count >= self.global_max:
                return RateLimitDecision(False, global_retry, "global")
            if client_count >= self.client_max:
                return RateLimitDecision(False, client_retry, "client")
            self._global_bucket = (global_start, global_count + 1)
            self._client_buckets[client] = (client_start, client_count + 1)
            return RateLimitDecision(True)

    @staticmethod
    def _active_bucket(
        bucket: tuple[float, int] | None, window: int, now: float
    ) -> tuple[float, int]:
        if bucket is None or now - bucket[0] >= window:
            return now, 0
        return bucket

    @staticmethod
    def _retry_after(start: float, window: int, now: float) -> int:
        return max(1, int(start + window - now + 0.999))


class RedisRateLimiter:
    """Atomic fixed-window limiter shared by all API processes."""

    _SCRIPT = """
local client_count = redis.call('GET', KEYS[1])
local global_count = redis.call('GET', KEYS[2])
client_count = tonumber(client_count) or 0
global_count = tonumber(global_count) or 0
local client_ttl = redis.call('PTTL', KEYS[1])
local global_ttl = redis.call('PTTL', KEYS[2])
if client_count >= tonumber(ARGV[1]) then
  return {0, math.max(1, client_ttl), 1}
end
if global_count >= tonumber(ARGV[3]) then
  return {0, math.max(1, global_ttl), 2}
end
local client_next = redis.call('INCR', KEYS[1])
if client_next == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local global_next = redis.call('INCR', KEYS[2])
if global_next == 1 then redis.call('EXPIRE', KEYS[2], ARGV[4]) end
return {1, 0, 0}
"""

    def __init__(
        self,
        client,
        *,
        prefix: str = "clipper:submission",
        client_max: int = 10,
        client_window: int = 3600,
        global_max: int = 100,
        global_window: int = 60,
    ):
        self.client = client
        self.prefix = prefix
        self.client_max = client_max
        self.client_window = client_window
        self.global_max = global_max
        self.global_window = global_window

    def check_and_consume(self, client: str) -> RateLimitDecision:
        result = self.client.eval(
            self._SCRIPT,
            2,
            f"{self.prefix}:client:{client}",
            f"{self.prefix}:global",
            self.client_max,
            self.client_window,
            self.global_max,
            self.global_window,
        )
        allowed, retry_ms, scope = (int(value) for value in result)
        return RateLimitDecision(
            bool(allowed),
            max(1, (retry_ms + 999) // 1000) if not allowed else 0,
            {1: "client", 2: "global"}.get(scope),
        )

    @classmethod
    def from_env(cls) -> RedisRateLimiter:
        url = os.getenv("REDIS_URL")
        if not url:
            raise RuntimeError("RATE_LIMIT_BACKEND=redis requires REDIS_URL")
        try:
            import redis

            client = redis.Redis.from_url(url, decode_responses=False)
            client.ping()
        except Exception as exc:
            raise RuntimeError("Configured Redis submission rate limiting is unavailable") from exc
        return cls(client, **rate_limit_settings())


def rate_limit_settings() -> dict[str, int]:
    return {
        "client_max": _positive_int("RATE_LIMIT_CLIENT_MAX", 10),
        "client_window": _positive_int("RATE_LIMIT_CLIENT_WINDOW_SECONDS", 3600),
        "global_max": _positive_int("RATE_LIMIT_GLOBAL_MAX", 100),
        "global_window": _positive_int("RATE_LIMIT_GLOBAL_WINDOW_SECONDS", 60),
    }


def make_rate_limiter() -> RateLimiter:
    backend = os.getenv("RATE_LIMIT_BACKEND", "local").lower()
    settings = rate_limit_settings()
    if backend in {"local", "memory", "inprocess"}:
        return LocalRateLimiter(**settings)
    if backend == "redis":
        return RedisRateLimiter.from_env()
    raise RuntimeError(f"Unknown RATE_LIMIT_BACKEND: {backend}")


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value
