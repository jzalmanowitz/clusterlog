#!/usr/bin/env bash
# Usage: scripts/restore.sh <clusterlog-backup-*.tar.gz | clusterlog.db>
# Replaces the current database (the old one is kept as data/clusterlog.db.before-restore-<stamp>).
source "$(dirname "$0")/lib.sh"
SRC="${1:-}"
[ -f "$SRC" ] || die "Usage: scripts/restore.sh <backup.tar.gz or .db file>"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
case "$SRC" in
  *.tar.gz|*.tgz) tar -C "$TMP" -xzf "$SRC"; DB="$TMP/clusterlog.db" ;;
  *) DB="$SRC" ;;
esac
[ -f "$DB" ] || die "No clusterlog.db inside $SRC"
read -r -p "Replace the current ClusterLog data with $SRC? [y/N] " ok
[ "$ok" = y ] || [ "$ok" = Y ] || exit 1
WAS_RUNNING=0; running && WAS_RUNNING=1
[ $WAS_RUNNING = 1 ] && compose stop
mkdir -p data
STAMP=$(date +%Y%m%d-%H%M%S)
[ -f data/clusterlog.db ] && mv data/clusterlog.db "data/clusterlog.db.before-restore-$STAMP"
rm -f data/clusterlog.db-wal data/clusterlog.db-shm
cp "$DB" data/clusterlog.db
if [ ! -f .env ] && [ -f "$TMP/env" ]; then cp "$TMP/env" .env; say "Restored .env from backup"; fi
[ $WAS_RUNNING = 1 ] && compose start
say "Restored. Previous database kept as data/clusterlog.db.before-restore-$STAMP"
