"""Browser window management for Buckaroo sessions.

On macOS: uses AppleScript with Chromium-based browsers (Chrome, Arc, Chromium).
On other platforms: falls back to webbrowser.open().

Set BUCKAROO_APP_MODE=1 for electron-light experience (Chrome --app mode
with a dedicated profile at ~/.buckaroo/chrome-profile).
"""

import logging
import os
import platform
import subprocess
import webbrowser

log = logging.getLogger("buckaroo.server.focus")

# Chromium-based browsers on macOS that share the same AppleScript tab/window API
_CHROMIUM_BROWSERS = [
    ("Google Chrome", "/Applications/Google Chrome.app"),
    ("Google Chrome Canary", "/Applications/Google Chrome Canary.app"),
    ("Chromium", "/Applications/Chromium.app"),
    ("Arc", "/Applications/Arc.app"),
]

_CHROME_BINARY = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_BUCKAROO_CHROME_PROFILE = os.path.join(
    os.path.expanduser("~"), ".buckaroo", "chrome-profile"
)


def _session_url(session_id: str, port: int) -> str:
    return f"http://localhost:{port}/s/{session_id}"


def _detect_chromium_browser() -> str | None:
    """Return the AppleScript name of the first available Chromium browser."""
    for name, app_path in _CHROMIUM_BROWSERS:
        if os.path.exists(app_path):
            return name
    return None


# ---------------------------------------------------------------------------
# Standard mode: AppleScript with Chromium browser
# ---------------------------------------------------------------------------


def _applescript_find_and_focus(browser: str, session_id: str, port: int) -> bool:
    """Find an existing tab by session URL, activate it and its window.

    Works even when the tab is buried behind other tabs or the browser is
    in the background.  Returns True if the tab was found.
    """
    url_fragment = f"localhost:{port}/s/{session_id}"
    script = f'''
    tell application "{browser}"
        repeat with w in windows
            set i to 0
            repeat with t in tabs of w
                set i to i + 1
                if URL of t contains "{url_fragment}" then
                    set active tab index of w to i
                    set index of w to 1
                    activate
                    return "found"
                end if
            end repeat
        end repeat
        return "not_found"
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        found = result.stdout.strip() == "found"
        log.debug("AppleScript find session=%s browser=%s → %s", session_id, browser, found)
        return found
    except Exception as e:
        log.debug("AppleScript find failed for %s: %s", browser, e)
        return False


def _applescript_create_window(browser: str, url: str) -> bool:
    """Create a new dedicated browser window and navigate to *url*."""
    script = f'''
    tell application "{browser}"
        make new window
        set URL of active tab of front window to "{url}"
        activate
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=5,
        )
        log.info("Created new %s window → %s", browser, url)
        return True
    except Exception as e:
        log.warning("AppleScript create-window failed (%s): %s", browser, e)
        return False


# ---------------------------------------------------------------------------
# App mode: Chrome --app with dedicated profile (electron-light)
# ---------------------------------------------------------------------------


def _open_chrome_app_mode(url: str) -> bool:
    """Launch Chrome in --app mode with a dedicated user-data-dir."""
    if not os.path.exists(_CHROME_BINARY):
        return False

    os.makedirs(_BUCKAROO_CHROME_PROFILE, exist_ok=True)
    try:
        subprocess.Popen(
            [
                _CHROME_BINARY,
                f"--app={url}",
                f"--user-data-dir={_BUCKAROO_CHROME_PROFILE}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("Opened Chrome app-mode window → %s", url)
        return True
    except Exception as e:
        log.warning("Chrome app-mode launch failed: %s", e)
        return False


def _app_mode_find_and_focus(session_id: str) -> bool:
    """Focus an app-mode window by matching the page title via System Events.

    App-mode Chrome windows run in a separate process from the user's normal
    Chrome, so we search by window title (which equals the <title> element)
    across all Chrome-like processes.
    """
    # The session page sets <title>Buckaroo — SESSION_ID</title>
    script = f'''
    tell application "System Events"
        repeat with p in (every process whose name contains "Google Chrome")
            repeat with w in windows of p
                if name of w contains "{session_id}" then
                    set frontmost of p to true
                    perform action "AXRaise" of w
                    return "found"
                end if
            end repeat
        end repeat
        return "not_found"
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        found = result.stdout.strip() == "found"
        log.debug("App-mode find session=%s → %s", session_id, found)
        return found
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_or_create_session_window(session_id: str, port: int) -> str:
    """Find and focus the existing browser window for *session_id*, or create one.

    Idempotent: calling this multiple times never creates duplicate windows.

    Returns a short status string describing what happened, e.g.:
      "focused existing Google Chrome window"
      "created new Google Chrome window"
      "opened in default browser"
      "skipped (non-macOS)"
    """
    if platform.system() != "Darwin":
        webbrowser.open(_session_url(session_id, port))
        status = "opened in default browser (non-macOS)"
        log.info(status)
        return status

    url = _session_url(session_id, port)
    app_mode = os.environ.get("BUCKAROO_APP_MODE", "").lower() in ("1", "true", "yes")

    if app_mode:
        if _app_mode_find_and_focus(session_id):
            status = "focused existing Chrome app-mode window"
            log.info(status)
            return status
        if _open_chrome_app_mode(url):
            status = "created new Chrome app-mode window"
            log.info(status)
            return status
        log.warning("App-mode failed, falling through to standard mode")

    # Standard mode: try each available Chromium browser
    browser = _detect_chromium_browser()
    if browser:
        if _applescript_find_and_focus(browser, session_id, port):
            status = f"focused existing {browser} window"
            log.info(status)
            return status
        if _applescript_create_window(browser, url):
            status = f"created new {browser} window"
            log.info(status)
            return status

    # Last resort: open in whatever the OS default browser is
    webbrowser.open(url)
    status = "opened in default browser (no Chromium found)"
    log.info(status)
    return status
