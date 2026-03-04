# Kernel Contention Diagnostics — Deep Research

Research for Exp 54: diagnosing why 0s stagger causes 8/9 kernels to hang at "starting".

## Background

With 9 JupyterLab servers launching simultaneously (0s stagger), 8/9 kernels never transition from "starting" to "idle". A 2s stagger between launches fixes it. We suspect ZMQ socket contention or kernel provisioner bottlenecks but have no proof.

---

## Tool #1: `ss` — Socket Statistics

### What it does

`ss` is the modern replacement for `netstat`. It queries the kernel directly via Netlink to dump socket statistics. Fast, no special permissions needed, works inside Docker containers.

### Key flags

| Flag | Meaning |
|------|---------|
| `-t` | TCP sockets only |
| `-n` | Numeric output (don't resolve names) |
| `-p` | Show owning process (PID + name) |
| `-a` | All sockets (listening + non-listening) |
| `-l` | Listening sockets only |
| `-i` | Internal TCP info (RTT, retransmits) |
| `-m` | Socket memory usage |
| `-s` | Summary statistics |

### Example output

```
State      Recv-Q  Send-Q  Local Address:Port   Peer Address:Port   Process
ESTAB      0       0       127.0.0.1:8889       127.0.0.1:42356     users:(("jupyter-lab",pid=1234,fd=12))
ESTAB      0       0       127.0.0.1:42356      127.0.0.1:8889      users:(("chromium",pid=5678,fd=45))
LISTEN     0       128     0.0.0.0:8889          0.0.0.0:*           users:(("jupyter-lab",pid=1234,fd=8))
```

Key columns:
- **State**: LISTEN, ESTAB, SYN-SENT, CLOSE-WAIT, TIME-WAIT
- **Recv-Q / Send-Q**: For LISTEN sockets, Recv-Q = backlog of pending connections. For ESTAB, bytes in buffer.
- **Process**: PID and fd of owning process

### Filtering for our ports

```bash
# All TCP sockets on JupyterLab ports 8889-8897
ss -tnp '( sport >= :8889 and sport <= :8897 ) or ( dport >= :8889 and dport <= :8897 )'

# Listening sockets only (should see exactly 9)
ss -tlnp 'sport >= :8889 and sport <= :8897'

# Summary of all socket states
ss -s
```

### What to look for in our failure mode

| Symptom | Likely cause |
|---------|-------------|
| Fewer than 9 LISTEN sockets on 8889-8897 | Server failed to start or bind |
| Many SYN-SENT to localhost | Target server not accepting connections yet |
| Recv-Q > 0 on LISTEN sockets | Backlog full — server not accept()ing fast enough |
| Many TIME-WAIT sockets | Rapid connect/disconnect cycle (warmup retries) |
| CLOSE-WAIT accumulating | Application not closing sockets (ZMQ leak) |

### Periodic snapshots

```bash
# Snapshot every 0.5s during warmup
while true; do
    echo "=== $(date +%H:%M:%S.%N) ==="
    ss -tnp '( sport >= :8889 and sport <= :8897 ) or ( dport >= :8889 and dport <= :8897 )'
    sleep 0.5
done > /tmp/ss-snapshots.log &
```

### Docker: works out of the box, no capabilities needed.

---

## Tool #2: `strace` — System Call Tracer

### What it does

Intercepts every system call a process makes. Uses `ptrace` to pause the target process on each syscall entry/exit, inspect arguments and return value, then resume it. Think of it as a wiretap on the process's conversation with the kernel.

### Key flags

| Flag | Meaning |
|------|---------|
| `-c` | Summary mode: counts syscalls, time, errors. Prints a table at the end |
| `-p PID` | Attach to a running process |
| `-f` | Follow forks (trace child processes too) |
| `-e trace=network` | Only trace network syscalls (socket, bind, connect, sendmsg, recvmsg) |
| `-e trace=desc` | Trace descriptor syscalls (read, write, close, poll, epoll_wait) |
| `-T` | Show time spent in each syscall |
| `-tt` | Microsecond-precision timestamps |
| `-o FILE` | Write to file instead of stderr |

### Summary mode example (`strace -c`)

```
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 45.23    0.892301          12     74358           epoll_wait
 22.11    0.436200           8     54525           recvmsg
 15.67    0.309100           7     44150           sendmsg
  3.21    0.063400          64       990        12 connect
  0.72    0.014200          14      1014       507 futex
```

### How to read it

- **epoll_wait dominating**: Process is mostly idle/waiting. Normal for I/O-bound JupyterLab.
- **High futex errors**: Lock contention between threads.
- **connect errors**: Target not listening when client tries to connect.
- **bind errors (EADDRINUSE)**: Port already in use.
- **getrandom taking seconds**: Entropy starvation in container (known ZMQ issue — libzmq #3183).
- **sendmsg/recvmsg slow (high usecs/call)**: ZMQ socket buffer contention.

### Relevant syscalls for our problem

| Syscall | Why it matters |
|---------|---------------|
| `epoll_wait` / `poll` | ZMQ event loop. Stuck here = waiting for events that never come |
| `connect` | ZMQ establishing connections. Errors = target not listening |
| `bind` | Port binding. EADDRINUSE = port conflict |
| `sendmsg` / `recvmsg` | ZMQ messaging. Slow = buffer contention |
| `futex` | Lock/mutex. High errors = thread contention |
| `getrandom` | ZMQ CURVE init. Can block on low entropy |

### Attaching to JupyterLab

```bash
# Find PIDs
pgrep -f 'jupyter-lab'

# Attach to one (summary, follow forks, network+descriptor only)
strace -c -f -e trace=network,desc -p 1234 -o /tmp/strace-1234.log

# Attach to all at once
strace -c -f -e trace=network,desc $(pgrep -f 'jupyter-lab' | sed 's/^/-p /')
```

### Performance impact

**strace is heavyweight.** It pauses the target twice per syscall (entry + exit) and context-switches to the strace process. Expect 2-10x slowdown during kernel startup. For our use case this is acceptable — the bug manifests as hangs (not timing races), so the slowdown won't mask it.

`-e trace=network` reduces overhead because non-matching syscalls are filtered in-kernel via seccomp-bpf (strace 5.3+, Ubuntu 24.04 has strace 6.x).

### Docker: REQUIRES `cap_add: SYS_PTRACE` in docker-compose.yml

Docker's default seccomp profile blocks `ptrace`. Add to docker-compose.yml:

```yaml
services:
  ci:
    cap_add:
      - SYS_PTRACE
```

Requires `docker compose down && docker compose up -d`. `strace` must also be installed inside the container (`apt-get install -y strace`).

---

## Tool #3: JupyterLab `--debug` + `--Session.debug=True`

### What it does

`--debug` sets JupyterLab's log level to DEBUG. Shows kernel manager lifecycle events, ZMQ channel setup, HTTP requests, Tornado IOLoop events.

`--Session.debug=True` additionally logs every ZMQ message on shell, control, stdin, and iopub channels. This is the key flag for seeing whether `kernel_info_request` is sent and whether `kernel_info_reply` arrives.

### Diagnostic launch command

```bash
jupyter lab --no-browser --port="$port" \
    --ServerApp.token="$JUPYTER_TOKEN" \
    --ServerApp.allow_origin='*' \
    --ServerApp.disable_check_xsrf=True \
    --allow-root \
    --debug \
    --Session.debug=True \
    >/tmp/jupyter-port${port}-debug.log 2>&1 &
```

### What the logs show

```
[D 2024-01-15 10:23:45.123 ServerApp] Starting kernel: ['python3', '-m', 'ipykernel_launcher', '-f', '/root/.local/share/jupyter/runtime/kernel-abc123.json']
[D 2024-01-15 10:23:45.456 ServerApp] Connecting to: tcp://127.0.0.1:52341
[I 2024-01-15 10:23:46.789 ServerApp] Kernel started: abc123-def4-5678-...
[D 2024-01-15 10:23:46.790 ServerApp] Kernel abc123 execution_state: 'starting'
```

If 8/9 kernels are stuck, you'd see `kernel_info_request` sent but no `kernel_info_reply` — pinpointing where the hang occurs.

### Docker: no special requirements. Just more verbose logging.

---

## Tool #4: ZMQ Socket Monitor (pyzmq)

### What it does

pyzmq can attach a monitor to any ZMQ socket to observe connection events in real time. This is a programmatic API, not a CLI tool.

### Monitor events

| Event | Meaning |
|---|---|
| `EVENT_CONNECTED` | TCP connection established |
| `EVENT_LISTENING` | Socket bound to interface |
| `EVENT_BIND_FAILED` | Socket could NOT bind |
| `EVENT_ACCEPTED` | Incoming connection accepted |
| `EVENT_ACCEPT_FAILED` | Incoming connection rejected |
| `EVENT_DISCONNECTED` | Unexpected disconnect |
| `EVENT_HANDSHAKE_SUCCEEDED` | ZMTP handshake completed |
| `EVENT_HANDSHAKE_FAILED_PROTOCOL` | ZMTP handshake failed |

### Limitation

ZMQ does NOT expose current queue depth. You can see high-water marks (limits) but not how many messages are currently queued.

---

## Primary Hypothesis: TCP Port Collision

This is the **most likely root cause** based on the research.

### How kernel port allocation works

When `POST /api/kernels` is called, `write_connection_file()` allocates 5 ports (shell, iopub, stdin, control, heartbeat) by:

1. `socket.bind((ip, 0))` — OS picks a free ephemeral port
2. `port = sock.getsockname()[1]` — read the port number
3. `sock.close()` — **release the port**
4. Write the port number to the connection JSON file
5. Later, the kernel subprocess reads the JSON and `zmq_bind()` to those ports

**The race:** Between step 3 (close) and step 5 (kernel bind), another kernel's step 1 can get the **same port** from the OS. With 9 servers × 5 ports = 45 port allocations in a ~100ms window, collisions are likely.

### Why 2s stagger fixes it

With 2s between launches, each server's `write_connection_file()` + kernel bind sequence completes before the next server starts. The OS never hands out a port that's still in the gap between close and re-bind.

### Cross-server cache is useless

`jupyter_client` has a `LocalPortCache` (PR #490) to prevent port reuse within a single `MultiKernelManager`. But each of our 9 JupyterLab servers has its **own** `MultiKernelManager`, so the cache provides ZERO protection across servers.

### How to prove it

```python
# Inject into warmup — check connection files for duplicate ports
import json, glob, collections

ports = collections.Counter()
for f in glob.glob('/root/.local/share/jupyter/runtime/kernel-*.json'):
    with open(f) as fh:
        info = json.load(fh)
    for key in ['shell_port', 'iopub_port', 'stdin_port', 'control_port', 'hb_port']:
        ports[info[key]] += 1

dupes = {p: c for p, c in ports.items() if c > 1}
if dupes:
    print(f"PORT COLLISION DETECTED: {dupes}")
else:
    print("No port collisions")
```

### Possible fixes (if confirmed)

1. **Keep the 2s stagger** — current fix, works, adds ~16s to total
2. **Pre-allocate ports**: Assign fixed port ranges per server (e.g., server 0 gets 50000-50004, server 1 gets 50010-50014) via `--KernelManager.shell_port=50000` etc.
3. **Use IPC transport**: `--KernelManager.transport=ipc` uses Unix domain sockets instead of TCP, eliminating port allocation entirely
4. **Bind-hold pattern**: Modify warmup to bind ports, hold them open, then pass to kernel subprocess (would need kernel provisioner changes)

---

## Secondary Hypotheses

### B: CPU Starvation / Heartbeat Timeout

9 JupyterLab + 9 ipykernel + 9 Chromium = 27+ processes all initializing on 16 vCPU. Heartbeat thread may not get scheduled, causing the server to declare the kernel dead.

**Diagnostic:**
```bash
# Increase kernel info timeout
jupyter lab --MappingKernelManager.kernel_info_timeout=120 ...
```

### C: Entropy Starvation

ZMQ uses `getrandom()` for CURVE security initialization (libzmq issue #3183). In containers with low entropy, this can block for seconds.

**Diagnostic:**
```bash
cat /proc/sys/kernel/random/entropy_avail  # Should be >256
```

---

## Implementation: Diagnostic Collection Script

### Prerequisites

1. Add `strace` to Dockerfile: `apt-get install -y strace`
2. Add to docker-compose.yml:
   ```yaml
   cap_add:
     - SYS_PTRACE
   ```
3. Recreate container: `docker compose down && docker compose up -d`

### The script

```bash
#!/bin/bash
# collect-diagnostics.sh — run during kernel warmup to capture contention data
# Usage: COLLECT_DIAGNOSTICS=1 in run-ci.sh, or manually:
#   docker exec buckaroo-ci bash /opt/ci-runner/collect-diagnostics.sh [DURATION_S]

set -uo pipefail
DURATION=${1:-30}
DIAG_DIR="/opt/ci/logs/diagnostics/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DIAG_DIR"

echo "[diag] Collecting for ${DURATION}s → $DIAG_DIR"

# 1. ss snapshots every 0.5s
(
    end=$(($(date +%s) + DURATION))
    while [ "$(date +%s)" -lt "$end" ]; do
        echo "=== $(date +%H:%M:%S.%N) ==="
        ss -tnp '( sport >= :8889 and sport <= :8897 ) or ( dport >= :8889 and dport <= :8897 )'
        sleep 0.5
    done
) > "$DIAG_DIR/ss-snapshots.log" 2>&1 &

# 2. Per-port connection counts (CSV)
(
    echo "time,port_8889,port_8890,port_8891,port_8892,port_8893,port_8894,port_8895,port_8896,port_8897"
    end=$(($(date +%s) + DURATION))
    while [ "$(date +%s)" -lt "$end" ]; do
        counts=""
        for port in $(seq 8889 8897); do
            c=$(ss -tn "sport = :$port" | tail -n +2 | wc -l)
            counts="${counts},${c}"
        done
        echo "$(date +%H:%M:%S.%N)${counts}"
        sleep 1
    done
) > "$DIAG_DIR/port-counts.csv" 2>&1 &

# 3. Port collision detector
(
    sleep 5
    for attempt in $(seq 1 6); do
        echo "=== Check $attempt at $(date +%H:%M:%S) ==="
        python3 -c "
import json, glob, collections
ports = collections.Counter()
files = glob.glob('/root/.local/share/jupyter/runtime/kernel-*.json')
print(f'Found {len(files)} connection files')
for f in sorted(files):
    with open(f) as fh:
        info = json.load(fh)
    for key in ['shell_port', 'iopub_port', 'stdin_port', 'control_port', 'hb_port']:
        ports[info[key]] += 1
    print(f'  {f}: shell={info[\"shell_port\"]} iopub={info[\"iopub_port\"]} hb={info[\"hb_port\"]}')
dupes = {p: c for p, c in ports.items() if c > 1}
if dupes:
    print(f'*** PORT COLLISION: {dupes}')
else:
    print('No port collisions')
" 2>&1
        sleep 5
    done
) > "$DIAG_DIR/collisions.log" 2>&1 &

# 4. strace on JupyterLab PIDs (if available)
STRACE_PIDS=()
for jpid in $(pgrep -f 'jupyter-lab' 2>/dev/null); do
    strace -c -f -e trace=network,desc -p "$jpid" \
        -o "$DIAG_DIR/strace-${jpid}.log" 2>/dev/null &
    STRACE_PIDS+=($!)
done

# 5. CPU load snapshots
(
    end=$(($(date +%s) + DURATION))
    while [ "$(date +%s)" -lt "$end" ]; do
        echo "$(date +%H:%M:%S.%N) $(cat /proc/loadavg)"
        sleep 0.5
    done
) > "$DIAG_DIR/loadavg.log" 2>&1 &

# Wait
sleep "$DURATION"

# Stop strace (SIGINT triggers summary output)
for spid in "${STRACE_PIDS[@]}"; do
    kill -INT "$spid" 2>/dev/null; done
sleep 2
kill 0 2>/dev/null || true
echo "[diag] Done → $DIAG_DIR"
```

### Integration with run-ci.sh

Add after JupyterLab servers start (after line 372 in `job_jupyter_warmup`):

```bash
if [[ "${COLLECT_DIAGNOSTICS:-0}" == "1" ]]; then
    bash "$CI_RUNNER_DIR/collect-diagnostics.sh" 30 &
fi
```

Trigger with: `COLLECT_DIAGNOSTICS=1 docker exec buckaroo-ci bash /opt/ci-runner/run-ci.sh ...`

---

## References

- [jupyter_client issue #487: Spawning many kernels → ZMQError](https://github.com/jupyter/jupyter_client/issues/487)
- [jupyter_client PR #490: Port collision prevention (LocalPortCache)](https://github.com/jupyter/jupyter_client/pull/490)
- [libzmq issue #3183: getrandom() hangs in containers](https://github.com/zeromq/libzmq/issues/3183)
- [jupyter-server issue #305: kernel_info_request only on WebSocket connect](https://github.com/jupyter-server/jupyter_server/issues/305)
- [pyzmq socket monitor API](https://pyzmq.readthedocs.io/en/latest/api/zmq.utils.monitor.html)
- [Brendan Gregg: strace performance overhead](https://www.brendangregg.com/blog/2014-05-11/strace-wow-much-syscall.html)
