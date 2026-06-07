import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent.parent / "episodes"
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Pipeline
NUM_EPISODES = 2
PODCASTS = {
    #"macrotradingfloor": "https://feeds.megaphone.fm/ALFINVESTMENTSTRATEGYBV2974145286",
    # "globaldatapod": "https://feed.podbean.com/globaldatapod/feed.xml",
    "streetsignals":     "https://omny.fm/shows/street-signals/playlists/podcast.rss",
    #"howardmarks":   "https://rss.art19.com/the-memo-by-howard-marks",
    #"saxomarketcall": "https://feed.podbean.com/saxostrats/feed.xml",
}

# LLM backend — switch here without touching other code
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")   # "ollama" | "claude"
LLM_MODEL   = os.getenv("LLM_MODEL", None)          # None = use provider default

# Anthropic (only needed if LLM_BACKEND=claude)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")