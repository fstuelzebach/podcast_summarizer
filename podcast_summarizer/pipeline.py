import json
import logging
import feedparser

from .config import PODCASTS, NUM_EPISODES, BASE_DIR, LLM_BACKEND, LLM_MODEL
from .rss import download_episode
from .transcribe import Transcriber
from .summarize import summarize

logger = logging.getLogger("podcast_summarizer.pipeline")


def _read_published(mp3: "Path") -> str:
    """Read publish date from sidecar .meta.json. Returns 'unknown' if missing."""
    meta_path = mp3.with_suffix("").with_suffix(".meta.json")  # strips .mp3, adds .meta.json
    # handle double suffix: title_podcast.mp3 -> title_podcast.meta.json
    stem = mp3.stem  # e.g. "EpisodeTitle_macrotradingfloor"
    meta_path = mp3.parent / f"{stem}.meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("published") or "unknown"
    except (FileNotFoundError, json.JSONDecodeError):
        return "unknown"


def run_pipeline() -> None:
    logger.info("Starting pipeline backend=%s model=%s", LLM_BACKEND, LLM_MODEL)

    transcriber = Transcriber()

    for podcast_name, rss_url in PODCASTS.items():
        logger.info("Processing podcast=%s", podcast_name)

        feed = feedparser.parse(rss_url)
        podcast_dir = BASE_DIR / podcast_name
        podcast_dir.mkdir(exist_ok=True)

        for entry in feed.entries[:NUM_EPISODES]:
            logger.info("Processing episode title=%s", entry.title)

            mp3 = download_episode(podcast_name, entry, podcast_dir)
            if not mp3:
                logger.warning("Skipping episode (no audio): %s", entry.title)
                continue

            published = _read_published(mp3)
            logger.info("Episode published=%s", published)

            logger.info("Transcribing %s", mp3.name)
            txt = transcriber.transcribe(mp3)

            logger.info("Summarizing %s", txt.name)
            summary = summarize(
                txt.read_text(encoding="utf-8"),
                backend=LLM_BACKEND,
                model=LLM_MODEL,
            )

            # Summary filename includes publish date: EpisodeTitle_podcast_2026-03-15_summary.txt
            summary_path = txt.with_name(f"{txt.stem}_{published}_summary.txt")
            summary_path.write_text(summary, encoding="utf-8")
            logger.info("Summary written to %s", summary_path)

    logger.info("Pipeline finished")