import logging
import feedparser

from .config import PODCASTS, NUM_EPISODES, BASE_DIR
from .rss import download_episode
from .transcribe import Transcriber
from .summarize import summarize_with_llama

logger = logging.getLogger("podcast_pipeline.pipeline")


def run_pipeline() -> None:
    logger.info("Starting podcast summarization pipeline")

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

            logger.info("Summarizing transcript %s", txt.name)
            summary = summarize_with_llama(txt.read_text(encoding="utf-8"))

            summary_path = txt.with_name(f"{txt.stem}_summary.txt")
            summary_path.write_text(summary, encoding="utf-8")

            logger.info("Summary written to %s", summary_path)

    logger.info("Pipeline finished successfully")
