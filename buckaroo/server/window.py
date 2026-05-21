"""Window clamping for ``infinite_request`` payloads.

The WS protocol carries ``{start, end}`` row indices from AG-Grid's
infinite-loading model. Without clamping, a malicious or buggy client
can request ``{start: 0, end: 99_999_999}`` and the server happily
materialises the entire underlying table into one parquet binary
frame — on a million-row table that's tens of megabytes per call.
See #797.

``clamp_window`` keeps the request bounded to a single page-sized
window (default 10 000 rows, matching AG-Grid's max practical page
size) regardless of caller intent.

The constant is module-level so tests can monkeypatch a lower bound
without having to fabricate a million-row fixture.
"""

# Hard ceiling on rows returned in a single infinite_request. Tuned to
# AG-Grid's default infinite-scroll buffer (a few thousand rows) with
# generous headroom; well below the practical WS write-buffer limit.
MAX_INFINITE_WINDOW: int = 10_000


def clamp_window(start, end, total_rows: int) -> tuple[int, int]:
    """Clamp an ``{start, end}`` window to a valid, bounded slice.

    Returns a ``(start, end)`` pair such that:
      - ``0 <= start <= end``
      - ``end <= total_rows`` (never asks for past-end rows)
      - ``end - start <= MAX_INFINITE_WINDOW`` (caps page size)
      - non-integer / None inputs are coerced where possible, else
        treated as 0 (the safest fallback)

    Designed for the WS infinite_request payload, but is a pure
    function with no buckaroo-side dependencies — drop in anywhere a
    row-window needs sanitising.
    """
    try:
        start = max(0, int(start))
    except (TypeError, ValueError):
        start = 0
    try:
        end = int(end)
    except (TypeError, ValueError):
        end = start
    try:
        total = int(total_rows)
    except (TypeError, ValueError):
        total = 0

    end = min(end, total)
    if end < start:
        end = start
    if end - start > MAX_INFINITE_WINDOW:
        end = start + MAX_INFINITE_WINDOW
    return start, end
