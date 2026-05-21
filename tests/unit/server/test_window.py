"""Unit tests for ``buckaroo.server.window.clamp_window``.

Pure function — fast, deterministic, doesn't need a server.
"""
import pytest

from buckaroo.server import window as W


@pytest.fixture(autouse=True)
def reset_max_window():
    """Restore MAX_INFINITE_WINDOW across tests that mutate it."""
    saved = W.MAX_INFINITE_WINDOW
    yield
    W.MAX_INFINITE_WINDOW = saved


class TestClampWindow:
    def test_normal_window_unchanged(self):
        assert W.clamp_window(0, 100, 1_000) == (0, 100)

    def test_end_clamped_to_total(self):
        """The DoS case from #797: end >> total returns the whole table.
        Must clamp to total."""
        assert W.clamp_window(0, 99_999_999, 500) == (0, 500)

    def test_window_cap_kicks_in_when_total_is_large(self):
        """For a million-row table the response must still be bounded."""
        s, e = W.clamp_window(0, 99_999_999, 1_000_000)
        assert e - s <= W.MAX_INFINITE_WINDOW

    def test_window_cap_with_offset(self):
        """Cap applies to (end - start), not just absolute end."""
        s, e = W.clamp_window(50_000, 99_999_999, 1_000_000)
        assert s == 50_000
        assert e - s <= W.MAX_INFINITE_WINDOW

    def test_negative_start_floored_to_zero(self):
        assert W.clamp_window(-100, 50, 1_000) == (0, 50)

    def test_end_less_than_start_returns_empty(self):
        """Caller asked for a backwards window; return an empty slice
        instead of crashing."""
        s, e = W.clamp_window(100, 50, 1_000)
        assert s == e  # empty

    def test_zero_window(self):
        assert W.clamp_window(0, 0, 1_000) == (0, 0)

    def test_total_zero_returns_empty(self):
        s, e = W.clamp_window(0, 100, 0)
        assert s == 0
        assert e == 0

    def test_string_inputs_coerced(self):
        """AG-Grid sometimes ships ``start`` / ``end`` as JSON strings."""
        assert W.clamp_window("0", "10", 100) == (0, 10)

    def test_none_inputs_safe_fallback(self):
        s, e = W.clamp_window(None, None, 1_000)
        assert s == 0
        assert e == 0

    def test_garbage_inputs_safe_fallback(self):
        s, e = W.clamp_window("not_a_number", "abc", 100)
        assert s == 0
        assert e == 0

    def test_monkeypatched_max_window(self):
        """MAX_INFINITE_WINDOW is module-level so tests can lower it."""
        W.MAX_INFINITE_WINDOW = 3
        s, e = W.clamp_window(0, 100, 1_000)
        assert e - s == 3
