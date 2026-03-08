#!/bin/bash
set -uo pipefail
cd /repo

wheel=$(ls dist/buckaroo-*.whl | head -1)
pids=()
names=()
rc=0

for extra in base polars mcp marimo jupyterlab notebook; do
    (
        cd /repo
        venv=/tmp/ci-smoke-${extra}-$$
        rm -rf "$venv"
        uv venv "$venv" -q
        if [[ "$extra" == "base" ]]; then
            uv pip install --python "$venv/bin/python" "$wheel" -q
        else
            uv pip install --python "$venv/bin/python" "${wheel}[${extra}]" -q
        fi
        "$venv/bin/python" scripts/smoke_test.py "$extra"
        rm -rf "$venv"
    ) &
    pids+=($!)
    names+=("$extra")
done

for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
        echo "FAIL: smoke-${names[$i]}"
        rc=1
    fi
done
exit $rc
