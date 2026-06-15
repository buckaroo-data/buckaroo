"""Opt-in perf instrumentation for the stats pipeline and the first data pull.

Default off — zero behavioural change and a single bool check at each call
site. Turn on with ``BUCKAROO_PERF=1`` in the environment, or
programmatically with :func:`enable` (handy in a notebook investigation)::

    from buckaroo.pluggable_analysis_framework import perf_log
    perf_log.enable()
    BuckarooWidget(df)          # spans + summary printed to the buckaroo.perf logger
    perf_log.disable()

When enabled, two things happen:

* :func:`perf_span` context managers emit one ``key=value`` line per span to
  the ``buckaroo.perf`` logger (greppable; in the server these land in
  ``~/.buckaroo/logs/server.log``).
* The stat pipelines feed a :class:`PerfRecorder` with one row per
  ``(phase, column, stat, seconds)`` and print a top-N-slowest summary at the
  end of a run.

The logger has no handler of its own — it inherits the root config (stderr in
a notebook, the server log file under the server). It stays quiet unless
``BUCKAROO_PERF`` is set, regardless of how noisy other loggers are.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import List, Tuple

log = logging.getLogger("buckaroo.perf")


def _env_enabled() -> bool:
    return os.environ.get("BUCKAROO_PERF", "").lower() in ("1", "true", "yes", "on")


# Computed once from the environment; flip at runtime with enable()/disable().
_ENABLED: bool = _env_enabled()


def enabled() -> bool:
    """True when perf instrumentation should run. Cheap; safe in hot paths."""
    return _ENABLED


def enable() -> None:
    """Turn perf instrumentation on for this process (overrides the env var)."""
    global _ENABLED
    _ENABLED = True


def disable() -> None:
    """Turn perf instrumentation off for this process."""
    global _ENABLED
    _ENABLED = False


def _fmt_fields(fields: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in fields.items())


@contextmanager
def perf_span(label: str, **fields):
    """Time a block and log one line as ``perf span=<label> secs=<n> ...``.

    No-op (a single bool check, no timing) when instrumentation is off.
    ``fields`` are appended as ``key=value`` pairs for grepping/parsing.

    If the block raises, the line still emits (the timing of the partial
    work) but is tagged ``errored=true`` so a parser keying on ``secs=``
    doesn't mistake a failed run's partial timing for a clean one.
    """
    if not _ENABLED:
        yield
        return
    t0 = time.perf_counter()
    errored = False
    try:
        yield
    except BaseException:
        errored = True
        raise
    finally:
        secs = time.perf_counter() - t0
        if errored:
            fields = {**fields, "errored": "true"}
        suffix = _fmt_fields(fields)
        log.info("perf span=%s secs=%.4f%s", label, secs,
            f" {suffix}" if suffix else "")


class PerfRecorder:
    """Accumulates ``(phase, column, stat, seconds)`` rows for one pipeline run.

    Shared schema across the pandas, polars and xorq pipelines so their output
    reads identically. ``summary()`` logs per-phase totals and the slowest
    individual stats.
    """

    def __init__(self, label: str = ""):
        self.label = label
        self.rows: List[Tuple[str, str, str, float]] = []

    def record(self, phase: str, column: str, stat: str, seconds: float) -> None:
        self.rows.append((phase, column, stat, seconds))

    def extend_timings(self, phase: str, timings) -> None:
        """Absorb ``(column, stat, seconds)`` tuples (StatPipeline.timings shape)."""
        for column, stat, seconds in timings:
            self.rows.append((phase, column, stat, seconds))

    def summary(self, top_n: int = 15) -> None:
        if not _ENABLED or not self.rows:
            return
        total = sum(r[3] for r in self.rows)
        by_phase: dict = {}
        for phase, _col, _stat, secs in self.rows:
            by_phase[phase] = by_phase.get(phase, 0.0) + secs
        label = f" {self.label}" if self.label else ""
        log.info("perf summary%s: total=%.4fs stats=%d", label, total, len(self.rows))
        for phase, secs in sorted(by_phase.items(), key=lambda kv: -kv[1]):
            log.info("perf   phase=%s secs=%.4f", phase, secs)
        slowest = sorted(self.rows, key=lambda r: -r[3])[:top_n]
        for phase, column, stat, secs in slowest:
            log.info("perf   slow phase=%s col=%s stat=%s secs=%.4f",
                phase, column, stat, secs)
