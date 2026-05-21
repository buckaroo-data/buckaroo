"""Server-side xorq loading — mirrors ``buckaroo.server.data_loading``
for the xorq backend.

Isolated module so the xorq import surface stays out of the rest of
the server. The handler in ``handlers.py`` lazy-imports this module
inside ``LoadExprHandler.post`` so a server without ``buckaroo[xorq]``
installed still imports cleanly.
"""
from __future__ import annotations

import logging
import os
import traceback

from buckaroo.xorq_buckaroo import (
    NoCleaningConfXorq, XorqAutocleaning, XorqDataflow, XorqDfStatsV2,
    XorqInfiniteSampling, _XORQ_ANALYSIS_KLASSES, _expr_count,
    window_to_parquet)

# Mirrors ``websocket_handler._BUCKAROO_DEBUG`` — when set, error_info
# carries the full traceback for local debugging. Without it, clients see
# a generic message so source paths and stack frames don't leak.
_BUCKAROO_DEBUG = os.environ.get("BUCKAROO_DEBUG", "").lower() in ("1", "true")
log = logging.getLogger("buckaroo.server.xorq_loading")


class XorqServerDataflow(XorqDataflow):
    """Headless XorqDataflow with infinite sampling.

    Mirrors the class-attribute set ``XorqBuckarooWidget`` injects into
    its ``InnerDataFlow`` (xorq_buckaroo.py:181-186) — without
    ``InnerDataFlow``'s widget-side ``_df_to_obj`` override, since the
    server never serialises a main-frame sample (``skip_main_serial=True``).
    """

    sampling_klass = XorqInfiniteSampling
    autocleaning_klass = XorqAutocleaning
    autoclean_conf = (NoCleaningConfXorq,)
    DFStatsClass = XorqDfStatsV2
    analysis_klasses = _XORQ_ANALYSIS_KLASSES


def load_expr_build_dir(build_dir: str):
    """Rehydrate an ibis expression from a xorq build directory.

    Wrapper around ``xorq.api.load_expr``. Build dirs that contain
    in-memory memtables (the small reference tables joined against a
    remote source) need a backend to re-read their parquet snapshot
    during rehydration. xorq's own datafusion backend is the natural
    default — it's what ``xo.connect()`` returns and what ships with
    every ``buckaroo[xorq]`` install. If the caller has already set
    a default (e.g. DuckDB), respect that."""
    from xorq.api import connect, load_expr  # noqa: PLC0415  (lazy, see module docstring)
    from xorq.vendor import ibis  # noqa: PLC0415
    # Direct option assignment — `ibis.set_backend(...)` was removed in
    # xorq 0.3.25; the option is the stable cross-version contract.
    if ibis.options.default_backend is None:
        ibis.options.default_backend = connect()
    return load_expr(build_dir)


def get_xorq_metadata(xorq_dataflow: XorqServerDataflow, build_dir: str) -> dict:
    """Metadata payload matching ``data_loading.get_metadata``'s shape."""
    expr = xorq_dataflow.processed_df
    columns = [{"name": str(name), "dtype": str(dtype)}
        for name, dtype in expr.schema().items()]
    return {"path": build_dir, "rows": _expr_count(expr), "columns": columns}


def handle_infinite_request_xorq(xorq_dataflow: XorqServerDataflow,
        payload_args: dict) -> tuple[dict, bytes]:
    """Drive one infinite_request window against a xorq expression.

    Reads the current ``processed_df`` (the expression, post-filter)
    from ``widget_args_tuple``, calls the shared
    ``window_to_parquet`` helper, and returns the
    ``(json_msg, parquet_bytes)`` pair the WebSocket handler ships as
    a text + binary frame pair (matching the pandas/polars paths)."""
    start = int(payload_args["start"])
    end = int(payload_args["end"])
    _unused, processed_df, merged_sd = xorq_dataflow.widget_args_tuple
    if processed_df is None:
        return ({"type": "infinite_resp", "key": payload_args, "data": [], "length": 0}, b"")

    try:
        sort = payload_args.get("sort")
        sort_col = None
        ascending = True
        if sort:
            sort_col = merged_sd[sort]["orig_col_name"]
            ascending = payload_args.get("sort_direction") == "asc"

        total_length = _expr_count(processed_df)
        parquet_bytes = window_to_parquet(processed_df, start, end, sort_col, ascending)
        return ({"type": "infinite_resp", "key": payload_args, "data": [],
            "length": total_length}, parquet_bytes)
    except Exception:
        tb = traceback.format_exc()
        log.error("xorq infinite_request error: %s", tb)
        # Mirrors the pandas-path gate in websocket_handler.py — clients
        # in production runs see a generic message; only ``BUCKAROO_DEBUG``
        # opens the source-leak channel.
        return ({"type": "infinite_resp", "key": payload_args, "data": [],
            "length": 0,
            "error_info": tb if _BUCKAROO_DEBUG else "Request failed"}, b"")
