"""Tests for the rate limiter module."""

import threading
import time

from auto_goldfish.decklist import rate_limiter


class TestRateLimiter:
    def setup_method(self):
        rate_limiter.reset()

    def teardown_method(self):
        rate_limiter.reset()

    def test_first_call_does_not_block(self):
        start = time.monotonic()
        rate_limiter.wait("test_service", interval=1.0)
        elapsed = time.monotonic() - start
        # First call should be near-instant
        assert elapsed < 0.1

    def test_second_call_waits_interval(self):
        rate_limiter.wait("test_service", interval=0.2)
        start = time.monotonic()
        rate_limiter.wait("test_service", interval=0.2)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Allow small tolerance

    def test_different_services_independent(self):
        rate_limiter.wait("service_a", interval=0.5)
        start = time.monotonic()
        rate_limiter.wait("service_b", interval=0.5)
        elapsed = time.monotonic() - start
        # Different service should not wait
        assert elapsed < 0.1

    def test_default_intervals_used(self):
        # Scryfall default is 0.1s
        rate_limiter.wait("scryfall")
        start = time.monotonic()
        rate_limiter.wait("scryfall")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08

    def test_unknown_service_defaults_to_1s(self):
        rate_limiter.wait("unknown_api")
        start = time.monotonic()
        rate_limiter.wait("unknown_api")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9

    def test_reset_clears_state(self):
        rate_limiter.wait("test_service", interval=5.0)
        rate_limiter.reset("test_service")
        # After reset, should not wait
        start = time.monotonic()
        rate_limiter.wait("test_service", interval=5.0)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_reset_all(self):
        rate_limiter.wait("svc_a", interval=5.0)
        rate_limiter.wait("svc_b", interval=5.0)
        rate_limiter.reset()
        start = time.monotonic()
        rate_limiter.wait("svc_a", interval=5.0)
        rate_limiter.wait("svc_b", interval=5.0)
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_thread_safety(self):
        """Concurrent calls should still respect the interval."""
        call_times = []
        interval = 0.15

        def worker():
            rate_limiter.wait("threaded", interval=interval)
            call_times.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        call_times.sort()
        # Each consecutive call should be at least ~interval apart
        for i in range(1, len(call_times)):
            gap = call_times[i] - call_times[i - 1]
            assert gap >= interval * 0.8, f"Gap {gap:.3f}s too small between calls {i-1} and {i}"
