import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

logger = logging.getLogger("podcast_summarizer.rss")

USER_AGENT = "podcast-summarizer/0.2 (+https://github.com/fstuelzebach/podcast_summarizer)"
PODCAST_NS = "https://podcastindex.org/namespace/1.0"

# Best first: formats that convert to clean plain text most reliably
_TRANSCRIPT_PREFERENCE = [
    "text/plain", "text/vtt", "application/x-subrip", "application/srt",
    "application/json", "text/html",
]


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


# ---------------------------------------------------------------------------
# Feed parsing
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    title: str
    published: str | None          # YYYY-MM-DD
    audio_url: str | None
    episode_url: str | None        # web page of the episode, falls back to audio URL
    guid: str | None
    duration: str | None
    feed_title: str | None
    transcripts: list[tuple[str, str]] = field(default_factory=list)  # (url, mime)


def _parse_published(entry) -> str | None:
    if getattr(entry, "published_parsed", None):
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    return None


def _audio_url(entry) -> str | None:
    for link in getattr(entry, "links", []):
        if link.get("type", "").startswith("audio"):
            return link.get("href")
    for enc in getattr(entry, "enclosures", []):
        if "audio" in enc.get("type", ""):
            return enc.get("href") or enc.get("url")
    return None


def _transcript_tags(raw: bytes) -> dict[str, list[tuple[str, str]]]:
    """Map item guid (or title) → [(url, mime)] from <podcast:transcript> tags.

    feedparser drops the attributes of unknown namespaced empty elements, so the
    raw XML is read separately.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        tags = [
            (t.get("url"), (t.get("type") or "").lower())
            for t in item.findall(f"{{{PODCAST_NS}}}transcript")
            if t.get("url")
        ]
        if not tags:
            continue
        for key_el in ("guid", "title"):
            el = item.find(key_el)
            if el is not None and el.text:
                out[el.text.strip()] = tags
    return out


def fetch_feed(url: str, limit: int) -> list[Episode]:
    resp = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    transcripts = _transcript_tags(resp.content)
    feed_title = feed.feed.get("title")

    episodes = []
    for entry in feed.entries[:limit]:
        guid = entry.get("id")
        title = entry.get("title", "untitled").strip()
        audio = _audio_url(entry)
        episodes.append(Episode(
            title=title,
            published=_parse_published(entry),
            audio_url=audio,
            episode_url=entry.get("link") or audio,
            guid=guid,
            duration=entry.get("itunes_duration"),
            feed_title=feed_title,
            transcripts=transcripts.get(guid or "", []) or transcripts.get(title, []),
        ))
    return episodes


# ---------------------------------------------------------------------------
# Feed-provided transcripts
# ---------------------------------------------------------------------------

_TS_LINE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?[.,]\d{3}\s+-->\s+")


def _cues_to_text(body: str) -> str:
    """VTT/SRT → plain text: drop headers, cue numbers, timestamps, tags; join lines."""
    lines = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.isdigit() or _TS_LINE.match(s) or s.startswith("NOTE"):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        if lines and lines[-1] == s:  # rolling captions repeat lines
            continue
        lines.append(s)
    return " ".join(lines)


def _json_to_text(body: str) -> str:
    data = json.loads(body)
    segs = data.get("segments", []) if isinstance(data, dict) else []
    return " ".join(s.get("body", "").strip() for s in segs if s.get("body"))


def _html_to_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", body)
    text = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def transcript_to_text(body: str, mime: str) -> str:
    if "vtt" in mime or "srt" in mime or "subrip" in mime:
        return _cues_to_text(body)
    if "json" in mime:
        return _json_to_text(body)
    if "html" in mime:
        return _html_to_text(body)
    return body.strip()


def fetch_feed_transcript(ep: Episode) -> str | None:
    """Return the feed's own transcript as plain text, or None if unavailable."""
    ranked = sorted(
        ep.transcripts,
        key=lambda t: next((i for i, m in enumerate(_TRANSCRIPT_PREFERENCE) if m in t[1]), 99),
    )
    for url, mime in ranked:
        try:
            resp = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            text = transcript_to_text(resp.text, mime or resp.headers.get("content-type", ""))
            if len(text) > 500:
                return text
        except Exception as e:  # noqa: BLE001 — any failure just falls back to Whisper
            logger.warning("Feed transcript failed url=%s err=%s", url, e)
    return None


# ---------------------------------------------------------------------------
# Files on disk
# ---------------------------------------------------------------------------

def episode_stem(podcast_key: str, ep: Episode) -> str:
    return f"{sanitize_filename(ep.title)}_{podcast_key}"


def download_audio(ep: Episode, dest: Path) -> Path:
    if dest.exists():
        logger.info("Already downloaded: %s", dest.name)
        return dest
    logger.info("Downloading %s", ep.audio_url)
    tmp = dest.with_suffix(".part")
    with requests.get(ep.audio_url, stream=True, timeout=120, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    tmp.replace(dest)
    return dest


def write_meta(path: Path, podcast_key: str, house: str, ep: Episode, transcript_source: str) -> None:
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    meta = {
        **existing,
        "title": ep.title,
        "podcast": podcast_key,
        "house": house,
        "feed_title": ep.feed_title,
        "published": ep.published,
        "episode_url": ep.episode_url,
        "mp3_url": ep.audio_url,
        "guid": ep.guid,
        "duration": ep.duration,
        "transcript_source": transcript_source,   # feed | whisper:<model>
        "transcribed_at": existing.get("transcribed_at") or datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
