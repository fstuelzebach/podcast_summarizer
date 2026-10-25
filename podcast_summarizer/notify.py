"""Phone push notifications via ntfy.sh (same pattern as olymp-capital).

The topic name is the only access control, so it lives in .env (NTFY_TOPIC),
never in the repo. Sending never fails the calling job.
"""
import logging
import urllib.request

from .config import NTFY_SERVER, NTFY_TOPIC

logger = logging.getLogger("podcast_summarizer.notify")


def send_push(title: str, body: str, *, priority: str = "default", tags: str = "") -> bool:
    if not NTFY_TOPIC:
        logger.info("NTFY_TOPIC not set — push skipped: %s", title)
        return False
    req = urllib.request.Request(
        f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        method="POST",
        headers={
            # HTTP headers must be latin-1
            "Title": title.encode("ascii", "replace").decode("ascii"),
            "Priority": priority,
            "Tags": tags,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        logger.warning("ntfy push failed (%s): %s", exc, title)
        return False
    logger.info("ntfy push sent: %s", title)
    return ok
