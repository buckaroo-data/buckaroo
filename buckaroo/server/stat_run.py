"""The stat run a session keeps for one stats generation (rows-first s4).

A ``StatRun`` holds the planned units of one ``(stats_gen, scope)``, the
fragments they produced in the order they finished, and the accumulator the
units read. It runs a unit only when its caller asks: it has no thread, timer or
callback, so there is nothing to cancel, and the session drops it when the
generation changes (``begin_stats_generation``).

The fragment list is append-only and shared. A ``StatCursor`` is one client's
position in it, held by that client's WebSocket handler, so work is done once
and every client reads all of it at its own pace.
"""
import itertools
import time
from typing import Any, List, Optional, Sequence, Tuple

from buckaroo.pluggable_analysis_framework.stat_units import Fragment, StatUnit, rewrite_sd

_run_ids = itertools.count(1)


class StatRun:
    """``stats`` is a stats class (``DfStatsV2`` and its siblings) built with
    ``run=False``: the run plans it once and runs its units through it.

    ``status`` is ``pending`` until the last unit has run, then ``complete``;
    ``error`` once a unit raised, and the run is not retried. A stat that fails
    inside a unit is not that: it is an entry in ``acc.errors`` and the unit
    still finishes.
    """

    def __init__(self, stats_gen: int, scope: str, stats: Any):
        self.id = next(_run_ids)
        self.stats_gen = stats_gen
        self.scope = scope
        self.stats = stats
        self.units: List[StatUnit] = stats.plan(stats.state)
        self.acc = stats.new_accumulator(stats.state)
        self.fragments: List[Fragment] = []
        self.ran: List[str] = []
        self.status = "pending" if self.units else "complete"
        self.error: Optional[Exception] = None
        self.created_at = time.time()

    @property
    def key(self) -> Tuple[int, str]:
        return (self.stats_gen, self.scope)

    @property
    def remaining(self) -> int:
        """The number of units not yet run."""
        return len(self.units) - len(self.ran)

    def next_unit(self, prefer: Sequence[Any] = ()) -> Optional[StatUnit]:
        """The unit ``run_next`` would run: the first whose prerequisites have
        run, or the first of those that covers a column named in ``prefer``
        (by original or rewritten name), so the columns a client is looking at
        come first. ``None`` when no unit is left."""
        ran = set(self.ran)
        ready = [unit for unit in self.units if unit.id not in ran and all(a in ran for a in unit.after)]
        if prefer:
            wanted = set(prefer)
            for unit in ready:
                if any(col in wanted or self.acc.rewritten.get(col) in wanted for col in unit.columns):
                    return unit
        return ready[0] if ready else None

    def run_next(self, prefer: Sequence[Any] = ()) -> Optional[Fragment]:
        """Run one unit and return its fragment, which is also appended to
        ``fragments``. ``None`` when the run is complete or failed. A unit that
        raises fails the run, and the exception propagates once."""
        if self.status != "pending":
            return None
        unit = self.next_unit(prefer)
        if unit is None:
            self.status = "complete"
            return None
        try:
            fragment = self.stats.run(unit, self.acc)
        except Exception as exc:
            self.status, self.error = "error", exc
            raise
        self.ran.append(unit.id)
        self.fragments.append(fragment)
        if self.remaining == 0:
            self.status = "complete"
        return fragment

    def raw_sd(self) -> dict:
        """The run's stats as the summary dict the dataflow carries, keyed by
        rewritten column name: what ``summary_sd`` holds after a whole run."""
        return rewrite_sd(self.acc.sd(), self.acc.state.data)


class StatCursor:
    """One client's position in a ``StatRun``'s fragment list. It follows one
    run at a time and starts again at the beginning of any other, since a
    position in one run means nothing in another."""

    def __init__(self) -> None:
        self.run_id: Optional[int] = None
        self.position = 0

    def _follow(self, run: StatRun) -> None:
        if self.run_id != run.id:
            self.run_id, self.position = run.id, 0

    def take(self, run: StatRun) -> List[Fragment]:
        """The fragments of ``run`` this cursor has not returned yet, and move
        past them."""
        self._follow(run)
        unseen = run.fragments[self.position:]
        self.position += len(unseen)
        return unseen

    def caught_up(self, run: StatRun) -> bool:
        """Whether the cursor has returned every fragment ``run`` has now."""
        return (self.position if self.run_id == run.id else 0) >= len(run.fragments)
