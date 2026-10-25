"""Git handoff to the cloud routines: transcripts are committed to branch `data`.

DATA_DIR is a git worktree checked out on that branch. Each run pulls first, so
the VPS and the Windows PC can both publish without clobbering each other, and
writes state/heartbeat.json so a standby host can tell whether the primary is alive.
"""
import json
import logging
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("podcast_summarizer.publish")

LOCK_STALE_SECONDS = 6 * 3600


class LockHeld(RuntimeError):
    pass


@contextmanager
def file_lock(path: Path):
    """Cross-platform single-run lock (O_EXCL). Locks older than 6h count as stale."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS:
        logger.warning("Removing stale lock %s", path)
        path.unlink(missing_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise LockHeld(f"another ingest run holds {path}") from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class DataRepo:
    def __init__(self, root: Path, branch: str = "data", remote: str = "origin"):
        self.root = root
        self.branch = branch
        self.remote = remote

    def git(self, *args: str, check: bool = True) -> str:
        res = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if check and res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
        return res.stdout.strip()

    @property
    def heartbeat_path(self) -> Path:
        return self.root / "state" / "heartbeat.json"

    def pull(self) -> None:
        self.git("pull", "--rebase", "--autostash", self.remote, self.branch)

    def read_heartbeat(self) -> dict | None:
        try:
            return json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def write_heartbeat(self, host: str, role: str, new: int) -> None:
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.write_text(json.dumps({
            "host": host,
            "role": role,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "new_transcripts": new,
        }, indent=2), encoding="utf-8")

    def commit_and_push(self, message: str) -> bool:
        # -f: the main branch's .gitignore excludes transcripts; audio never goes in
        self.git(
            "add", "-f", "--", "episodes", "state",
            ":(exclude)*.mp3", ":(exclude)*.m4a", ":(exclude)*.part",
        )
        if not self.git("diff", "--cached", "--name-only"):
            return False
        self.git("commit", "-q", "-m", message)
        self.git("push", "-q", self.remote, f"HEAD:{self.branch}")
        return True


def primary_is_alive(heartbeat: dict | None, max_age_hours: float) -> bool:
    if not heartbeat or heartbeat.get("role") != "primary":
        return False
    try:
        at = datetime.fromisoformat(heartbeat["at"])
    except (KeyError, ValueError):
        return False
    return (datetime.now(timezone.utc) - at).total_seconds() < max_age_hours * 3600
