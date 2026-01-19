from pathlib import Path

# RSS feeds to ingest
PODCASTS = {
    "macrotradingfloor": "https://feeds.megaphone.fm/ALFINVESTMENTSTRATEGYBV2974145286",
    # "globaldatapod": "https://feed.podbean.com/globaldatapod/feed.xml",
    # "streetsignals": "https://www.omnycontent.com/d/playlist/...",
}

# How many recent episodes per podcast
NUM_EPISODES = 3

# Where all audio + text artifacts live
BASE_DIR = Path("episodes")
BASE_DIR.mkdir(parents=True, exist_ok=True)
