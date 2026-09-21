import pytest

from app.rate_limit import LocalRateLimiter, RateLimitDecision, make_rate_limiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_client_limit_retry_after_and_window_reset():
    clock = Clock()
    limiter = LocalRateLimiter(
        client_max=2, client_window=10, global_max=100, global_window=60, clock=clock
    )

    assert limiter.check_and_consume("one").allowed
    assert limiter.check_and_consume("one").allowed
    limited = limiter.check_and_consume("one")
    assert limited == RateLimitDecision(False, 10, "client")

    assert limiter.check_and_consume("two").allowed
    clock.now += 10
    assert limiter.check_and_consume("one").allowed


def test_global_limit_is_shared_but_client_buckets_are_isolated():
    limiter = LocalRateLimiter(client_max=10, client_window=60, global_max=2, global_window=60)

    assert limiter.check_and_consume("one").allowed
    assert limiter.check_and_consume("two").allowed
    limited = limiter.check_and_consume("three")
    assert limited.allowed is False
    assert limited.scope == "global"
    assert limited.retry_after >= 1


def test_redis_mode_requires_url_and_fails_explicitly(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(RuntimeError, match="requires REDIS_URL"):
        make_rate_limiter()
