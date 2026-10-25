# Podcast Summarizer

Turns macro/markets podcasts into research in Notion, without anyone pressing a button.

- **Servers** (Hetzner VPS, Windows PC as standby) fetch new episodes and transcribe
  them: the feed's own transcript when there is one, otherwise
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on CPU. Transcripts go to
  the private repo `financial_research_data`.
- **Scheduled Claude Code routines** read those transcripts and write the research:
  a briefing per episode (and per newsletter under the Gmail label `Research`), a daily
  digest, a weekly Regime Synthesis and a monthly Client Pitch Brief. All of it is filed in the
  Notion *Resources* database, with pushes via ntfy and Gmail. The prompts live in the
  data repo under `prompts/`.

No Claude API key is needed: the writing happens in routines on the Claude subscription.

```
 VPS cron 03:00/15:00 UTC                    Claude Code routines (Europe/Berlin)
 (Windows "Podcast-Ingest" = standby)        ────────────────────────────────────
 ──────────────────────────────              daily 07:00   research-digest
 RSS ─► feed transcript? ─► faster-whisper     new transcripts ─► briefing ─► Notion
   │                            │              Gmail "Research"  ─► briefing ─► Notion
   ▼                            ▼              Daily Digest ─► Notion · ntfy · Gmail
 episodes/<podcast>/<title>_<podcast>.txt    Sat 09:00     research-regime ─► Notion …
                 + .meta.json (date, URL)    1st 09:00     research-pitch  ─► Notion …
   │
   ▼  git push ─► financial_research_data (private) ─► read by the routines
      + state/heartbeat.json (standby host + digest check it)
```

Dedup: every briefing stores the episode URL in Notion's `URL` property, and the
routine skips URLs that are already there.

---

## Commands

```bash
python -m podcast_summarizer ingest            # fetch + transcribe + publish
python -m podcast_summarizer ingest --only streetsignals
python -m podcast_summarizer status            # role, heartbeat, counts per podcast
python -m podcast_summarizer summarize         # optional: old local Ollama/Claude-API summaries
```

## Configuration

- **Podcasts**: `conf/sources.toml` in the data repo (template: `conf/sources.example.toml`) (`enabled`, `url`, `house`, `num_episodes`).
  `house` is how the prompts group sources ("all State Street = one house").
- **Runtime**: `.env`; see `.env.example`. The main switches:

| Var | VPS | Windows PC |
|---|---|---|
| `DATA_DIR` | `~/financial_research_data` | `D:\financial_research_data` |
| `PUBLISH` | `1` | `1` |
| `HOST_ROLE` | `primary` | `standby` |
| `WHISPER_MODEL` | `small` | `small` or `medium` |
| `NTFY_TOPIC` | your topic | your topic |

## Hosts

**VPS (primary).** `bash deploy/install_vps.sh` clones code and data, sets up a deploy
key (write access) for the data repo, a venv, `.env`, and the cron line.

**Windows PC (standby).** `.\deploy\setup_windows_task.ps1` (admin) registers
`Podcast-Ingest` (04:30 + 16:30, wakes the PC). As standby it exits within seconds while
the VPS heartbeat is fresh, and takes over if the VPS has been silent for 24 h.

**Moving the load to Windows.** When ingest takes more than `MAX_RUNTIME_MIN`, or needs
more than `MAX_BACKLOG` Whisper runs, you get an ntfy push. To switch, run
`setup_windows_task.ps1 -Primary` and set `HOST_ROLE=standby` on the VPS. No code
changes are needed.

## Routines

Set up with `/schedule` in Claude Code, on the repo `financial_research_data`, with the
Notion and Gmail connectors attached and `NTFY_TOPIC` set as an environment variable:

| Routine | Cron (Europe/Berlin) | Prompt |
|---|---|---|
| research-digest | `0 7 * * *` | `prompts/routines/digest.md` |
| research-regime | `0 9 * * 6` | `prompts/routines/regime.md` |
| research-pitch | `0 9 1 * *` | `prompts/routines/pitch.md` |

To change the next REGIME/PITCH run's parameters, drop `key: value` lines into
`prompts/overrides/regime.md` or `pitch.md` in the data repo.

## Install (development)

```bash
poetry install --with dev          # or: pip install -e .
pytest
```

`faster-whisper` is the default engine. It bundles its own audio decoding, so ffmpeg is
not needed. The old `openai-whisper` (PyTorch) is the optional extra
`pip install -e ".[openai-whisper]"`, with `WHISPER_ENGINE=openai`.
