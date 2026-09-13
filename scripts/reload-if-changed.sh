#!/usr/bin/env bash
# Test DEV first; only then promote an immutable production release.
set -euo pipefail
cd "$(dirname "$0")/.."
systemctl --user is-active --quiet nutrition-bot.service || exit 0
mkdir -p .data/dev
exec 9>.data/reload.lock
flock --nonblock 9 || exit 0
current=$(.venv/bin/python scripts/source_snapshot.py)
if [ "${1:-}" != '--force' ] && [ -f .data/reload-attempt.sha ] && [ "$(< .data/reload-attempt.sha)" = "$current" ]; then
  exit 0
fi
fail() {
  printf '%s\n' "$current" > .data/reload-attempt.sha
  echo "Validation failed: $1. Inspect DEV logs; no test meals were sent to production." >&2
  exit 1
}
make test || fail offline
for attempt in {1..60}; do
  if [ -f .data/dev/running.sha ] && [ "$(< .data/dev/running.sha)" = "$current" ]; then break; fi
  sleep 2
done
[ -f .data/dev/running.sha ] && [ "$(< .data/dev/running.sha)" = "$current" ] || fail 'DEV sidecar not on current source'
.venv/bin/python scripts/live_language_check.py --run-live --restart-check || fail languages
.venv/bin/python scripts/live_reply_check.py --run-live || fail 'English reply flow'
.venv/bin/python scripts/live_telegram_check.py --run-live || fail 'English media flow'
.venv/bin/python scripts/live_language_check.py --run-live --russian || fail 'Russian selection'
.venv/bin/python scripts/live_reply_check.py --run-live || fail 'Russian reply flow'
.venv/bin/python scripts/live_telegram_check.py --run-live || fail 'Russian media flow'
.venv/bin/python scripts/live_mini_app_check.py --run-live || fail 'DEV Mini App'
browser=/home/alek/.local/bin/playwright-cli
"$browser" -s=nutrition-gate open http://127.0.0.1:8766 --mobile || fail 'browser startup'
if ! "$browser" -s=nutrition-gate run-code --filename=scripts/browser_check.js; then
  "$browser" -s=nutrition-gate close || true
  fail 'browser flows'
fi
"$browser" -s=nutrition-gate close
[ "$(.venv/bin/python scripts/source_snapshot.py)" = "$current" ] || fail 'source changed during DEV verification'
printf '%s\n' "$current" > .data/dev/validated.sha
.venv/bin/python scripts/promote_release.py --expected "$current" || fail promotion
systemctl --user restart nutrition-bot.service
.venv/bin/python scripts/production_smoke.py --run-live || fail 'production read-only commands'
.venv/bin/python scripts/live_mini_app_check.py --run-live --production || fail 'production read-only Mini App'
printf '%s\n' "$current" > .data/reload-attempt.sha
printf '%s\n' "$current" > .data/deployed.sha
echo 'Both-language DEV flows passed; production release verified without synthetic production entries'
