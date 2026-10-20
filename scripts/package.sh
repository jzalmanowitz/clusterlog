#!/usr/bin/env bash
# Usage: scripts/package.sh [--with-data]
# Builds dist/clusterlog-<version>.tar.gz — copy it to another machine,
# extract, and run ./install.sh. With --with-data, your database comes along.
source "$(dirname "$0")/lib.sh"
VERSION=$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' app/main.py)
NAME="clusterlog-$VERSION"
[ "${1:-}" = "--with-data" ] && NAME="$NAME-with-data-$(date +%Y%m%d)"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/clusterlog" dist
tar --exclude=./data --exclude=./backups --exclude=./dist --exclude=./.env --exclude=./.git \
    --exclude='__pycache__' -cf - . | tar -C "$TMP/clusterlog" -xf -
if [ "${1:-}" = "--with-data" ]; then
  mkdir -p "$TMP/clusterlog/data"
  snapshot_db "$TMP/clusterlog/data/clusterlog.db"
fi
tar -C "$TMP" -czf "dist/$NAME.tar.gz" clusterlog
say "Package: dist/$NAME.tar.gz"
echo "On the new machine:  tar xzf $NAME.tar.gz && cd clusterlog && ./install.sh"
