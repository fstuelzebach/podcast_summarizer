from datetime import datetime, timezone
import json

from podcast_summarizer import config, pipeline
from podcast_summarizer.config import Podcast
from podcast_summarizer.rss import Episode


class FakeTranscriber:
    label = "fake:tiny"

    def __init__(self, *a):
        self.calls = 0

    def transcribe(self, mp3):
        self.calls += 1
        out = mp3.with_suffix(".txt")
        out.write_text("whisper text")
        return out


def _setup(monkeypatch, tmp_path, role="primary"):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path / "episodes")
    monkeypatch.setattr(config, "LOCK_FILE", tmp_path / "ingest.lock")
    monkeypatch.setattr(config, "PUBLISH", False)
    monkeypatch.setattr(config, "HOST_ROLE", role)
    monkeypatch.setattr(pipeline, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(pipeline, "send_push", lambda *a, **k: True)
    ep = Episode("Ep: One?", "2026-10-22", "https://a/1.mp3", "https://site/1", "g1", "1969", "Show")
    monkeypatch.setattr(pipeline, "fetch_feed", lambda url, n: [ep])
    monkeypatch.setattr(pipeline, "download_audio", lambda ep, dest: (dest.write_bytes(b"x"), dest)[1])


def test_ingest_transcribes_writes_meta_and_deletes_audio(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    res = pipeline.ingest([Podcast("pod", "u", "House", 1)])
    folder = tmp_path / "episodes" / "pod"
    assert res.new == ["pod · Ep: One?"] and not res.failures
    assert (folder / "Ep One_pod.txt").read_text() == "whisper text"
    assert not (folder / "Ep One_pod.mp3").exists()
    meta = json.loads((folder / "Ep One_pod.meta.json").read_text())
    assert meta["episode_url"] == "https://site/1" and meta["house"] == "House"
    assert meta["transcript_source"] == "whisper:fake:tiny"

    again = pipeline.ingest([Podcast("pod", "u", "House", 1)])
    assert again.new == []


def test_standby_skips_when_primary_alive(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, role="standby")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "heartbeat.json").write_text(json.dumps(
        {"role": "primary", "at": datetime.now(timezone.utc).isoformat()}))
    res = pipeline.ingest([Podcast("pod", "u", "House", 1)])
    assert res.skipped_reason == "primary host is alive"
    assert not (tmp_path / "episodes" / "pod").exists()


def test_iter_transcripts_skips_derived(tmp_path):
    d = tmp_path / "pod"
    d.mkdir()
    for n in ["A_pod.txt", "A_pod_summary.txt", "A_pod_2026-01-01_summary.txt", "A_pod_sentiment.txt"]:
        (d / n).write_text("x")
    assert [p.name for p in pipeline.iter_transcripts(tmp_path)] == ["A_pod.txt"]
