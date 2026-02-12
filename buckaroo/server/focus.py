import platform
import subprocess


def focus_browser_tab(session_id: str, port: int):
    """Bring the browser tab for this session to the foreground (macOS only)."""
    if platform.system() != "Darwin":
        return

    url_fragment = f"localhost:{port}/s/{session_id}"
    script = f'''
    tell application "Google Chrome"
        activate
        repeat with w in windows
            set i to 0
            repeat with t in tabs of w
                set i to i + 1
                if URL of t contains "{url_fragment}" then
                    set active tab index of w to i
                    set index of w to 1
                    return
                end if
            end repeat
        end repeat
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass
