"""
Buckaroo Hetzner CI webhook receiver.

Receives GitHub webhook events, validates HMAC-SHA256, runs CI via
`docker exec` into the warm buckaroo-ci sidecar container, and reports
commit status back to GitHub.

Run via gunicorn (see cloud-init.yml for the systemd service):
    gunicorn -w 1 -b 0.0.0.0:9000 webhook:app

Single worker is intentional: concurrency is handled internally with threads.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort

# ── Config ────────────────────────────────────────────────────────────────────

def _load_env(path: str = "/opt/ci/.env") -> dict:
    env = {}
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

_cfg = _load_env()

WEBHOOK_SECRET = _cfg.get("WEBHOOK_SECRET", os.environ.get("WEBHOOK_SECRET", ""))
GITHUB_TOKEN   = _cfg.get("GITHUB_TOKEN",   os.environ.get("GITHUB_TOKEN", ""))
GITHUB_REPO    = _cfg.get("GITHUB_REPO",    os.environ.get("GITHUB_REPO", ""))
SERVER_IP      = _cfg.get("HETZNER_SERVER_IP", os.environ.get("HETZNER_SERVER_IP", "localhost"))
LOGS_DIR       = Path("/opt/ci/logs")
LAST_SUCCESS   = Path("/opt/ci/last-success")
CONTAINER_NAME = "buckaroo-ci"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────

# branch_name → SHA of the currently running CI job (or recently started).
_branch_sha: dict[str, str] = {}
# Guard for _branch_sha mutations.
_branch_lock = threading.Lock()
# Maximum two concurrent CI runs (different branches).
_sem = threading.Semaphore(2)

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_signature(payload: bytes, sig_header: str) -> bool:
    if not WEBHOOK_SECRET:
        log.warning("WEBHOOK_SECRET not set — accepting all payloads (unsafe)")
        return True
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def _log_url(sha: str) -> str:
    return f"http://{SERVER_IP}:9000/logs/{sha}"


def _set_github_status(sha: str, state: str, description: str, url: str) -> None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        log.warning("GITHUB_TOKEN / GITHUB_REPO not set — skipping status update")
        return
    payload = {
        "state": state,
        "context": "ci/hetzner",
        "description": description[:140],
        "target_url": url,
    }
    try:
        subprocess.run(
            [
                "curl", "-sf", "-X", "POST",
                f"https://api.github.com/repos/{GITHUB_REPO}/statuses/{sha}",
                "-H", f"Authorization: token {GITHUB_TOKEN}",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(payload),
                "-o", "/dev/null",
            ],
            check=False, timeout=10,
        )
    except Exception as exc:
        log.error("Failed to set GitHub status: %s", exc)


def _cancel_previous(branch: str) -> None:
    """Best-effort: kill any running run-ci.sh for the previous SHA on this branch."""
    with _branch_lock:
        old_sha = _branch_sha.get(branch)
    if not old_sha:
        return
    log.info("Cancelling previous run for branch %s (sha %s)", branch, old_sha[:8])
    subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "pkill", "-f", f"run-ci.sh.*{old_sha}"],
        capture_output=True,
    )


def _run_ci(sha: str, branch: str) -> None:
    """Run CI for sha in a background thread. Acquires _sem to cap concurrency."""
    log_url = _log_url(sha)
    _set_github_status(sha, "pending", "Running CI...", log_url)

    _sem.acquire()
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "GITHUB_TOKEN": GITHUB_TOKEN,
            "GITHUB_REPO": GITHUB_REPO,
            "HETZNER_SERVER_IP": SERVER_IP,
        }
        log.info("Starting CI for %s @ %s", branch, sha[:8])
        proc = subprocess.Popen(
            [
                "docker", "exec",
                "-e", f"GITHUB_TOKEN={GITHUB_TOKEN}",
                "-e", f"GITHUB_REPO={GITHUB_REPO}",
                "-e", f"HETZNER_SERVER_IP={SERVER_IP}",
                CONTAINER_NAME,
                "bash", "/repo/ci/hetzner/run-ci.sh", sha, branch,
            ],
            env=env,
        )

        with _branch_lock:
            _branch_sha[branch] = sha

        proc.wait()
        rc = proc.returncode
        log.info("CI finished for %s @ %s: rc=%d", branch, sha[:8], rc)
        # run-ci.sh sets the final GitHub status itself.
        # We only intervene if it crashed unexpectedly (rc=-N = killed by signal).
        if rc < 0:
            _set_github_status(sha, "failure", f"CI process killed (signal {-rc})", log_url)
    except Exception as exc:
        log.exception("CI thread crashed for %s: %s", sha, exc)
        _set_github_status(sha, "failure", f"CI error: {exc}", log_url)
    finally:
        _sem.release()
        with _branch_lock:
            if _branch_sha.get(branch) == sha:
                _branch_sha.pop(branch, None)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/webhook")
def webhook():
    payload = request.get_data()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(payload, sig):
        log.warning("Invalid webhook signature")
        abort(401)

    event = request.headers.get("X-GitHub-Event", "")
    data = request.get_json(force=True)

    sha, branch = None, None

    if event == "push":
        sha    = data.get("after")
        branch = data.get("ref", "").removeprefix("refs/heads/")
        # Skip branch deletions (sha is all zeros).
        if sha and re.fullmatch(r"0+", sha):
            return jsonify({"status": "ignored", "reason": "branch deletion"})

    elif event == "pull_request":
        action = data.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            return jsonify({"status": "ignored", "reason": f"action={action}"})
        sha    = data["pull_request"]["head"]["sha"]
        branch = data["pull_request"]["head"]["ref"]

    if not sha or not branch:
        return jsonify({"status": "ignored", "reason": "unrecognised event"})

    _cancel_previous(branch)

    t = threading.Thread(target=_run_ci, args=(sha, branch), daemon=True)
    t.start()

    return jsonify({"status": "accepted", "sha": sha, "branch": branch})


@app.get("/health")
def health():
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
        capture_output=True, text=True,
    )
    container_up = result.stdout.strip() == "true"

    last_success_ts = None
    if LAST_SUCCESS.exists():
        last_success_ts = LAST_SUCCESS.stat().st_mtime

    status = "ok" if container_up else "degraded"
    return jsonify({
        "status": status,
        "container": container_up,
        "last_success": last_success_ts,
        "active_runs": list(_branch_sha.items()),
    })


@app.get("/logs/<sha>")
def log_index(sha: str):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        abort(400)
    sha_dir = LOGS_DIR / sha
    if not sha_dir.is_dir():
        abort(404)
    files = sorted(p.name for p in sha_dir.iterdir() if p.is_file())
    links = "".join(f'<li><a href="/logs/{sha}/{f}">{f}</a></li>' for f in files)
    return f"<ul>{links}</ul>", 200, {"Content-Type": "text/html"}


@app.get("/logs/<sha>/<filename>")
def log_file(sha: str, filename: str):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        abort(400)
    sha_dir = LOGS_DIR / sha
    if not sha_dir.is_dir():
        abort(404)
    # Prevent path traversal.
    if "/" in filename or filename.startswith("."):
        abort(400)
    return send_from_directory(sha_dir, filename, mimetype="text/plain")


# ── Systemd watchdog ──────────────────────────────────────────────────────────

def _sd_notify(state: str) -> None:
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(sock_path)
            s.sendall(state.encode())
    except Exception:
        pass


def _watchdog_loop() -> None:
    _sd_notify("READY=1")
    while True:
        _sd_notify("WATCHDOG=1")
        time.sleep(30)


threading.Thread(target=_watchdog_loop, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, debug=False)
