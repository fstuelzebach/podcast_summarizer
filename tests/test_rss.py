import json

from podcast_summarizer.rss import _transcript_tags, transcript_to_text

FEED = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:podcast="https://podcastindex.org/namespace/1.0">
<channel><title>Show</title>
<item><title>Ep 1</title><guid>g1</guid>
  <podcast:transcript url="https://x/t1.vtt" type="text/vtt"/>
  <podcast:transcript url="https://x/t1.txt" type="text/plain"/>
</item>
<item><title>Ep 2</title><guid>g2</guid></item>
</channel></rss>"""


def test_transcript_tags_keyed_by_guid_and_title():
    tags = _transcript_tags(FEED)
    assert tags["g1"] == [("https://x/t1.vtt", "text/vtt"), ("https://x/t1.txt", "text/plain")]
    assert tags["Ep 1"] == tags["g1"]
    assert "g2" not in tags


def test_transcript_tags_bad_xml():
    assert _transcript_tags(b"<not xml") == {}


def test_vtt_to_text():
    vtt = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\n<v Tim>Hello markets\n\n2\n00:00:02.000 --> 00:00:04.000\nHello markets\nrates are up\n"
    assert transcript_to_text(vtt, "text/vtt") == "Hello markets rates are up"


def test_json_to_text():
    body = json.dumps({"segments": [{"body": "One."}, {"body": " Two."}]})
    assert transcript_to_text(body, "application/json") == "One. Two."


def test_html_to_text():
    assert transcript_to_text("<p>A &amp; B</p><script>x()</script>", "text/html") == "A & B"
