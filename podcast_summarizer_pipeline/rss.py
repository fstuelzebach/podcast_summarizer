import re
import logging
from pathlib import Path

import feedparser
import requests

logger = logging.getLogger("podcast_pipeline.rss")


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name)


def download_episode(podcast_name, entry, target_dir: Path) -> Path | None:
    safe_title = sanitize_filename(entry.title)
    filename = target_dir / f"{safe_title}_{podcast_name}.mp3"

    if filename.exists():
        logger.info("Audio already exists: %s", filename.name)
        return filename

    audio_url = None
    if entry.get("enclosures"):
        audio_url = entry.enclosures[0].href
    else:
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio"):
                audio_url = link.get("href")
                break

    if not audio_url:
        logger.warning("No audio URL found for episode=%s", entry.title)
        return None

    logger.info("Downloading audio: %s", entry.title)

    try:
        with requests.get(audio_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
    except Exception:
        logger.exception("Failed to download episode=%s", entry.title)
        return None

    logger.info("Saved audio to %s", filename)
    return filename
