#!/usr/bin/env bash
# Stops and removes the ClusterLog container and image. Your data in ./data is kept.
source "$(dirname "$0")/lib.sh"
compose down --rmi local
say "ClusterLog stopped and removed. Data is still in $ROOT/data"
