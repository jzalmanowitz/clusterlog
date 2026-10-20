#!/usr/bin/env bash
# Usage: scripts/backup.sh [output-dir]
# Writes clusterlog-backup-<stamp>.tar.gz containing a consistent copy of the
# database and your .env. Restore with scripts/restore.sh.
source "$(dirname "$0")/lib.sh"
OUT="${1:-backups}"
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M%S)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
snapshot_db "$TMP/clusterlog.db"
[ -f .env ] && cp .env "$TMP/env"
tar -C "$TMP" -czf "$OUT/clusterlog-backup-$STAMP.tar.gz" .
say "Backup written: $OUT/clusterlog-backup-$STAMP.tar.gz"
