#!/bin/bash
set -uo pipefail
cd /repo

# Skip entirely if MCP integration tests aren't present (old commits predate MCP).
if [[ ! -f tests/unit/server/test_mcp_server_integration.py ]]; then
    echo "[skip] MCP tests not present in this commit"
    exit 0
fi

venv=/tmp/ci-mcp-$$
rm -rf "$venv"
uv venv "$venv" -q
wheel=$(ls dist/buckaroo-*.whl | head -1)
uv pip install --python "$venv/bin/python" "${wheel}[mcp]" pytest -q

rc=0
# test_uvx_no_stdout_pollution: flushes subprocess stdin which Docker closes
# unexpectedly (non-TTY pipe), causing ValueError: flush of closed file.
BUCKAROO_MCP_CMD="$venv/bin/buckaroo-table" \
    "$venv/bin/pytest" \
        tests/unit/server/test_mcp_uvx_install.py \
        tests/unit/server/test_mcp_server_integration.py \
        --deselect tests/unit/server/test_mcp_uvx_install.py::TestMcpInstall::test_uvx_no_stdout_pollution \
        -v --color=yes -m slow || rc=$?
"$venv/bin/pytest" \
    tests/unit/server/test_mcp_uvx_install.py::TestUvxFailureModes \
    -v --color=yes -m slow || rc=$?
rm -rf "$venv"
exit $rc
