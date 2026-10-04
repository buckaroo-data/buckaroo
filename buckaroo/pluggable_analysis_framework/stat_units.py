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


# The tiers a stat run is planned at: ``full`` is every stat, and ``scalar`` the
# scalar class of them (the xorq pipeline says which, ``SCALAR_OMITTED_KEYS``).
# The ``schema`` tier is the dataflow's own and runs no units.
UNIT_TIERS = ("scalar", "full")

# How a caller writes the column names it hands in (``StatState.columns`` and
# ``priority``, and ``StatRun``'s ``prefer``): ``original`` names only,
# ``rewritten`` (``a, b, c``) names only, or ``any``.
NAMESPACES = ("any", "original", "rewritten")


def check_namespace(namespace: str) -> None:
    if namespace not in NAMESPACES:
        raise ValueError(f"namespace must be one of {NAMESPACES}, not {namespace!r}")


def resolve_names(pairs: Sequence[Tuple[Any, str]], names: Iterable[Any], namespace: str = "any") -> List[Any]:
    """The original names of the columns that ``names`` pick out of ``pairs``,
    the ``(orig, rewritten)`` of every column of the frame, in the order given.
    A name that matches no column is ignored.

    Each name is read once, so it picks one column. In ``any``, a name that is
    an original column name picks that column, and only a name that is not one
    is read as a rewritten name. That makes ``any`` right for a caller that
    writes original names. A caller that holds the rewritten names, as a client
    does, must say ``rewritten``: when one of its names is also another column's
    original name (a frame with columns ``c, b, a`` has a column named ``c``
    and a column rewritten to ``c``), ``any`` would read it as the original.
    """
    check_namespace(namespace)
    originals = {orig for orig, _rewritten in pairs}
    by_rewritten = {rewritten: orig for orig, rewritten in pairs}
    picked: List[Any] = []
    for name in names:
        if namespace != "rewritten" and name in originals:
            picked.append(name)
        elif namespace != "original" and name in by_rewritten:
            picked.append(by_rewritten[name])
    return picked


@dataclass(frozen=True, eq=False)
class StatState:
    """What a stat run describes: the frame or expression, and how to cut it.

    ``skip_columns`` get no unit. ``columns`` restricts the run to a group (a
    column-group request), and ``priority`` names columns to plan first. Both
    are written in ``namespace`` (see ``resolve_names``): a client that only
    knows the rewritten ``a, b, c`` names says ``rewritten``. ``rows`` is the
    row count when the caller already has it, which the xorq column-chunk split
    needs and which is never queried for. ``tier`` is the tier the run is at
    (see ``UNIT_TIERS``); a pipeline that has only the full tier refuses another.
    """
    data: Any
    skip_columns: frozenset = frozenset()
    columns: Optional[Tuple[Any, ...]] = None
    priority: Tuple[Any, ...] = ()
    rows: Optional[int] = None
    namespace: str = "any"
    tier: str = "full"

    def __post_init__(self) -> None:
        check_namespace(self.namespace)
        if self.tier not in UNIT_TIERS:
            raise ValueError(f"tier must be one of {UNIT_TIERS}, not {self.tier!r}")


def columns_in_scope(state: StatState) -> List[Tuple[Any, str]]:
    """``(orig, rewritten)`` for each column the run covers, in data order. The
    rewritten name is the column's position in the whole of ``state.data``,
    whatever group is asked for."""
    pairs = old_col_new_col(state.data)
    if state.columns is None:
        return list(pairs)
    wanted = set(resolve_names(pairs, state.columns, state.namespace))
    return [pair for pair in pairs if pair[0] in wanted]


def prioritized(state: StatState, pairs: Sequence[Tuple[Any, str]]) -> List[Tuple[Any, str]]:
    """``pairs`` with the columns named in ``state.priority`` first, in that
    order, and the rest in their own order. The names are read against every
    column of ``state.data``, not only ``pairs``, so a name picks the same
    column whatever group is asked for."""
    if not state.priority:
        return list(pairs)
    rank: Dict[Any, int] = {}
    for position, orig in enumerate(resolve_names(old_col_new_col(state.data), state.priority, state.namespace)):
        rank.setdefault(orig, position)
    return sorted(pairs, key=lambda pair: rank.get(pair[0], len(rank)))


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
