"""GitHub commit status API helpers. Port of status.sh."""
import json
import os
import urllib.request


def _github_status(state: str, sha: str, context: str, description: str, target_url: str) -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "buckaroo-data/buckaroo")
    if not token:
        print(f"[status] no GITHUB_TOKEN — skipping {state} for {context}")
        return
    url = f"https://api.github.com/repos/{repo}/statuses/{sha}"
    data = json.dumps({
        "state": state,
        "context": context,
        "description": description[:140],
        "target_url": target_url,
    }).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def status_pending(sha: str, context: str, description: str, url: str) -> None:
    _github_status("pending", sha, context, description, url)


def status_success(sha: str, context: str, description: str, url: str) -> None:
    _github_status("success", sha, context, description, url)


def status_failure(sha: str, context: str, description: str, url: str) -> None:
    _github_status("failure", sha, context, description, url)
