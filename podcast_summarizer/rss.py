import re
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import feedparser
import requests

logger = logging.getLogger("podcast_summarizer.rss")


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def _parse_published(entry) -> str | None:
    """Extract ISO-8601 publish date from feed entry. Returns None if unavailable."""
    # feedparser normalizes to published_parsed (time.struct_time UTC)
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    # fallback: raw string
    if hasattr(entry, "published") and entry.published:
        return entry.published
    return None


def download_episode(podcast_name: str, entry, podcast_dir: Path) -> Path | None:
    mp3_url = None
    for link in getattr(entry, "links", []):
        if link.get("type", "").startswith("audio"):
            mp3_url = link["href"]
            break

    if not mp3_url:
        for enc in getattr(entry, "enclosures", []):
            if "audio" in enc.get("type", ""):
                mp3_url = enc.get("href") or enc.get("url")
                break

    if not mp3_url:
        return None

    safe_title = sanitize_filename(entry.title)
    mp3_path = podcast_dir / f"{safe_title}_{podcast_name}.mp3"

    if mp3_path.exists():
        logger.info("Already downloaded: %s", mp3_path.name)
    else:
        logger.info("Downloading %s", mp3_url)
        response = requests.get(mp3_url, stream=True, timeout=60)
        response.raise_for_status()
        with open(mp3_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    # Write sidecar metadata file with publish date
    published = _parse_published(entry)
    meta_path = podcast_dir / f"{safe_title}_{podcast_name}.meta.json"
    meta = {
        "title": entry.title,
        "podcast": podcast_name,
        "published": published,          # "YYYY-MM-DD" or None
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "mp3_url": mp3_url,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Metadata written to %s (published=%s)", meta_path.name, published)

    return mp3_path