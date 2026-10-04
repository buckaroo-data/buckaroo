"""Resumable stat units (rows-first s4).

A stat run is a list of units a caller can run one at a time. ``plan(state)``
lists them without computing anything, ``new_accumulator(state)`` makes the
object they share, and ``run(unit, acc)`` runs one and returns its *fragment*,
a ``{orig_col: {stat: value}}`` dict holding the stats that unit produced. The
pipelines' ``process_df`` and ``process_table`` are these three called in order,
so running a whole table and running its units one by one cannot differ.

A column named in ``StatState.skip_columns`` (its stats come from ``init_sd``)
gets no unit. It still has an entry in ``acc.sd()``, with whatever structural
keys the pipeline gives a skipped column, because ``process_df`` and
``process_table`` always returned one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from buckaroo.df_util import old_col_new_col

from .col_analysis import SDType
from .stat_result import StatError

# {orig_col: {stat: value}}: the stats one unit produced, for the columns it covers.
Fragment = Dict[Any, Dict[str, Any]]


@dataclass(frozen=True)
class StatUnit:
    """One bounded piece of a stat run.

    ``id`` is unique within a plan. ``columns`` are original column names.
    ``phase`` says what kind of work it is, and ``cost`` is a plain string
    class (``column``, ``scan`` or ``query``) a scheduler can read. ``after``
    names the units whose results this one reads, which must have run first.
    """
    id: str
    columns: Tuple[Any, ...]
    phase: str
    after: Tuple[str, ...] = ()
    cost: str = "column"


@dataclass(frozen=True, eq=False)
class StatState:
    """What a stat run describes: the frame or expression, and how to cut it.

    ``skip_columns`` get no unit. ``columns`` restricts the run to a group (a
    column-group request), and ``priority`` names columns to plan first. Both
    take original or rewritten (``a, b, c``) names, since a client only knows
    the rewritten ones. ``rows`` is the row count when the caller already has
    it, which the xorq column-chunk split needs and which is never queried for.
    """
    data: Any
    skip_columns: frozenset = frozenset()
    columns: Optional[Tuple[Any, ...]] = None
    priority: Tuple[Any, ...] = ()
    rows: Optional[int] = None


def columns_in_scope(state: StatState) -> List[Tuple[Any, str]]:
    """``(orig, rewritten)`` for each column the run covers, in data order. The
    rewritten name is the column's position in the whole of ``state.data``,
    whatever group is asked for."""
    pairs = old_col_new_col(state.data)
    if state.columns is None:
        return list(pairs)
    wanted = set(state.columns)
    return [(orig, rewritten) for orig, rewritten in pairs if orig in wanted or rewritten in wanted]


def prioritized(pairs: Sequence[Tuple[Any, str]], priority: Sequence[Any]) -> List[Tuple[Any, str]]:
    """``pairs`` with the columns named in ``priority`` first, in that order,
    and the rest in their own order."""
    rank: Dict[Any, int] = {}
    for position, name in enumerate(priority):
        rank.setdefault(name, position)

    def key(pair: Tuple[Any, str]) -> int:
        ranks = [rank[name] for name in pair if name in rank]
        return min(ranks) if ranks else len(rank)

    return sorted(pairs, key=key)


class StatAccumulator:
    """What the units of one run share: the state, the stats recorded so far
    for each column (``results``, keyed by original name) and the errors the
    units reported.

    ``record`` is how a unit's fragment lands here. ``sd()`` is the result so
    far in data order. A column no unit has run for is absent from it, unless
    it is a skipped column, whose entry is there from the start.
    """

    def __init__(self, state: StatState, columns: Sequence[Any] = (), rewritten: Optional[Dict[Any, str]] = None):
        self.state = state
        self.order: List[Any] = list(columns)
        self.rewritten: Dict[Any, str] = dict(rewritten or {})
        self.results: Dict[Any, Dict[str, Any]] = {}
        self.errors: List[StatError] = []

    def record(self, fragment: Fragment, errors: Iterable[StatError] = ()) -> None:
        for col, stats in fragment.items():
            self.results.setdefault(col, {}).update(stats)
        self.errors.extend(errors)

    def sd(self) -> Dict[Any, Dict[str, Any]]:
        return {col: self.results[col] for col in self.order if col in self.results}


def merge_fragments(fragments: Iterable[Fragment]) -> Fragment:
    """The union of fragments: each column's stats from every fragment that
    has it. Neither the fragments nor their column dicts are changed."""
    merged: Fragment = {}
    for fragment in fragments:
        for col, stats in fragment.items():
            merged.setdefault(col, {}).update(stats)
    return merged


def rewrite_sd(results: Dict[Any, Dict[str, Any]], data: Any) -> SDType:
    """``results`` (keyed by original column name) as the summary dict the
    dataflow carries: keyed by the rewritten name, with ``orig_col_name`` and
    ``rewritten_col_name`` set from ``data``'s columns. Empty when ``results``
    is, as ``process_df`` is for an empty frame."""
    if not results:
        return {}
    rewritten: SDType = {}
    for orig_col, rewritten_col in old_col_new_col(data):
        col_meta = dict(results.get(orig_col, {}))
        col_meta['orig_col_name'] = orig_col
        col_meta['rewritten_col_name'] = rewritten_col
        rewritten[rewritten_col] = col_meta
    return rewritten


class UnitPipeline:
    """The loop ``StatPipeline`` and ``XorqStatPipeline`` share: plan, then run
    each unit. A subclass implements ``plan``, ``new_accumulator`` and ``run``."""

    def plan(self, state: StatState) -> List[StatUnit]:
        raise NotImplementedError

    def new_accumulator(self, state: StatState) -> StatAccumulator:
        raise NotImplementedError

    def run(self, unit: StatUnit, acc: StatAccumulator) -> Fragment:
        raise NotImplementedError

    def iter_units(self, state: StatState, acc: StatAccumulator) -> Iterator[Tuple[StatUnit, Fragment]]:
        """Plan the run and run its units in order, yielding each with its
        fragment as it finishes. Nothing runs until the generator is advanced,
        so a caller can stop between units."""
        for unit in self.plan(state):
            yield unit, self.run(unit, acc)

    def run_all(self, state: StatState) -> StatAccumulator:
        """Every unit, in order. What ``process_df`` and ``process_table`` are."""
        acc = self.new_accumulator(state)
        for _unit, _fragment in self.iter_units(state, acc):
            pass
        return acc


class UnitStats:
    """``plan``, ``new_accumulator`` and ``run`` for a stats class (``DfStatsV2``
    and its siblings) that holds a pipeline in ``ap`` and the state it analyzes
    in ``state``. The state defaults to the stats class's own."""
    ap: Any
    state: StatState

    def plan(self, state: Optional[StatState] = None) -> List[StatUnit]:
        return self.ap.plan(self.state if state is None else state)

    def new_accumulator(self, state: Optional[StatState] = None) -> StatAccumulator:
        return self.ap.new_accumulator(self.state if state is None else state)

    def run(self, unit: StatUnit, acc: StatAccumulator) -> Fragment:
        return self.ap.run(unit, acc)
