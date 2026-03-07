# Tech 5a (standalone): Keep Kernels Alive from Warmup

**Goal:** When servers are NOT pre-started (cold start), keep the warmup kernels alive
instead of deleting them. Saves ~4-6s of import burst during pw-jupyter.

This is the cold-start fallback for Tech 1+5a. When Tech 1 is working (servers
pre-started), this is already handled. This section covers the modification needed
when warmup runs during the CI run itself.

---

## What changes

### 1. Modify `job_jupyter_warmup()` in `run-ci.sh`

The kernel warmup currently DELETEs the kernel after reaching idle (line 629-634).
Change: DON'T delete. Save kernel ID to a state file for pw-jupyter.

```python
# REMOVE this block (lines 629-634):
# try:
#     req = urllib.request.Request(
#         f'{base}/api/kernels/{kid}?token={token}', method='DELETE')
#     urllib.request.urlopen(req)
# except Exception:
#     pass

# ADD: save kernel ID for pw-jupyter
with open(f'/tmp/ci-jupyter-warmup-kernel-{port}', 'w') as f:
    f.write(kid)
```

### 2. Modify `test_playwright_jupyter_parallel.sh`

When connecting to a JupyterLab server, check for pre-warmed kernel:
```bash
# For each slot, if a warm kernel exists, pass its ID to the notebook
KERNEL_ID_FILE="/tmp/ci-jupyter-warmup-kernel-${port}"
if [[ -f "$KERNEL_ID_FILE" ]]; then
    export JUPYTER_WARM_KERNEL_ID=$(cat "$KERNEL_ID_FILE")
fi
```

**Critical question:** How does Playwright open a notebook on a *specific* kernel?
- JupyterLab URL: `?kernel_id=...` is not standard
- Jupyter Sessions API: `POST /api/sessions` with `kernel.id` — opens a notebook
  session attached to an existing kernel
- Need to modify the Playwright test to use the Sessions API before navigating

This is the hardest part of 5a. The Playwright test currently just opens a notebook URL
and lets JupyterLab auto-create a kernel. To reuse a warm kernel, the test (or a
pre-step) needs to create a session via REST API binding the notebook to the existing
kernel.

**Alternative approach:** Don't try to reuse kernel IDs. Instead, just don't delete
kernels — the heavy imports (pandas/polars) populate the OS page cache + Python's
bytecode cache. Even if pw-jupyter creates NEW kernels, their imports will be faster
because the .pyc files are warm and the shared libraries are in page cache. This gives
~2-3s instead of ~4-6s but with zero wiring complexity.

---

## Validation

1. Run with kernel deletion removed. Compare pw-jupyter timing.
2. Verify no stale kernel issues (OOM from 18 kernels alive simultaneously).

## Risks

- 9 warm kernels + 9 new kernels = 18 kernels = high memory. Each kernel ~150MB.
  18 x 150MB = 2.7GB. On 64GB machine, fine. On 32GB, tight.
- If the warm kernels' Python processes are OOM-killed, the server may behave oddly.
