"""The stat run a session keeps for one stats generation (rows-first s4).

A ``StatRun`` holds the planned units of one ``(stats_gen, scope)``, the
fragments they produced in the order they finished, and the accumulator the
units read. It runs a unit only when its caller asks: it has no thread, timer or
callback, so there is nothing to cancel, and the session drops it when the
generation changes (``begin_stats_generation``).

The fragment list is append-only and shared. A ``StatCursor`` is one client's
position in it, held by that client's WebSocket handler, so work is done once
and every client reads all of it at its own pace.

Only the full run over every column is the session's stats: its results are the
final assignment. A run at another tier (``scalar``) or over a column group
behaves like a filtered run: its fragments go to the clients that ask and
nothing is assigned. ``stat_run_key`` keeps the full run's key as it was and
gives every other run a key of its own, so the two never meet.
"""
import itertools
import time
from typing import Any, List, Optional, Sequence, Tuple

from buckaroo.df_util import old_col_new_col
from buckaroo.pluggable_analysis_framework.stat_pipeline import errors_to_errdict
from buckaroo.pluggable_analysis_framework.stat_units import Fragment, StatState, StatUnit, resolve_names, rewrite_sd

_run_ids = itertools.count(1)


def stat_run_key(stats_gen: int, scope: str, tier: str = "full", columns: Optional[Sequence[Any]] = None) -> tuple:
    """The key a session keeps a run under. The full run over every column is
    ``(stats_gen, scope)``, as it has always been. A run at another tier or over
    a column group is ``(stats_gen, scope, tier, columns)`` (``columns`` a tuple,
    or ``None`` for every column), so it never takes the full run's place."""
    group = None if columns is None else tuple(columns)
    if tier == "full" and group is None:
        return (stats_gen, scope)
    return (stats_gen, scope, tier, group)


class StatRun:
    """``stats`` is a stats class (``DfStatsV2`` and its siblings) built with
    ``run=False``: the run plans it once and runs its units through it. ``state``
    is what the run describes, the stats class's own unless a tier or a column
    group says otherwise (see ``StatState``).

    ``status`` is ``pending`` until the last unit has run, then ``complete``;
    ``error`` once a unit raised, and the run is not retried. A stat that fails
    inside a unit is not that: it is an entry in ``acc.errors`` and the unit
    still finishes. ``elapsed_s`` is the time the units have taken, summed over
    every request that ran one.
    """

    def __init__(self, stats_gen: int, scope: str, stats: Any, state: Optional[StatState] = None):
        self.id = next(_run_ids)
        self.stats_gen = stats_gen
        self.scope = scope
        self.stats = stats
        self.state: StatState = stats.state if state is None else state
        self.units: List[StatUnit] = stats.plan(self.state)
        self.acc = stats.new_accumulator(self.state)
        self.fragments: List[Fragment] = []
        self.ran: List[str] = []
        self.status = "pending" if self.units else "complete"
        self.error: Optional[Exception] = None
        self.created_at = time.time()
        self.elapsed_s = 0.0
        self._frame_columns: Optional[List[Tuple[Any, str]]] = None

    @property
    def tier(self) -> str:
        return self.state.tier

    @property
    def assigns(self) -> bool:
        """Whether the run's results are the session's stats: the full tier over
        every column. Any other run is a fragment source for clients and is
        never assigned or cached as complete."""
        return self.state.tier == "full" and self.state.columns is None

    @property
    def key(self) -> tuple:
        return stat_run_key(self.stats_gen, self.scope, self.state.tier, self.state.columns)

    @property
    def remaining(self) -> int:
        """The number of units not yet run."""
        return len(self.units) - len(self.ran)

    def next_unit(self, prefer: Sequence[Any] = (), namespace: str = "any") -> Optional[StatUnit]:
        """The unit ``run_next`` would run: the first whose prerequisites have
        run, or the first of those that covers a column named in ``prefer``, so
        the columns a client is looking at come first. The names are written in
        ``namespace`` (see ``resolve_names``): a client that holds the rewritten
        ``a, b, c`` names says ``rewritten``. ``None`` when no unit is left."""
        ran = set(self.ran)
        ready = [unit for unit in self.units if unit.id not in ran and all(a in ran for a in unit.after)]
        if prefer:
            if self._frame_columns is None:
                self._frame_columns = old_col_new_col(self.acc.state.data)
            wanted = set(resolve_names(self._frame_columns, prefer, namespace))
            for unit in ready:
                if any(col in wanted for col in unit.columns):
                    return unit
        return ready[0] if ready else None

    def run_next(self, prefer: Sequence[Any] = (), namespace: str = "any") -> Optional[Fragment]:
        """Run one unit and return its fragment, which is also appended to
        ``fragments``. ``None`` when the run is complete or failed. A unit that
        raises fails the run, and the exception propagates once. ``prefer`` and
        ``namespace`` are as in ``next_unit``."""
        if self.status != "pending":
            return None
        unit = self.next_unit(prefer, namespace)
        if unit is None:
            self.status = "complete"
            return None
        started = time.perf_counter()
        try:
            fragment = self.stats.run(unit, self.acc)
        except Exception as exc:
            self.status, self.error = "error", exc
            raise
        finally:
            self.elapsed_s += time.perf_counter() - started
        self.ran.append(unit.id)
        self.fragments.append(fragment)
        if self.remaining == 0:
            self.status = "complete"
        return fragment

    def raw_sd(self) -> dict:
        """The run's stats as the summary dict the dataflow carries, keyed by
        rewritten column name: what ``summary_sd`` holds after a whole run."""
        return rewrite_sd(self.acc.sd(), self.acc.state.data)

    def errs(self) -> dict:
        """The stats that failed inside a unit, as the ``{(col, stat): (error,
        None)}`` dict the dataflow's ``errs`` holds."""
        return errors_to_errdict(self.acc.errors)


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
