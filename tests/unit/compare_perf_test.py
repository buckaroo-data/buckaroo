"""Performance / big-O regression tests for buckaroo.compare.

These guard the scaling claims the three diff backends make, not absolute
speed. Each test measures an operation at two row counts and asserts on the
*ratio* between them, which is largely machine-independent (both sizes scale
by the same hardware factor), so the thresholds hold on a fast laptop and a
slow CI runner alike. The whole module is sized to run in well under 10s.

What the ratios encode:
  - stats_diff*  is O(rows): a 10x row increase should cost ~10x, not ~100x.
  - head_diff*   is lazy on the polars/xorq (parquet) backends: a 100x row
                 increase should barely move the clock, because only the
                 N-row preview (+ a metadata count) is read.
  - key_diff* (all backends) detect a real unique key, so each stays ~linear
                 and matches every row exactly once (matched == n). The
                 deterministic matched count guards against the cartesian
                 blowup the old low-cardinality key heuristic produced.

Run `pytest -s tests/unit/compare_perf_test.py` to see the timing table.
"""
import time

import numpy as np
import pandas as pd
import pytest

from buckaroo.compare import (head_diff, head_diff_polars, head_diff_xorq, key_diff, key_diff_polars, key_diff_xorq, stats_diff, stats_diff_polars, stats_diff_xorq)

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


# --- row counts -------------------------------------------------------------
# Linear ops compare SMALL -> BIG (10x). Lazy ops compare TINY -> BIG (100x)
# so a "reads the whole frame" regression shows up as ~100x, not ~1x.
TINY = 10_000
SMALL = 100_000
BIG = 1_000_000


def _gen(n, seed=0):
    """Mixed-dtype frame: a unique int key, a low-cardinality column, nulls, a bool.

    'id' is unique (a real join key). 'cat' has 10 distinct values, which is
    exactly the kind of column the pandas/polars key heuristic wrongly treats
    as a join key. Kept allocation-light so generating 1M rows is cheap.
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


def _best_of(fn, n=3):
    """Warmup once, then return the min of n timed runs (steady-state cost)."""
    fn()
    return min(_timed(fn) for _ in range(n))


def _timed(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def _report(op, small_n, small_t, big_n, big_t):
    ratio = big_t / max(small_t, 1e-9)
    print(
        f"\n[compare-perf] {op:<28} "
        f"{small_n:>9,}={small_t * 1e3:7.1f}ms  "
        f"{big_n:>9,}={big_t * 1e3:7.1f}ms  "
        f"ratio={ratio:5.1f}x (rows x{big_n // small_n})")
    return ratio


@pytest.fixture(scope="session")
def data(tmp_path_factory):
    """Generate each row-size once: an in-memory frame plus a parquet file.

    Tests pass the frame/path as BOTH sides of a diff — identical before/after
    is a fine perf proxy (the per-side work is unchanged) and makes
    key_diff_xorq match every row exactly once.
    """
    d = tmp_path_factory.mktemp("compare_perf")
    frames, paths = {}, {}
    for n in (TINY, SMALL, BIG):
        df = _gen(n)
        frames[n] = df
        p = d / f"{n}.parquet"
        df.to_parquet(p)
        paths[n] = p
    return {"frames": frames, "paths": paths}


# ===========================================================================
# stats_diff: O(rows). A 10x row jump should cost ~10x, never ~100x.
# A correct linear backend lands near 10x; the ceiling still trips on an
# accidental O(n^2) regression (~100x).
# ===========================================================================

_LINEAR_MAX = 25.0


def test_stats_diff_linear_pandas(data):
    s, b = data["frames"][SMALL], data["frames"][BIG]
    small_t = _best_of(lambda: stats_diff(s, s), n=3)
    big_t = _best_of(lambda: stats_diff(b, b), n=2)
    ratio = _report("stats_diff (pandas)", SMALL, small_t, BIG, big_t)
    assert ratio < _LINEAR_MAX, f"stats_diff scaling {ratio:.1f}x for 10x rows — superlinear?"


@needs_polars
def test_stats_diff_linear_polars(data):
    s = pl.from_pandas(data["frames"][SMALL])
    b = pl.from_pandas(data["frames"][BIG])
    small_t = _best_of(lambda: stats_diff_polars(s, s), n=3)
    big_t = _best_of(lambda: stats_diff_polars(b, b), n=2)
    ratio = _report("stats_diff (polars)", SMALL, small_t, BIG, big_t)
    assert ratio < _LINEAR_MAX, f"stats_diff_polars scaling {ratio:.1f}x for 10x rows — superlinear?"


@needs_xorq
def test_stats_diff_linear_xorq(data):
    s, b = data["paths"][SMALL], data["paths"][BIG]
    small_t = _best_of(lambda: stats_diff_xorq(s, s), n=3)
    big_t = _best_of(lambda: stats_diff_xorq(b, b), n=1)
    ratio = _report("stats_diff (xorq)", SMALL, small_t, BIG, big_t)
    assert ratio < _LINEAR_MAX, f"stats_diff_xorq scaling {ratio:.1f}x for 10x rows — superlinear?"


# ===========================================================================
# head_diff: must NOT read the whole frame on the lazy (parquet) backends.
# 100x more rows should stay near-flat; a non-lazy regression scales ~100x.
# ===========================================================================

_LAZY_MAX = 15.0


@needs_polars
def test_head_diff_lazy_polars(data):
    t, b = data["paths"][TINY], data["paths"][BIG]
    small_t = _best_of(lambda: head_diff_polars(t, t), n=3)
    big_t = _best_of(lambda: head_diff_polars(b, b), n=3)
    ratio = _report("head_diff (polars,lazy)", TINY, small_t, BIG, big_t)
    assert ratio < _LAZY_MAX, (
        f"head_diff_polars is {ratio:.1f}x slower for 100x rows — lazy scan should keep this "
        "near-flat; it may be reading the full frame instead of N rows + metadata.")


@needs_xorq
def test_head_diff_lazy_xorq(data):
    t, b = data["paths"][TINY], data["paths"][BIG]
    small_t = _best_of(lambda: head_diff_xorq(t, t), n=3)
    big_t = _best_of(lambda: head_diff_xorq(b, b), n=3)
    ratio = _report("head_diff (xorq,lazy)", TINY, small_t, BIG, big_t)
    assert ratio < _LAZY_MAX, (
        f"head_diff_xorq is {ratio:.1f}x slower for 100x rows — limit(n)+count should keep this "
        "near-flat; it may be materialising the full frame.")


def test_head_diff_pandas_independent_of_rows(data):
    # pandas head_diff is on an in-memory frame; it only renders head(10) + len(),
    # so it is O(1) in row count.
    s, b = data["frames"][SMALL], data["frames"][BIG]
    small_t = _best_of(lambda: head_diff(s, s), n=3)
    big_t = _best_of(lambda: head_diff(b, b), n=3)
    ratio = _report("head_diff (pandas)", SMALL, small_t, BIG, big_t)
    assert ratio < _LAZY_MAX, f"head_diff (pandas) scales with rows ({ratio:.1f}x) — should be ~O(1)."


# ===========================================================================
# key_diff: xorq picks a real unique key -> stays linear and matches 1:1.
# ===========================================================================


@needs_xorq
def test_key_diff_xorq_linear_with_unique_key(data):
    t, s = data["paths"][TINY], data["paths"][SMALL]
    big_res = key_diff_xorq(s, s)
    # It must detect the unique 'id', not the low-card 'cat', so every row
    # matches exactly once: matched == n, no cartesian blowup.
    assert big_res is not None and big_res["matched"] == SMALL, (
        f"key_diff_xorq matched={big_res and big_res['matched']} (expected {SMALL}); "
        f"detected keys={big_res and big_res['keys']} — should be a unique key.")
    small_t = _best_of(lambda: key_diff_xorq(t, t), n=2)
    big_t = _best_of(lambda: key_diff_xorq(s, s), n=2)
    ratio = _report("key_diff (xorq,unique)", TINY, small_t, SMALL, big_t)
    assert ratio < _LINEAR_MAX, (
        f"key_diff_xorq is {ratio:.1f}x for 10x rows — should be ~linear on a unique key.")


# ===========================================================================
# key_diff must NOT cartesian-blow-up (pandas / polars). The detector picks the
# unique 'id', so matched == n (one row per input row). The earlier low-
# cardinality heuristic picked 'cat' (10 distinct) and produced ~n^2/k matched
# rows; the deterministic matched count is the regression guard.
# ===========================================================================

_BLOWUP_N = 2_000  # quadratic blowup would build ~n^2/k rows here — kept small


def test_key_diff_pandas_no_cartesian_blowup():
    a, b = _gen(_BLOWUP_N, 0), _gen(_BLOWUP_N, 1)
    res = key_diff(a, b)
    matched = res["matched"] if res else None
    print(f"\n[compare-perf] key_diff (pandas) n={_BLOWUP_N} matched={matched} keys={res and res['keys']}")
    # A sound key gives one matched row per input row.
    assert res is not None and res["keys"] == ["id"] and matched == _BLOWUP_N, (
        f"key_diff matched={matched} for n={_BLOWUP_N} on keys={res and res['keys']} — "
        "expected matched==n on the unique 'id' (no cartesian blowup).")


@needs_polars
def test_key_diff_polars_no_cartesian_blowup():
    a, b = pl.from_pandas(_gen(_BLOWUP_N, 0)), pl.from_pandas(_gen(_BLOWUP_N, 1))
    res = key_diff_polars(a, b)
    matched = res["matched"] if res else None
    print(f"\n[compare-perf] key_diff (polars) n={_BLOWUP_N} matched={matched} keys={res and res['keys']}")
    assert res is not None and res["keys"] == ["id"] and matched == _BLOWUP_N, (
        f"key_diff_polars matched={matched} for n={_BLOWUP_N} on keys={res and res['keys']} — "
        "expected matched==n on the unique 'id' (no cartesian blowup).")
