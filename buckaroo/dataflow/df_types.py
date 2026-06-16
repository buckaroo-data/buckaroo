"""Backend-agnostic dataframe typing for the dataflow pipeline.

The dataflow classes move a single "dataframe" object through a fixed
pipeline (``raw_df`` -> ``sampled_df`` -> ``cleaned`` -> ``processed``)
and then derive summary statistics from it. Three concrete backends
supply that object, and they share *no* common base class:

- pandas -> ``pandas.DataFrame``
- polars -> ``polars.DataFrame``
- xorq   -> a xorq/ibis expression (``xorq.vendor.ibis`` ``Table``)

There are actually two tiers of carrier, so there are two type variables:

``FrameT`` (unbounded) — the umbrella for *every* dataflow, including the
lazy one. ``ColumnExecutorDataflow`` carries a ``pl.LazyFrame`` that is
never materialised: it has no row count and is not row-sliceable, so it
cannot meet the eager contract below. It binds ``FrameT = pl.LazyFrame``
directly on the abstract base and supplies its own pipeline.

``DataFrameT`` (bound to ``DataFrameLike``) — the *eager*, materialised
frames used by the shared ``DataFlow`` / ``CustomizableDataflow`` body,
which reads ``df.columns``, calls ``len(df)``, and row-slices ``df[:n]``.
pandas, polars (eager), and xorq ``Table`` all satisfy this structurally.
Each eager backend binds it to its concrete frame type::

    CustomizableDataflow[pd.DataFrame]               # pandas
    CustomizableDataflow[pl.DataFrame]               # polars (eager)
    XorqDataflow  ==  CustomizableDataflow[XorqExpr]  # xorq

There is no nominal base class spanning these three, so the bound is a
structural ``Protocol``, not a shared superclass. ``DataFrameT`` is a
valid argument to ``FrameT`` (a bounded type var satisfies an unbounded
one), so ``DataFlow(ABCDataflow[DataFrameT])`` type-checks while the lazy
``ColumnExecutorDataflow(ABCDataflow[pl.LazyFrame])`` also does.

The type variable flows through the method boundaries that actually take
or return the frame — ``_compute_sampled_df``, ``_compute_processed_result``,
``_get_summary_sd``, and the ``processed_df`` / ``cleaned_df`` properties
— so a ``CustomizableDataflow[pd.DataFrame]`` reports ``processed_df`` as
``pd.DataFrame | None`` rather than ``Any``.

The traitlets-backed attributes (``raw_df``, ``sampled_df``, ``cleaned``,
``processed_result``, the lazy ``raw_ldf``) stay deliberately untyped: a
traitlets descriptor returns ``Any`` on instance access, and annotating
the class-level trait assignment fights the descriptor protocol. The
generic contract is expressed where it is sound — the method boundaries —
not on the traits.
"""
from __future__ import annotations

from typing import Any, Protocol, TypeVar


class DataFrameLike(Protocol):
    """The structural surface the *shared* dataflow body uses on a frame.

    The pandas/polars-shared code in ``CustomizableDataflow`` reads
    ``df.columns``, calls ``len(df)``, and row-slices ``df[:n]``. All three
    backends expose these members, so each backend's concrete type
    structurally satisfies this Protocol and can bind ``DataFrameT``.

    Caveat for xorq: an ibis/xorq expression *defines* ``__len__`` but
    raises at runtime (it is not materialised, so it has no row count).
    That is fine for the static bound — and ``XorqDataflow`` overrides the
    methods that would actually call ``len`` (``populate_df_meta`` issues
    ``expr.count().execute()`` instead). The Protocol describes the
    interface the shared code *names*; backends whose semantics differ
    override those methods rather than weakening the bound.
    """

    @property
    def columns(self) -> Any: ...
    def __len__(self) -> int: ...
    def __getitem__(self, key: Any) -> Any: ...


#: Unbounded umbrella carrier for the abstract base ``ABCDataflow`` — spans
#: every dataflow, including the lazy ``ColumnExecutorDataflow`` whose
#: ``pl.LazyFrame`` cannot meet the eager ``DataFrameLike`` contract (it is
#: never materialised). Eager subclasses pass the tighter ``DataFrameT`` in
#: its place; the lazy one binds ``pl.LazyFrame`` directly.
FrameT = TypeVar("FrameT")

#: The *eager* dataframe type carried through the shared ``DataFlow`` /
#: ``CustomizableDataflow`` body. Bound to ``DataFrameLike`` — the minimal
#: structural interface that body uses (``columns`` / ``len`` / row-slice)
#: — which pandas frames, polars (eager) frames, and xorq ``Table``
#: expressions all satisfy. There is no nominal base class spanning the
#: three (see module docstring), so the bound is structural.
DataFrameT = TypeVar("DataFrameT", bound=DataFrameLike)

__all__ = ["FrameT", "DataFrameT", "DataFrameLike"]
