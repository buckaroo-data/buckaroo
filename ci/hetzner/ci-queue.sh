#!/bin/bash
# CI Job Queue — directory-based queue with flock for single-worker enforcement.
#
# Deploy to HOST at /opt/ci/ci-queue.sh, symlink to /usr/local/bin/ci-queue.
#
# Usage:
#   ci-queue push SHA BRANCH [ARGS...]   # Enqueue + auto-start worker
#   ci-queue status                       # Show running/pending/recent
#   ci-queue cancel                       # Kill current job
#   ci-queue clear                        # Remove all pending jobs
#   ci-queue log [SHA]                    # Tail active job's CI log
#   ci-queue repeat SHA BRANCH N          # Push same SHA N times
#   ci-queue worker                       # (internal) Run worker loop

set -uo pipefail

QUEUE_DIR=/opt/ci/queue
PENDING_DIR=$QUEUE_DIR/pending
ACTIVE_DIR=$QUEUE_DIR/active
DONE_DIR=$QUEUE_DIR/done
FAILED_DIR=$QUEUE_DIR/failed
WORKER_LOCK=$QUEUE_DIR/worker.lock
WORKER_PID=$QUEUE_DIR/worker.pid
WORKER_LOG=$QUEUE_DIR/worker.log
CONTAINER=${HETZNER_CONTAINER:-buckaroo-ci}

# ── Helpers ──────────────────────────────────────────────────────────────────

ensure_dirs() {
    mkdir -p "$PENDING_DIR" "$ACTIVE_DIR" "$DONE_DIR" "$FAILED_DIR"
}

ts() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

log() {
    echo "[$(date +'%H:%M:%S')] $*" | tee -a "$WORKER_LOG"
}

# Generate a sortable job filename: timestamp + random suffix
job_filename() {
    echo "$(date +%Y%m%d%H%M%S)-$$-$RANDOM.job"
}

# Read a field from a job file
job_field() {
    local file=$1 field=$2
    grep "^${field}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-
}

# Update/add a field in a job file
job_set() {
    local file=$1 field=$2 value=$3
    if grep -q "^${field}=" "$file" 2>/dev/null; then
        sed -i "s|^${field}=.*|${field}=${value}|" "$file"
    else
        echo "${field}=${value}" >> "$file"
    fi
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd_push() {
    local sha=${1:?usage: ci-queue push SHA BRANCH [ARGS...]}
    local branch=${2:?usage: ci-queue push SHA BRANCH [ARGS...]}
    shift 2
    local args="$*"

    ensure_dirs
    local jobfile="$PENDING_DIR/$(job_filename)"
    cat > "$jobfile" <<EOF
SHA=$sha
BRANCH=$branch
ARGS=$args
QUEUED_AT=$(ts)
STATUS=pending
EOF
    echo "Queued: $sha ($branch) → $(basename "$jobfile")"

    # Auto-start worker if not already running
    if ! _worker_alive; then
        nohup "$0" worker >> "$WORKER_LOG" 2>&1 &
        disown
        echo "Worker started (pid $!)"
    fi
}

cmd_status() {
    ensure_dirs

    # Active job
    local active_jobs
    active_jobs=$(ls "$ACTIVE_DIR"/*.job 2>/dev/null)
    if [[ -n "$active_jobs" ]]; then
        echo "RUNNING:"
        for f in $active_jobs; do
            local sha=$(job_field "$f" SHA)
            local branch=$(job_field "$f" BRANCH)
            local started=$(job_field "$f" STARTED_AT)
            echo "  $sha ($branch) started $started"
        done
    else
        echo "RUNNING: (none)"
    fi

    # Pending jobs
    local pending_jobs
    pending_jobs=$(ls "$PENDING_DIR"/*.job 2>/dev/null | sort)
    local pending_count=$(echo "$pending_jobs" | grep -c '.job$' 2>/dev/null || echo 0)
    echo ""
    echo "PENDING: $pending_count"
    if [[ -n "$pending_jobs" ]]; then
        for f in $pending_jobs; do
            local sha=$(job_field "$f" SHA)
            local branch=$(job_field "$f" BRANCH)
            echo "  $sha ($branch)"
        done
    fi

    # Recent completed (last 5)
    echo ""
    echo "RECENT:"
    local done_jobs
    done_jobs=$(ls -t "$DONE_DIR"/*.job "$FAILED_DIR"/*.job 2>/dev/null | head -5)
    if [[ -n "$done_jobs" ]]; then
        for f in $done_jobs; do
            local sha=$(job_field "$f" SHA)
            local status=$(job_field "$f" STATUS)
            local duration=$(job_field "$f" DURATION)
            local exit_code=$(job_field "$f" EXIT_CODE)
            echo "  $sha  $status  ${duration}s  exit=$exit_code"
        done
    else
        echo "  (none)"
    fi

    # Worker status
    echo ""
    if _worker_alive; then
        echo "Worker: running (pid $(cat "$WORKER_PID" 2>/dev/null))"
    else
        echo "Worker: stopped"
    fi
}

cmd_cancel() {
    local active_jobs
    active_jobs=$(ls "$ACTIVE_DIR"/*.job 2>/dev/null)
    if [[ -z "$active_jobs" ]]; then
        echo "No active job to cancel"
        return 0
    fi

    for f in $active_jobs; do
        local sha=$(job_field "$f" SHA)
        echo "Cancelling: $sha"
        # Kill the docker exec process for this SHA
        docker exec "$CONTAINER" pkill -f "run-ci.sh.*$sha" 2>/dev/null || true
        job_set "$f" STATUS "cancelled"
        job_set "$f" FINISHED_AT "$(ts)"
        mv "$f" "$FAILED_DIR/"
    done
    echo "Cancelled. Pending jobs will continue when worker restarts."
}

cmd_clear() {
    local count
    count=$(ls "$PENDING_DIR"/*.job 2>/dev/null | wc -l)
    rm -f "$PENDING_DIR"/*.job
    echo "Cleared $count pending jobs"
}

cmd_log() {
    local sha=${1:-}

    if [[ -n "$sha" ]]; then
        # Tail specific SHA's CI log
        local logfile="/opt/ci/logs/$sha/ci.log"
        if [[ -f "$logfile" ]]; then
            tail -f "$logfile"
        else
            echo "No log found: $logfile"
            return 1
        fi
    else
        # Find active job and tail its log
        local active_job
        active_job=$(ls "$ACTIVE_DIR"/*.job 2>/dev/null | head -1)
        if [[ -z "$active_job" ]]; then
            echo "No active job. Tailing worker log instead."
            tail -f "$WORKER_LOG"
            return
        fi
        sha=$(job_field "$active_job" SHA)
        local logfile="/opt/ci/logs/$sha/ci.log"
        echo "Tailing $sha ..."
        tail -f "$logfile"
    fi
}

cmd_repeat() {
    local sha=${1:?usage: ci-queue repeat SHA BRANCH N}
    local branch=${2:?usage: ci-queue repeat SHA BRANCH N}
    local n=${3:?usage: ci-queue repeat SHA BRANCH N}

    for ((i=1; i<=n; i++)); do
        cmd_push "$sha" "$branch"
    done
    echo "Queued $n runs of $sha"
}

# ── Worker ───────────────────────────────────────────────────────────────────

_worker_alive() {
    [[ -f "$WORKER_PID" ]] && kill -0 "$(cat "$WORKER_PID")" 2>/dev/null
}

cmd_worker() {
    ensure_dirs

    # flock for single-worker enforcement
    exec 9>"$WORKER_LOCK"
    if ! flock -n 9; then
        echo "Worker already running"
        return 0
    fi

    echo $$ > "$WORKER_PID"
    log "Worker started (pid $$)"

    # Recover orphaned jobs in active/ (from a crash)
    for f in "$ACTIVE_DIR"/*.job; do
        [[ -f "$f" ]] || continue
        local sha=$(job_field "$f" SHA)
        log "Recovering orphaned job: $sha → failed"
        job_set "$f" STATUS "failed"
        job_set "$f" FINISHED_AT "$(ts)"
        job_set "$f" EXIT_CODE "-1"
        mv "$f" "$FAILED_DIR/"
    done

    # Process queue
    while true; do
        local next
        next=$(ls "$PENDING_DIR"/*.job 2>/dev/null | sort | head -1)
        if [[ -z "$next" ]]; then
            log "Queue empty — worker exiting"
            break
        fi

        # Move to active
        mv "$next" "$ACTIVE_DIR/"
        local jobfile="$ACTIVE_DIR/$(basename "$next")"

        local sha=$(job_field "$jobfile" SHA)
        local branch=$(job_field "$jobfile" BRANCH)
        local args=$(job_field "$jobfile" ARGS)
        local start_ts
        start_ts=$(date +%s)

        job_set "$jobfile" STATUS "running"
        job_set "$jobfile" STARTED_AT "$(ts)"

        log "START $sha ($branch) args=[$args]"

        # Load env for docker exec
        local env_args=()
        if [[ -f /opt/ci/.env ]]; then
            while IFS='=' read -r key val; do
                [[ -z "$key" || "$key" == \#* ]] && continue
                env_args+=("-e" "${key}=${val}")
            done < /opt/ci/.env
        fi

        # Run CI
        local rc=0
        docker exec "${env_args[@]}" "$CONTAINER" \
            bash /opt/ci-runner/run-ci.sh "$sha" "$branch" $args \
            >> "/opt/ci/logs/$sha/ci.log" 2>&1 || rc=$?

        local end_ts
        end_ts=$(date +%s)
        local duration=$((end_ts - start_ts))

        job_set "$jobfile" FINISHED_AT "$(ts)"
        job_set "$jobfile" EXIT_CODE "$rc"
        job_set "$jobfile" DURATION "$duration"

        if [[ $rc -eq 0 ]]; then
            job_set "$jobfile" STATUS "passed"
            mv "$jobfile" "$DONE_DIR/"
            log "PASS  $sha  (${duration}s)"
        else
            job_set "$jobfile" STATUS "failed"
            mv "$jobfile" "$FAILED_DIR/"
            log "FAIL  $sha  (${duration}s, exit=$rc)"
        fi
    done

    rm -f "$WORKER_PID"
    # flock released automatically when fd 9 closes
}

# ── Dispatch ─────────────────────────────────────────────────────────────────

cmd=${1:-help}
shift 2>/dev/null || true

case "$cmd" in
    push)    cmd_push "$@" ;;
    status)  cmd_status ;;
    cancel)  cmd_cancel ;;
    clear)   cmd_clear ;;
    log)     cmd_log "$@" ;;
    repeat)  cmd_repeat "$@" ;;
    worker)  cmd_worker ;;
    help|--help|-h)
        echo "Usage: ci-queue <command> [args]"
        echo ""
        echo "Commands:"
        echo "  push SHA BRANCH [ARGS...]   Enqueue a CI run"
        echo "  status                       Show queue status"
        echo "  cancel                       Kill current job"
        echo "  clear                        Remove all pending jobs"
        echo "  log [SHA]                    Tail active job's CI log"
        echo "  repeat SHA BRANCH N          Push same SHA N times"
        echo "  worker                       (internal) Run worker loop"
        ;;
    *)
        echo "Unknown command: $cmd (try: ci-queue help)"
        exit 1
        ;;
esac
