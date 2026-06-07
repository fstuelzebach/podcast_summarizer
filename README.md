# Podcast Summarizer

Fetches the latest episodes from configured RSS feeds, transcribes them with [Whisper](https://github.com/openai/whisper), and produces a structured macro research summary using a local Ollama model or the Claude API.

---

## How it works

1. **RSS fetch** — pulls the N most recent episodes from each enabled podcast feed
2. **Download** — streams the MP3 and writes a `.meta.json` sidecar with title, publish date, and source URL
3. **Transcribe** — runs Whisper locally to produce a `.txt` transcript (cached; skipped on re-runs)
4. **Summarize** — sends the transcript (chunked at 8 000 chars) to an LLM and merges partials into a 4-section research note:
   - Executive Summary
   - Economic Mechanisms
   - Market Implications / Trade Ideas
   - Narrative

Output files land in `episodes/{podcast_name}/`.

---

## Requirements

- Python 3.10+
- [Whisper](https://github.com/openai/whisper): `pip install openai-whisper`
- [ffmpeg](https://ffmpeg.org/) on PATH (Whisper dependency)
- **Ollama backend** (default): [Ollama](https://ollama.com/) installed and running, e.g. `ollama pull llama3.2:3b`
- **Claude backend** (optional): `pip install anthropic` + an `ANTHROPIC_API_KEY` in `.env`

---

## Installation

```bash
git clone https://github.com/fstuelzebach/podcast_summarizer.git
cd podcast_summarizer
pip install -e .
cp .env.example .env   # then fill in your values
```

---

## Configuration

### Podcasts

Edit `podcast_summarizer/config.py` — uncomment feeds to enable them:

```python
PODCASTS = {
    "streetsignals": "https://omny.fm/shows/street-signals/playlists/podcast.rss",
    # "macrotradingfloor": "https://feeds.megaphone.fm/...",
    # "globaldatapod":     "https://feed.podbean.com/...",
}

NUM_EPISODES = 2   # how many recent episodes to process per podcast
```

### LLM backend

Set in `.env`:

```env
LLM_BACKEND=ollama          # "ollama" (local) or "claude" (API)
LLM_MODEL=llama3.2:3b       # optional model override; omit to use provider default
ANTHROPIC_API_KEY=sk-ant-…  # only required when LLM_BACKEND=claude
```

| Backend | Default model | Requires |
|---|---|---|
| `ollama` | `llama3.2:3b` | Ollama running locally |
| `claude` | `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` in `.env` |

---

## Running

```bash
# Python
python -m podcast_summarizer

# Windows one-click
run.bat
```

---

## Output structure

```
episodes/
└── streetsignals/
    ├── EpisodeTitle_streetsignals.mp3
    ├── EpisodeTitle_streetsignals.meta.json
    ├── EpisodeTitle_streetsignals.txt          ← transcript
    └── EpisodeTitle_streetsignals_2026-06-07_summary.txt
```

Re-running skips already-downloaded MP3s and already-transcribed episodes.

---

## Custom Ollama model

A pre-tuned analyst persona is included (`llama3_analyst.Modelfile`):

```bash
ollama create llama3_analyst -f llama3_analyst.Modelfile
```

Then set `LLM_MODEL=llama3_analyst` in `.env`.
