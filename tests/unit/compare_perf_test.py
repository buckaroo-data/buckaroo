"""Deterministic scaling-regression guards for buckaroo.compare.

These replace the old wall-clock timing tests. Instead of measuring elapsed
time and asserting on a ratio (machine-dependent, flaky on a loaded CI runner),
each test asserts on *work done* and *results* — counts that are identical on a
fast laptop and a slow runner:

  - head_diff*  on the parquet (polars / xorq) backends is lazy: it never
                materialises more than the N-row preview, regardless of file
                size. Guarded by spying on the materialisation boundary
                (``LazyFrame.collect`` / ``Expr.execute``) and asserting no
                call pulls more than N rows — plus, for polars, that no eager
                full read (``pl.read_parquet``) happens at all.
  - stats_diff* batches every column into a fixed number of backend passes
                rather than one scan per column. Guarded by counting the
                backend op (pandas ``DataFrame.agg`` / polars ``DataFrame.select``
                / xorq ``Expr.execute``) on a narrow vs a wide frame and
                asserting the count does not grow with the column count.
  - key_diff*   detects the real unique key (not a low-cardinality column), so
                every row matches exactly once (``matched == n``). The matched
                count is the deterministic guard against the cartesian blowup
                the old low-cardinality key heuristic produced.

The module is small and fast (no million-row fixtures) — the regressions show
up at a few thousand rows just as clearly as at a million, because the spies
measure rows materialised, not rows on disk.
"""
import numpy as np
import pandas as pd
import pytest

from buckaroo.compare import (
    head_diff, head_diff_polars, head_diff_xorq,
    key_diff, key_diff_polars, key_diff_xorq,
    stats_diff, stats_diff_polars, stats_diff_xorq)

# polars is a hard test dependency in this repo; xorq is gated to python < 3.14.
# Gate per-backend (not at module level) so the pandas tests still run when an
# optional backend is absent.
try:
    import polars as pl
    HAS_POLARS = True
except ImportError:
    HAS_POLARS = False

try:
    import xorq.api  # noqa: F401
    HAS_XORQ = True
except ImportError:
    HAS_XORQ = False

needs_polars = pytest.mark.skipif(not HAS_POLARS, reason="requires buckaroo[polars]")
needs_xorq = pytest.mark.skipif(not HAS_XORQ, reason="requires buckaroo[xorq] (python < 3.14)")


# --- sizes ------------------------------------------------------------------
N_PREVIEW = 10        # head_diff preview rows
LAZY_ROWS = 2_000     # rows in the parquet used for the laziness spies (>> preview)
KEY_N = 2_000         # rows for the no-blowup key tests (a cartesian blowup -> ~n^2/10)
BATCH_ROWS = 500      # rows for the batching tests (column count is what varies)
NCOLS_NARROW = 4
NCOLS_WIDE = 40


def _gen(n, seed=0):
    """Mixed-dtype frame: a unique int key, a low-cardinality column, nulls, a bool.

    'id' is ``arange(n)`` — identical for every seed, so two frames built with
    different seeds share the same key set (every row matches) while their other
    columns differ. 'cat' has 10 distinct values: exactly the low-cardinality
    column the old key heuristic wrongly treated as a join key.
    """
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "id": np.arange(n, dtype="int64"),
        "cat": rng.integers(0, 10, n).astype(str),
        "val1": rng.standard_normal(n),
        "val2": rng.standard_normal(n),
        "flag": rng.integers(0, 2, n).astype(bool)})
    df.loc[df.index % 50 == 0, "val1"] = np.nan  # ~2% nulls
    return df


def _gen_wide(ncols, nrows, seed=0):
    """All-numeric frame of ``ncols`` columns — exercises the numeric-agg batch."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({f"c{i}": rng.standard_normal(nrows) for i in range(ncols)})


def _count_calls(cls, method, fn):
    """Run ``fn`` and return how many times ``cls.method`` was invoked.

    Deterministic stand-in for "how much work scales with the input": a backend
    op called once per side is constant in column count; one called per column
    is not.
    """
    orig = getattr(cls, method)
    n = 0

    def wrapped(self, *args, **kwargs):
        nonlocal n
        n += 1
        return orig(self, *args, **kwargs)

    setattr(cls, method, wrapped)
    try:
        fn()
    finally:
        setattr(cls, method, orig)
    return n


def _materialised_rows(cls, method, fn):
    """Run ``fn`` and return the row count of every result ``cls.method`` produced.

    A scalar result (e.g. a ``count()``) counts as 1 row. The max over all calls
    is the largest frame the operation ever pulled into memory.
    """
    orig = getattr(cls, method)
    sizes = []

    def wrapped(self, *args, **kwargs):
        out = orig(self, *args, **kwargs)
        sizes.append(len(out) if hasattr(out, "__len__") else 1)
        return out

    setattr(cls, method, wrapped)
    try:
        fn()
    finally:
        setattr(cls, method, orig)
    return sizes


def _xorq_expr_base():
    """The vendored-ibis ``Expr`` base class (the owner of ``.execute``).

    Found via the MRO of a real expression so the test does not hard-code the
    vendored module path, which has moved between xorq versions.
    """
    import xorq.api as xo

    expr = xo.literal(1)
    return next(c for c in type(expr).__mro__ if c.__name__ == "Expr")


@pytest.fixture(scope="module")
def lazy_parquet(tmp_path_factory):
    """A single parquet file of LAZY_ROWS rows, used by the laziness spies."""
    p = tmp_path_factory.mktemp("compare_lazy") / "t.parquet"
    _gen(LAZY_ROWS).to_parquet(p)
    return p


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    """A narrow and a wide frame (same row count) + their parquet files."""
    d = tmp_path_factory.mktemp("compare_batch")
    narrow = _gen_wide(NCOLS_NARROW, BATCH_ROWS)
    wide = _gen_wide(NCOLS_WIDE, BATCH_ROWS)
    narrow_p = d / "narrow.parquet"
    wide_p = d / "wide.parquet"
    narrow.to_parquet(narrow_p)
    wide.to_parquet(wide_p)
    return {"narrow_df": narrow, "wide_df": wide, "narrow_p": narrow_p, "wide_p": wide_p}


# ===========================================================================
# head_diff: lazy on the parquet backends — never materialise more than N rows.
# ===========================================================================


@needs_polars
def test_head_diff_polars_reads_only_preview(lazy_parquet, monkeypatch):
    eager = {"n": 0}
    orig_read = pl.read_parquet

    def spy_read(*args, **kwargs):
        eager["n"] += 1
        return orig_read(*args, **kwargs)

    monkeypatch.setattr(pl, "read_parquet", spy_read)
    sizes = _materialised_rows(
        pl.LazyFrame, "collect",
        lambda: _assert_head_total(head_diff_polars(lazy_parquet, lazy_parquet, n=N_PREVIEW)))

    assert sizes, "expected at least one LazyFrame.collect()"
    assert max(sizes) <= N_PREVIEW, (
        f"head_diff_polars materialised {max(sizes)} rows (> {N_PREVIEW}); a lazy scan should "
        "read only the N-row preview plus a scalar count, not the whole frame.")
    assert eager["n"] == 0, (
        f"head_diff_polars called pl.read_parquet {eager['n']}x — that eagerly reads the whole "
        "file; the preview must come from a lazy scan_parquet().head(n).")


@needs_xorq
def test_head_diff_xorq_reads_only_preview(lazy_parquet):
    expr_base = _xorq_expr_base()
    sizes = _materialised_rows(
        expr_base, "execute",
        lambda: _assert_head_total(head_diff_xorq(lazy_parquet, lazy_parquet, n=N_PREVIEW)))

    assert sizes, "expected at least one Expr.execute()"
    assert max(sizes) <= N_PREVIEW, (
        f"head_diff_xorq materialised {max(sizes)} rows (> {N_PREVIEW}); limit(n) + count() "
        "should never pull the whole file into memory.")


def _assert_head_total(res):
    """The preview is only meaningful if the totals are right (the count ran)."""
    assert res["a_total"] == LAZY_ROWS and res["b_total"] == LAZY_ROWS
    assert res["n"] == N_PREVIEW
    return res


def test_head_diff_pandas_totals():
    # pandas head_diff is in-memory (the frame is already materialised), so there
    # is no laziness to prove — just that it reports the right totals + preview.
    df = _gen(500)
    res = head_diff(df, df, n=N_PREVIEW)
    assert res["a_total"] == 500 and res["b_total"] == 500 and res["n"] == N_PREVIEW
    assert "<table" in res["before"] and "<table" in res["after"]


# ===========================================================================
# stats_diff: batched over all columns — work is constant in the column count,
# not one scan per column.
# ===========================================================================


@pytest.mark.parametrize("backend", ["pandas", "polars", "xorq"])
def test_stats_diff_work_constant_in_column_count(backend, batch):
    if backend == "pandas":
        cls, method, run = pd.DataFrame, "agg", stats_diff
        narrow, wide = batch["narrow_df"], batch["wide_df"]
    elif backend == "polars":
        pytest.importorskip("polars")
        cls, method, run = pl.DataFrame, "select", stats_diff_polars
        narrow, wide = pl.from_pandas(batch["narrow_df"]), pl.from_pandas(batch["wide_df"])
    else:
        pytest.importorskip("xorq")
        cls, method, run = _xorq_expr_base(), "execute", stats_diff_xorq
        narrow, wide = batch["narrow_p"], batch["wide_p"]

    n_narrow = _count_calls(cls, method, lambda: run(narrow, narrow))
    n_wide = _count_calls(cls, method, lambda: run(wide, wide))

    assert n_narrow > 0, f"{backend}: expected stats_diff to call {method}() at least once"
    assert n_narrow == n_wide, (
        f"{backend} stats_diff issued {n_narrow} {method}() call(s) on {NCOLS_NARROW} columns "
        f"but {n_wide} on {NCOLS_WIDE} — the work scales with column count; expected a fixed "
        "number of batched passes regardless of width.")


# ===========================================================================
# key_diff: detect the unique key (not a low-cardinality column) so every row
# matches exactly once. matched == n is the cartesian-blowup guard.
# ===========================================================================


@pytest.mark.parametrize("backend", ["pandas", "polars", "xorq"])
def test_key_diff_detects_unique_key_no_blowup(backend, tmp_path):
    a, b = _gen(KEY_N, 0), _gen(KEY_N, 1)  # identical unique 'id', other columns differ
    if backend == "pandas":
        res = key_diff(a, b)
    elif backend == "polars":
        pytest.importorskip("polars")
        res = key_diff_polars(pl.from_pandas(a), pl.from_pandas(b))
    else:
        pytest.importorskip("xorq")
        ap, bp = tmp_path / "a.parquet", tmp_path / "b.parquet"
        a.to_parquet(ap)
        b.to_parquet(bp)
        res = key_diff_xorq(ap, bp)

    assert res is not None, f"{backend}: expected a diff joined on the unique 'id'"
    assert res["keys"] == ["id"], (
        f"{backend}: detected keys {res['keys']}, expected the unique 'id'; a low-cardinality "
        "key (e.g. 'cat', 10 distinct) would explode the outer join into a many-to-many product.")
    # 1:1 alignment — one matched row per input row, no n^2 cartesian explosion.
    assert res["matched"] == KEY_N, (
        f"{backend}: matched={res['matched']} (expected {KEY_N}) — a cartesian blowup on a "
        "low-cardinality key would produce far more.")
    assert res["only_before"] == 0 and res["only_after"] == 0
