import logging
import feedparser

from .config import PODCASTS, NUM_EPISODES, BASE_DIR, LLM_BACKEND, LLM_MODEL
from .rss import download_episode
from .transcribe import Transcriber
from .summarize import summarize

logger = logging.getLogger("podcast_pipeline.pipeline")


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

            logger.info("Transcribing %s", mp3.name)
            txt = transcriber.transcribe(mp3)

            logger.info("Summarizing %s", txt.name)
            summary = summarize(
                txt.read_text(encoding="utf-8"),
                backend=LLM_BACKEND,
                model=LLM_MODEL,
            )

            summary_path = txt.with_name(f"{txt.stem}_summary.txt")
            summary_path.write_text(summary, encoding="utf-8")
            logger.info("Summary written to %s", summary_path)

    logger.info("Pipeline finished")