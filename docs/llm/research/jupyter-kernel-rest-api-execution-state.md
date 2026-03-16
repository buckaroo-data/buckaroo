# Why JupyterLab Kernels Stay "starting" via REST API

**Date:** 2026-03-03
**Context:** CI warmup creates kernels via POST /api/kernels, polls GET /api/kernels/{id} for execution_state. With PARALLEL=1, kernels reach "idle" in ~70s. With PARALLEL=9, all kernels stay "starting" for 90+ seconds and never transition.

## Root Cause: No Messages Reach the Kernel, So No IOPub Status Updates Occur

The REST API endpoint `GET /api/kernels/{id}` returns `kernel.execution_state` from the `MappingKernelManager`'s in-memory model. This value starts as `"starting"` and is only updated by a `record_activity` callback listening on the kernel's ZMQ iopub channel. **The callback can correctly transition `"starting"` to `"idle"`, but only if iopub messages actually arrive. With a pure REST-only workflow (no WebSocket connection, no code execution), nobody sends the kernel any requests, so the kernel never publishes any iopub messages, and `execution_state` stays `"starting"` forever.**

There are two layers to this problem:

1. **Primary: No one talks to the kernel.** POST /api/kernels starts the kernel process and returns. The `KernelManager.ready` future resolves when the subprocess launches -- it does NOT send a `kernel_info_request` or any other message. The kernel sits idle on its ZMQ channels waiting for a request that never comes.

2. **Secondary: ZMQ SUB socket subscription race.** Even if someone did send a request, the server's `_activity_stream` (ZMQ SUB socket created by `start_watching_activity`) might miss early iopub messages due to the well-known SUB subscription propagation delay ([jupyter/jupyter_client#593](https://github.com/jupyter/jupyter_client/issues/593)).

### Detailed Code Trace

Source: [`jupyter_server/services/kernels/kernelmanager.py`](https://github.com/jupyter-server/jupyter_server/blob/main/jupyter_server/services/kernels/kernelmanager.py)

**Step 1: `_async_start_kernel` sets `execution_state = "starting"` and creates a task for `_finish_kernel_start`:**

```python
kernel.execution_state = "starting"
# ...
task = asyncio.create_task(self._finish_kernel_start(kernel_id))
```

**Step 2: `_finish_kernel_start` awaits `km.ready` (process launch), then calls `start_watching_activity`:**

```python
async def _finish_kernel_start(self, kernel_id):
    km = self.get_kernel(kernel_id)
    if hasattr(km, "ready"):
        await km.ready  # Waits for subprocess to start (NOT for kernel to be responsive)
    self._kernel_ports[kernel_id] = km.ports
    self.start_watching_activity(kernel_id)  # Creates ZMQ SUB on iopub
```

The `KernelManager.ready` future resolves when the kernel subprocess starts. It does NOT send `kernel_info_request` or verify the kernel is responsive. Source: [`jupyter_client/manager.py`](https://github.com/jupyter/jupyter_client/blob/main/jupyter_client/manager.py)

**Step 3: `start_watching_activity` creates a ZMQ SUB socket and registers `record_activity`:**

```python
def start_watching_activity(self, kernel_id):
    kernel = self._kernels[kernel_id]
    kernel._activity_stream = kernel.connect_iopub()
    # ...
    def record_activity(msg_list):
        # ...
        if msg_type == "status":
            execution_state = msg["content"]["execution_state"]
            if self.track_message_type(parent_msg_type):
                kernel.execution_state = execution_state
            elif kernel.execution_state == "starting" and execution_state != "starting":
                kernel.execution_state = "idle"
    kernel._activity_stream.on_recv(record_activity)
```

Note: the `if msg_type == "status"` block is **not** gated by the `track_message_type` check on `msg_type`. The `execution_state` update logic runs for ALL status messages, not just tracked ones. The `elif` branch correctly handles `starting -> idle` for any parent message type.

**Step 4: Nothing happens.** The kernel process is running. The iopub SUB socket is listening. But no one sends the kernel a `kernel_info_request`, `execute_request`, or any other message. The kernel publishes exactly one `status: starting` message at process startup (from [`ipykernel/kernelbase.py`](https://github.com/ipython/ipykernel/blob/main/ipykernel/kernelbase.py):

```python
# In ipykernel's start():
self._publish_status("starting", "shell")
```

This message is likely **missed** by `record_activity` because the SUB socket is created AFTER the kernel process starts (the `km.ready` await completes, THEN `connect_iopub()` is called). The kernel's `status: starting` message was already published before the SUB subscription propagated.

After that single message, **the kernel goes quiet.** It has nothing to do. No iopub messages flow. `record_activity` is never called. `execution_state` stays `"starting"` on the server.

### What the `record_activity` callback CAN do (if messages arrive)

The callback IS properly coded to handle the transition. If someone sends a `kernel_info_request`:
- The kernel publishes `status: busy` with `parent_header.msg_type = "kernel_info_request"`
- `"kernel_info_request"` is in the untracked list, so `track_message_type("kernel_info_request")` = False
- But `kernel.execution_state == "starting"` and `"busy" != "starting"`, so the `elif` fires: `kernel.execution_state = "idle"`

The problem is not the callback logic. The problem is that **no messages ever arrive at the callback** because nobody sends the kernel any requests via the REST API path.

### What DOES work: WebSocket "nudge" mechanism

When a WebSocket client connects (`KernelWebsocketHandler.open()`), it calls `connection.prepare()` which calls `nudge()`. The nudge mechanism ([source](https://github.com/jupyter-server/jupyter_server/blob/main/jupyter_server/services/kernels/connection/channels.py)):
1. Opens transient shell/control channels
2. Sends `kernel_info_request` repeatedly
3. Monitors iopub directly, waiting for both the shell reply AND at least one iopub message
4. Confirms ZMQ subscriptions are active and kernel is responsive

This is the ONLY code path in jupyter_server that actively verifies kernel readiness. It is triggered exclusively by WebSocket connections. The `kernel_info_request` messages it sends also cause iopub status messages that `record_activity` receives, transitioning `execution_state` from "starting" to "idle" as a side effect.

### The ZMQ SUB socket subscription race

Even when messages are being sent, the `_activity_stream` SUB socket can miss early iopub messages because ZMQ SUB subscriptions take time to propagate. The kernel may publish `status: busy` and `status: idle` before the SUB socket receives them. This is the issue documented in [jupyter/jupyter_client#593](https://github.com/jupyter/jupyter_client/issues/593) and fixed for the WebSocket path via the nudge retry mechanism, but NOT fixed for the `record_activity` path.

## Why PARALLEL=1 Works But PARALLEL=9 Doesn't

With PARALLEL=1, the warmup creates a kernel and polls. We observed it reaching "idle" after ~70s. Most likely explanation: something else on the JupyterLab server (perhaps a session manager, extension, or internal heartbeat) eventually sends a message that triggers iopub activity. With only one server, system load is low, and the kernel starts quickly enough that some internal mechanism triggers the transition.

With PARALLEL=9, nine servers start simultaneously on a 16-vCPU machine. CPU contention from 9 simultaneous Python startups (each kernel imports numpy, pandas, etc.) delays kernel initialization. But more fundamentally, the pure REST polling loop (POST kernel -> poll GET -> wait for idle -> DELETE) never sends the kernel any ZMQ messages and never opens a WebSocket. The `execution_state` has no mechanism to transition.

CPU contention amplifies the problem but is NOT the root cause. Even with infinite CPU, `execution_state` would stay "starting" in the pure REST path unless something else sends the kernel a tracked message.

## Confirmed Upstream Issues

- [jupyter-server/enterprise_gateway#1138](https://github.com/jupyter-server/enterprise_gateway/issues/1138): "The /api/kernels call shows the kernel in starting state even when the kernel is busy." Kevin Bates confirms: **"the kernel status will remain in the 'starting' state until the websocket is created."**
- [jupyter-server/jupyter_server#900](https://github.com/jupyter-server/jupyter_server/issues/900): Proposal for a new kernels REST API with proper state tracking via an event system. Still open.
- [jupyter-server/jupyter_server#1395](https://github.com/jupyter-server/jupyter_server/issues/1395): Kernel execution_state not updated after crash with no open notebook (no WebSocket = no status updates flowing).
- [jupyter/jupyter_client#593](https://github.com/jupyter/jupyter_client/issues/593): ZMQ SUB socket subscription race -- messages lost during subscription propagation window.
- [jupyter-server/jupyter_server#361](https://github.com/jupyter-server/jupyter_server/pull/361): PR that added the nudge mechanism -- "nudge kernel with info request until we receive IOPub messages." WebSocket-only fix.

## Solutions

### Option A: Open a WebSocket connection to trigger nudge (CORRECT FIX)

Use `websocat` or a Python websocket client to connect to `/api/kernels/{id}/channels`, triggering the nudge mechanism that properly verifies kernel readiness:

```bash
# Create kernel
KID=$(curl -s -X POST "http://localhost:$PORT/api/kernels" \
  -H "Content-Type: application/json" -d '{"name":"python3"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Open WebSocket to trigger nudge (kernel_info_request loop until iopub responds)
# websocat will connect, nudge fires server-side, kernel transitions to idle
timeout 30 websocat --one-message "ws://localhost:$PORT/api/kernels/$KID/channels" < /dev/null &
WS_PID=$!

# Poll REST API for execution_state (now it WILL transition because nudge sent messages)
for i in $(seq 1 60); do
  STATE=$(curl -s "http://localhost:$PORT/api/kernels/$KID" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['execution_state'])")
  [ "$STATE" = "idle" ] && break
  sleep 1
done
kill $WS_PID 2>/dev/null

# Delete warmup kernel
curl -s -X DELETE "http://localhost:$PORT/api/kernels/$KID"
```

Or with Python's `websocket-client` library:

```python
import websocket, json, threading, time
ws = websocket.WebSocket()
ws.connect(f"ws://localhost:{port}/api/kernels/{kid}/channels")
# Nudge happens server-side on connect; wait briefly then close
time.sleep(5)
ws.close()
```

### Option B: Use jupyter_client directly (bypass REST API entirely)

Instead of the REST API, use `jupyter_client.BlockingKernelClient` which has a proper `wait_for_ready()` method that sends `kernel_info_request` and waits for shell reply + iopub idle:

```python
from jupyter_client import KernelManager
km = KernelManager(kernel_name='python3')
km.start_kernel()
kc = km.client()
kc.start_channels()
kc.wait_for_ready(timeout=60)  # Sends kernel_info_request, waits for reply + iopub idle
print("Kernel ready")
kc.stop_channels()
km.shutdown_kernel()
```

This completely bypasses the broken REST polling path.

### Option C: Don't check execution_state at all -- use fixed delay

```bash
# Create kernel (blocks until subprocess launches)
KID=$(curl -s -X POST "http://localhost:$PORT/api/kernels" \
  -H "Content-Type: application/json" -d '{"name":"python3"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Wait fixed time for kernel to initialize (kernel IS starting regardless of execution_state)
sleep 10

# Delete warmup kernel
curl -s -X DELETE "http://localhost:$PORT/api/kernels/$KID"
```

Crude but avoids the fundamentally broken polling loop. The kernel process IS running and initializing; `execution_state` just doesn't reflect that.

### Option D: Skip kernel warmup entirely

The kernel warmup was added because "HTTP ready != kernel provisioner ready." But Playwright tests open notebooks which create WebSocket connections which trigger the nudge mechanism. The first notebook's kernel startup happens within Playwright's test timeouts anyway.

```bash
# Just check JupyterLab is serving HTTP
for i in $(seq 1 30); do
  curl -sf "http://localhost:$PORT/api/status" && break
  sleep 1
done
```

## Recommendation

**Option D (skip kernel warmup)** is simplest. The warmup was a workaround for a problem that Playwright's own `waitForSelector` timeouts handle. Each Playwright test opens a notebook, which creates a WebSocket, which triggers the nudge, which properly waits for the kernel. The REST warmup kernel adds overhead and its state polling is fundamentally broken.

If kernel warmup is still desired for first-notebook latency reduction, **Option A (WebSocket connection)** is the most correct approach. It exercises the exact code path that JupyterLab uses internally and is the only path in jupyter_server that properly verifies kernel readiness.

## Key Takeaway

**The jupyter_server REST API `GET /api/kernels/{id}` reports stale `execution_state` because the server's iopub activity monitor only updates when messages flow, and no messages flow without a WebSocket connection or direct ZMQ client.** This is by design -- the REST API was built for kernel lifecycle management (create/list/delete), not for kernel readiness checking. Kernel readiness has always been a WebSocket-layer concern in Jupyter's architecture.
