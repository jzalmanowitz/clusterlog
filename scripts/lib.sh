# Shared helpers for ClusterLog scripts. Sourced, not run.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1mError:\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is not installed. Debian guide: https://docs.docker.com/engine/install/debian/"
if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)   # tip: 'sudo usermod -aG docker $USER' then log out/in to skip sudo
fi
"${DOCKER[@]}" compose version >/dev/null 2>&1 || die "Docker Compose plugin missing: sudo apt install docker-compose-plugin"
compose() { "${DOCKER[@]}" compose "$@"; }

[ -f .env ] && { set -a; . ./.env; set +a; }
PORT="${CLUSTERLOG_PORT:-8765}"

running() { [ -n "$(compose ps --status running -q clusterlog 2>/dev/null)" ]; }

# Consistent copy of the live database -> $1 (works whether or not the app is running)
snapshot_db() {
  local dest="$1"
  if running; then
    local name
    name=$(compose exec -T clusterlog python -c "import main; print(main.make_backup('manual').name)")
    cp "data/backups/$name" "$dest"
  elif [ -f data/clusterlog.db ]; then
    python3 -I -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d)" \
      data/clusterlog.db "$dest"
  else
    die "No database found in ./data"
  fi
}
