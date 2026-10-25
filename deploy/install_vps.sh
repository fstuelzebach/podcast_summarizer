#!/usr/bin/env bash
# One-time setup on the Hetzner VPS (same box as olymp-capital). Re-runnable.
#
#   curl -fsSL https://raw.githubusercontent.com/fstuelzebach/podcast_summarizer/main/deploy/install_vps.sh | bash
#   (or: git clone … && bash podcast_summarizer/deploy/install_vps.sh)
#
# What it does:
#   1. installs git + python venv support
#   2. clones the code (public) to ~/podcast_summarizer
#   3. creates a deploy key for the private data repo and waits until you add it on
#      GitHub (Settings → Deploy keys → "Allow write access")
#   4. clones the data repo to ~/financial_research_data
#   5. venv + pip install, writes .env if missing
#   6. cron: ingest at 03:00 and 15:00 server time (UTC on Hetzner by default) —
#      done well before the 07:00 Berlin digest, clear of olymp's 06:00 refresh
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/podcast_summarizer}"
DATA_DIR="${DATA_DIR:-$HOME/financial_research_data}"
CODE_REPO="https://github.com/fstuelzebach/podcast_summarizer.git"
DATA_REPO="git@github-frdata:fstuelzebach/financial_research_data.git"
KEY="$HOME/.ssh/financial_research_data_deploy"

echo "[1/6] packages"
if ! command -v git >/dev/null || ! python3 -c "import venv, ensurepip" 2>/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y -qq git python3-venv
fi

echo "[2/6] code → $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then git -C "$APP_DIR" pull -q --ff-only; else git clone -q "$CODE_REPO" "$APP_DIR"; fi

echo "[3/6] deploy key for the private data repo"
mkdir -p ~/.ssh && chmod 700 ~/.ssh
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "vps-financial-research-data" -f "$KEY"
if ! grep -q "Host github-frdata" ~/.ssh/config 2>/dev/null; then
  cat >> ~/.ssh/config <<CFG

Host github-frdata
  HostName github.com
  User git
  IdentityFile $KEY
  IdentitiesOnly yes
CFG
  chmod 600 ~/.ssh/config
fi
ssh-keyscan -q github.com >> ~/.ssh/known_hosts 2>/dev/null || true
until ssh -o BatchMode=yes -T github-frdata 2>&1 | grep -q "successfully authenticated"; do
  echo
  echo "Add this key at https://github.com/fstuelzebach/financial_research_data/settings/keys"
  echo "(title: hetzner-vps, tick 'Allow write access'):"
  echo
  cat "$KEY.pub"
  echo
  read -r -p "Press Enter once it is added… " _ </dev/tty
done

echo "[4/6] data → $DATA_DIR"
if [ -d "$DATA_DIR/.git" ]; then git -C "$DATA_DIR" pull -q --rebase; else git clone -q "$DATA_REPO" "$DATA_DIR"; fi
git -C "$DATA_DIR" config user.name  "podcast-ingest (vps)"
git -C "$DATA_DIR" config user.email "podcast-ingest@users.noreply.github.com"

echo "[5/6] venv + .env"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -e "$APP_DIR"
if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<ENV
DATA_DIR=$DATA_DIR
DATA_BRANCH=main
PUBLISH=1
HOST_ROLE=primary
HOST_NAME=vps
WHISPER_MODEL=small
LOG_FILE=$APP_DIR/logs/ingest.log
# same topic as olymp-capital (or a separate one)
NTFY_TOPIC=
ENV
  echo "    wrote $APP_DIR/.env — set NTFY_TOPIC there"
fi

echo "[6/6] cron"
LINE="0 3,15 * * * cd $APP_DIR && $APP_DIR/.venv/bin/python -m podcast_summarizer ingest >/dev/null 2>&1"
(crontab -l 2>/dev/null | grep -v "podcast_summarizer ingest" || true; echo "$LINE") | crontab -
crontab -l | grep podcast_summarizer

echo
echo "Done. First run (takes a while — downloads the Whisper model):"
echo "  cd $APP_DIR && .venv/bin/python -m podcast_summarizer ingest && .venv/bin/python -m podcast_summarizer status"
