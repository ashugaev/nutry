#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data/dev
exec 9>.data/dev/bot.lock
flock --nonblock 9 || exit 75
child=''
trap 'if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null || true; wait "$child" || true; fi; exit 0' TERM INT
while true; do
  version=$(.venv/bin/python scripts/source_snapshot.py)
  restart_request=$(test -f .data/dev/restart.request && cat .data/dev/restart.request || true)
  .venv/bin/python scripts/run_dev.py &
  child=$!
  while kill -0 "$child" 2>/dev/null; do
    sleep 2
    if [ "$(.venv/bin/python scripts/source_snapshot.py)" != "$version" ] || [ "$(test -f .data/dev/restart.request && cat .data/dev/restart.request || true)" != "$restart_request" ]; then
      kill -TERM "$child" 2>/dev/null || true
      break
    fi
  done
  wait "$child" || true
  child=''
  echo "DEV runtime restarting"
  sleep 2
done
