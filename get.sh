#!/usr/bin/env bash
# One-line install / update for ClusterLog on a Linux box with Docker:
#
#   curl -fsSL https://raw.githubusercontent.com/jzalmanowitz/clusterlog/main/get.sh | bash
#
# Downloads the app into ~/clusterlog (or $CLUSTERLOG_DIR) and runs ./install.sh.
# Re-running it updates the code; your data in <dir>/data and <dir>/.env is never touched.
# Options (environment variables): CLUSTERLOG_DIR, CLUSTERLOG_PORT, CLUSTERLOG_REF (branch or tag).
set -euo pipefail

REPO="${CLUSTERLOG_REPO:-https://github.com/jzalmanowitz/clusterlog}"
REF="${CLUSTERLOG_REF:-main}"
DIR="${CLUSTERLOG_DIR:-$HOME/clusterlog}"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1mError:\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is not installed. Debian guide: https://docs.docker.com/engine/install/debian/"

if [ -d "$DIR/.git" ]; then
  say "Updating $DIR"
  command -v git >/dev/null 2>&1 || die "git is needed to update $DIR (sudo apt install git)"
  git -C "$DIR" fetch --depth 1 origin "$REF"
  git -C "$DIR" checkout -q -B "$REF" FETCH_HEAD
elif command -v git >/dev/null 2>&1; then
  [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ] && die "$DIR exists and isn't a ClusterLog checkout — set CLUSTERLOG_DIR to another folder"
  say "Downloading ClusterLog into $DIR"
  git clone -q --depth 1 --branch "$REF" "$REPO.git" "$DIR"
else
  # no git: unpack a snapshot over the folder (data/ and .env aren't in it, so they survive)
  say "Downloading ClusterLog into $DIR (no git found, using a snapshot)"
  mkdir -p "$DIR"
  curl -fsSL "$REPO/archive/$REF.tar.gz" | tar -xz -C "$DIR" --strip-components=1
fi

cd "$DIR"
exec ./install.sh
