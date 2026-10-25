import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

REPO_DIR = Path(__file__).parent.parent
load_dotenv(REPO_DIR / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# DATA_DIR is the git checkout that holds transcripts. On the servers it is a
# worktree on branch `data` (see deploy/); locally it defaults to the repo itself.
DATA_DIR = Path(os.getenv("DATA_DIR") or REPO_DIR).expanduser().resolve()
BASE_DIR = DATA_DIR / "episodes"
BASE_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = DATA_DIR / "state"
SOURCES_FILE = Path(os.getenv("SOURCES_FILE") or REPO_DIR / "conf" / "sources.toml")
LOCK_FILE = REPO_DIR / "logs" / "ingest.lock"

# ---------------------------------------------------------------------------
# Hosts / publishing
# ---------------------------------------------------------------------------

HOST_ROLE = os.getenv("HOST_ROLE", "primary")            # primary | standby
HOST_NAME = os.getenv("HOST_NAME") or platform.node() or "host"
PUBLISH = os.getenv("PUBLISH", "0") == "1"               # commit + push transcripts
DATA_BRANCH = os.getenv("DATA_BRANCH", "data")
STANDBY_AFTER_HOURS = float(os.getenv("STANDBY_AFTER_HOURS", "24"))

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

WHISPER_ENGINE = os.getenv("WHISPER_ENGINE", "auto")     # auto | faster | openai
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
KEEP_AUDIO = os.getenv("KEEP_AUDIO", "0") == "1"

# Load warnings — when these trip, move transcription to the Windows PC
MAX_RUNTIME_MIN = float(os.getenv("MAX_RUNTIME_MIN", "90"))
MAX_BACKLOG = int(os.getenv("MAX_BACKLOG", "6"))

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")

# ---------------------------------------------------------------------------
# Optional local LLM summary (legacy `summarize` command)
# ---------------------------------------------------------------------------

LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")   # "ollama" | "claude"
LLM_MODEL = os.getenv("LLM_MODEL") or None
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


@dataclass(frozen=True)
class Podcast:
    key: str
    url: str
    house: str
    num_episodes: int


def load_podcasts(path: Path = SOURCES_FILE, include_disabled: bool = False) -> list[Podcast]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    default_n = data.get("defaults", {}).get("num_episodes", 3)
    out = []
    for key, cfg in data.get("podcasts", {}).items():
        if not include_disabled and not cfg.get("enabled", True):
            continue
        out.append(Podcast(
            key=key,
            url=cfg["url"],
            house=cfg.get("house", key),
            num_episodes=int(cfg.get("num_episodes", default_n)),
        ))
    return out
