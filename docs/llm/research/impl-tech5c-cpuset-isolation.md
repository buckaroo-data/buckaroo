# Tech 5c: cpuset Isolation

**Goal:** Pin pw-jupyter processes to dedicated cores, eliminating CPU contention from
other jobs. Estimated savings: **3-6s** (unmeasured).

---

## What changes

### 1. Modify `docker-compose.yml`

Add `--privileged` or `SYS_ADMIN` capability:
```yaml
services:
  buckaroo-ci:
    privileged: true  # needed for cgroup writes
    # OR:
    # cap_add:
    #   - SYS_ADMIN
```

### 2. New file: `ci/hetzner/lib/cpuset.sh`

```bash
setup_cpuset() {
    local ncpus
    ncpus=$(nproc)
    if (( ncpus < 12 )); then
        echo "Not enough CPUs for cpuset isolation ($ncpus < 12)" >&2
        return 1
    fi

    # pw-jupyter gets cores 0-11 (12 cores for 9 Chromium + 9 kernels)
    mkdir -p /sys/fs/cgroup/pw-jupyter
    echo "0-11" > /sys/fs/cgroup/pw-jupyter/cpuset.cpus
    echo "0" > /sys/fs/cgroup/pw-jupyter/cpuset.mems

    # everything-else gets cores 12-15
    mkdir -p /sys/fs/cgroup/ci-other
    echo "12-$((ncpus-1))" > /sys/fs/cgroup/ci-other/cpuset.cpus
    echo "0" > /sys/fs/cgroup/ci-other/cpuset.mems
}

run_in_cpuset() {
    local cgroup=$1; shift
    echo $$ > "/sys/fs/cgroup/$cgroup/cgroup.procs"
    "$@"
}
```

### 3. Modify `run_dag()` in `run-ci.sh`

```bash
# Before starting pw-jupyter:
if setup_cpuset 2>/dev/null; then
    # Run pw-jupyter in dedicated cpuset
    run_in_cpuset pw-jupyter run_job playwright-jupyter job_playwright_jupyter_warm & PID_PW_JP=$!
    # Move other running jobs to ci-other cpuset
    for pid in $PID_PY312 $PID_PY314 $PID_SMOKE; do
        echo "$pid" > /sys/fs/cgroup/ci-other/cgroup.procs 2>/dev/null || true
    done
else
    # Fallback: no cpuset, run as before
    run_job playwright-jupyter job_playwright_jupyter_warm & PID_PW_JP=$!
fi
```

---

## Validation

1. Run with cpuset. Compare pw-jupyter timing + flakiness vs baseline.
2. Run stress test (5 consecutive runs). Compare timing variance.
3. Verify cgroup v2 is available in container with --privileged.

## Risks

- `--privileged` is a security concern for shared hosts (our CI is single-tenant, so OK).
- cgroup v2 may not be available in all Docker configurations.
- 4 cores for all other jobs may slow them down — monitor tail latency.
