#!/usr/bin/env bash
# ClusterLog installer / updater. Safe to re-run: it rebuilds and restarts,
# and never touches your data in ./data.
source "$(dirname "$0")/scripts/lib.sh"

port_free() { ! ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .; }

if [ ! -f .env ]; then
  PORT="${CLUSTERLOG_PORT:-8765}"
  while ! port_free "$PORT"; do PORT=$((PORT + 1)); done
  TZV=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo UTC)
  cat > .env <<ENV
CLUSTERLOG_PORT=$PORT
TZ=$TZV
PUID=${SUDO_UID:-$(id -u)}
PGID=${SUDO_GID:-$(id -g)}
ENV
  say "Created .env (port $PORT, timezone $TZV)"
  set -a; . ./.env; set +a
fi

mkdir -p data
say "Building and starting ClusterLog…"
compose up -d --build

say "Waiting for it to come up…"
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo
    say "ClusterLog is running."
    for ip in $(hostname -I 2>/dev/null); do
      case "$ip" in 172.*|*:*) continue ;; esac   # skip docker bridges / IPv6
      echo "    http://$ip:$PORT"
    done
    echo "    http://$(hostname):$PORT"
    echo
    echo "On your phone: open the address in Safari → Share → Add to Home Screen."
    exit 0
  fi
  sleep 1
done
die "It didn't answer on port $PORT. See logs with: docker compose logs clusterlog"
