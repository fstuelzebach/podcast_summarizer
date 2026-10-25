import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .config import Podcast, load_podcasts
from .keep_awake import keep_awake
from .notify import send_push
from .publish import DataRepo, LockHeld, file_lock, primary_is_alive
from .rss import (
    Episode, download_audio, episode_stem, fetch_feed, fetch_feed_transcript, write_meta,
)
from .transcribe import Transcriber

logger = logging.getLogger("podcast_summarizer.pipeline")

_DERIVED = re.compile(r"_(summary|sentiment|compare)$")


@dataclass
class IngestResult:
    new: list[str] = field(default_factory=list)          # "podcast · title"
    failures: list[str] = field(default_factory=list)
    whisper_count: int = 0
    skipped_reason: str | None = None
    runtime_min: float = 0.0


# ---------------------------------------------------------------------------
# ingest — fetch + transcribe + publish. No LLM: briefings are written by the
# Claude Code routines that read the published transcripts (see prompts/).
# ---------------------------------------------------------------------------

def _ingest_episode(pod: Podcast, ep: Episode, folder: Path, transcriber: Transcriber,
                    result: IngestResult) -> None:
    stem = episode_stem(pod.key, ep)
    txt = folder / f"{stem}.txt"
    meta = folder / f"{stem}.meta.json"

    if txt.exists():
        # Older runs wrote thinner metadata; refresh it so routines get the URL.
        if not meta.exists() or "episode_url" not in meta.read_text(encoding="utf-8"):
            write_meta(meta, pod.key, pod.house, ep, transcript_source="whisper:legacy")
        return

    text = fetch_feed_transcript(ep) if ep.transcripts else None
    if text:
        txt.write_text(text, encoding="utf-8")
        source = "feed"
    elif ep.audio_url:
        mp3 = download_audio(ep, folder / f"{stem}.mp3")
        logger.info("Transcribing %s", mp3.name)
        transcriber.transcribe(mp3)
        result.whisper_count += 1
        source = f"whisper:{transcriber.label}"
        if not config.KEEP_AUDIO:
            mp3.unlink(missing_ok=True)
    else:
        logger.warning("No audio or transcript: %s", ep.title)
        return

    write_meta(meta, pod.key, pod.house, ep, transcript_source=source)
    result.new.append(f"{pod.key} · {ep.title}")
    logger.info("New transcript (%s): %s", source, txt.name)


def _notify(result: IngestResult) -> None:
    host = config.HOST_NAME
    if result.failures:
        send_push(
            f"Podcast ingest: {len(result.failures)} failed ({host})",
            "\n".join(result.failures[:10]),
            priority="high", tags="warning",
        )
    if result.new:
        send_push(
            f"{len(result.new)} new podcast transcript(s)",
            "\n".join(result.new[:10]) + "\nBriefings follow with the 07:00 digest.",
            priority="low", tags="headphones",
        )
    if result.runtime_min > config.MAX_RUNTIME_MIN or result.whisper_count > config.MAX_BACKLOG:
        send_push(
            f"Podcast ingest heavy on {host}",
            f"Runtime {result.runtime_min:.0f} min, {result.whisper_count} Whisper transcriptions "
            f"(limits {config.MAX_RUNTIME_MIN:.0f} min / {config.MAX_BACKLOG}). "
            "Consider moving transcription to the Windows PC (HOST_ROLE=primary there).",
            priority="default", tags="hourglass",
        )


def ingest(podcasts: list[Podcast] | None = None) -> IngestResult:
    started = time.monotonic()
    result = IngestResult()
    repo = DataRepo(config.DATA_DIR, branch=config.DATA_BRANCH)

    try:
        with file_lock(config.LOCK_FILE), keep_awake():
            if config.PUBLISH:
                repo.pull()
            if config.HOST_ROLE == "standby" and primary_is_alive(
                repo.read_heartbeat(), config.STANDBY_AFTER_HOURS
            ):
                result.skipped_reason = "primary host is alive"
                logger.info("Standby: primary published recently — nothing to do")
                return result

            transcriber = Transcriber(config.WHISPER_MODEL, config.WHISPER_ENGINE)
            for pod in podcasts if podcasts is not None else load_podcasts():
                folder = config.BASE_DIR / pod.key
                folder.mkdir(parents=True, exist_ok=True)
                try:
                    episodes = fetch_feed(pod.url, pod.num_episodes)
                except Exception as e:  # noqa: BLE001
                    logger.exception("Feed failed podcast=%s", pod.key)
                    result.failures.append(f"{pod.key}: feed — {e}")
                    continue
                for ep in episodes:
                    try:
                        _ingest_episode(pod, ep, folder, transcriber, result)
                    except Exception as e:  # noqa: BLE001
                        logger.exception("Episode failed: %s", ep.title)
                        result.failures.append(f"{pod.key}: {ep.title} — {e}")

            result.runtime_min = (time.monotonic() - started) / 60
            if config.PUBLISH:
                repo.write_heartbeat(config.HOST_NAME, config.HOST_ROLE, len(result.new))
                msg = (f"ingest: {len(result.new)} new transcript(s) from {config.HOST_NAME}"
                       if result.new else f"heartbeat: {config.HOST_NAME}")
                if repo.commit_and_push(msg):
                    logger.info("Published to branch %s", config.DATA_BRANCH)
    except LockHeld as e:
        result.skipped_reason = str(e)
        logger.warning("Skipped: %s", e)
        return result
    except Exception as e:  # noqa: BLE001 — git/pull failures must still reach the phone
        logger.exception("Ingest aborted")
        result.failures.append(f"aborted — {e}")

    result.runtime_min = (time.monotonic() - started) / 60
    _notify(result)
    logger.info("Ingest done: %d new, %d failed, %.1f min",
                len(result.new), len(result.failures), result.runtime_min)
    return result


# ---------------------------------------------------------------------------
# summarize — optional local summaries (Ollama / Claude API), the old pipeline
# ---------------------------------------------------------------------------

def iter_transcripts(base: Path = None):
    base = base or config.BASE_DIR
    for txt in sorted(base.glob("*/*.txt")):
        if not _DERIVED.search(txt.stem) and not txt.stem.endswith(".txt"):
            yield txt


def _published(txt: Path) -> str:
    try:
        meta = json.loads(txt.with_suffix(".meta.json").read_text(encoding="utf-8"))
        return meta.get("published") or "unknown"
    except (FileNotFoundError, json.JSONDecodeError):
        return "unknown"


def summarize_pending() -> int:
    from .summarize import summarize

    done = 0
    for txt in iter_transcripts():
        if any(txt.parent.glob(f"{glob_escape(txt.stem)}*_summary.txt")):
            continue
        logger.info("Summarizing %s", txt.name)
        summary = summarize(txt.read_text(encoding="utf-8"),
                            backend=config.LLM_BACKEND, model=config.LLM_MODEL)
        out = txt.with_name(f"{txt.stem}_{_published(txt)}_summary.txt")
        out.write_text(summary, encoding="utf-8")
        done += 1
    return done


def glob_escape(s: str) -> str:
    return re.sub(r"([*?\[])", r"[\1]", s)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def status() -> str:
    repo = DataRepo(config.DATA_DIR, branch=config.DATA_BRANCH)
    lines = [
        f"host      {config.HOST_NAME} (role={config.HOST_ROLE}, publish={config.PUBLISH})",
        f"data dir  {config.DATA_DIR}",
        f"heartbeat {repo.read_heartbeat()}",
        "",
    ]
    for pod in load_podcasts(include_disabled=True):
        folder = config.BASE_DIR / pod.key
        txts = list(iter_transcripts(config.BASE_DIR)) if folder.exists() else []
        n = sum(1 for t in txts if t.parent == folder)
        flag = "on " if pod in load_podcasts() else "off"
        lines.append(f"[{flag}] {pod.key:<20} {n:>3} transcripts  ({pod.house})")
    return "\n".join(lines)
