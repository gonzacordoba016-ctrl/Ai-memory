import subprocess

try:
    GIT_HASH = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()
except Exception:
    GIT_HASH = "1"


def render_html_with_cache_busting(html: str) -> str:
    return html.replace("{GIT_HASH}", GIT_HASH)
