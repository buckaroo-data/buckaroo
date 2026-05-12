#!/usr/bin/env bash
#
# Wraps a pytest invocation so a known polars-stream / pyo3 shutdown race
# does not fail the job when every test passed.
#
# Symptom (intermittent, only on polars >= 1.38 + pyo3 0.27 — i.e. our
# "Max Versions" matrix):
#
#   ==== 862 passed, 5 skipped, 103 deselected, 16 warnings in 93s ====
#   FATAL: exception not rethrown
#   thread 'tokio-runtime-worker' panicked at .../pyo3-0.27.2/.../interpreter_lifecycle.rs:117:13:
#     The Python interpreter is not initialized and the `auto-initialize`
#     feature is not enabled.
#   thread 'async-executor-1' panicked at crates/polars-stream/src/nodes/io_sinks/writers/parquet/mod.rs
#   Aborted (core dumped)
#   ##[error]Process completed with exit code 134.
#
# Cause: pytest finishes; Python begins finalization; polars-stream's
# background workers (tokio + async-executor for the parquet sink) still
# hold pending tasks and try to call back into Python through pyo3, which
# is already past Py_Finalize. pyo3 panics, abort() runs, exit code 134
# (= 128 + SIGABRT). Every test had already passed; the failure is purely
# in Rust-side teardown.
#
# This wrapper:
#   1. Runs the command (passed as argv).
#   2. Treats exit 134 as success ONLY when ALL of these hold:
#        a. The captured output shows a passing pytest summary.
#        b. No `failed` / `error` lines appear in the summary.
#        c. The captured output contains a known signature of the
#           polars-stream / pyo3 shutdown race (the FATAL line plus a
#           pyo3/polars-stream panic frame). Without this signature
#           guard, an unrelated native crash producing exit 134 after a
#           passing summary would silently get reported as success.
#   3. Otherwise propagates the original exit code unchanged.
#
# Real failures (pytest exit 1, crashes before the summary, errored
# collection, native crashes in other libraries) are preserved.

set -uo pipefail

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <pytest-command> [args...]" >&2
    exit 2
fi

LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

# Run the command, mirror output to console AND capture for inspection.
"$@" 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}

# Signature of the known polars-stream / pyo3 shutdown race. We require
# both the FATAL marker AND a Rust panic frame from pyo3 OR polars-stream.
# An unrelated SIGABRT (e.g. malloc corruption, a different C extension
# crashing) would not produce these strings.
has_known_signature() {
    grep -qE "FATAL: exception not rethrown" "$LOG" \
        && grep -qE "panicked at .*(pyo3|polars-stream|polars_stream)" "$LOG"
}

if [ "$status" -eq 134 ] \
   && grep -qE "[0-9]+ passed" "$LOG" \
   && ! grep -qE "[0-9]+ failed" "$LOG" \
   && ! grep -qE "[0-9]+ error" "$LOG" \
   && has_known_signature; then
    echo ""
    echo "::warning::pytest exited 134 (SIGABRT) but the summary shows all tests passed"
    echo "::warning::AND the polars-stream / pyo3 shutdown signature was present in output."
    echo "::warning::Treating as success. See scripts/run_pytest_tolerant.sh for context."
    exit 0
fi

exit "$status"
