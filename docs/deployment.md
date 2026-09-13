# Production and isolated development

Production is nutrition-bot.service, a systemd user service for alek following
DiaryBot's pattern. Linger is enabled: it survives logout, reboot and Spur closure.
Never stop or modify diary-bot.service.

## Environment boundary

| Resource | Production | DEV |
|---|---|---|
| Telegram bot | Configured production bot | Configured separate DEV bot |
| Configuration | .env | .env.dev |
| SQLite | Production DATABASE_PATH | .data/dev/nutrition.db |
| Notion | Dedicated production diary | Nutrition Bot DEV — test diary |
| Runtime | nutrition-bot.service | Spur sidecar bot |
| Code | .releases/current | Working checkout |
| Python | .venv-prod | .venv |
| Polling lock | .data/bot.lock | .data/dev/bot.lock |
| Loopback web port | 8765 | 8766 |
| Public HTTPS port | 8443 | 10000 |

Both runtimes may run concurrently. Never launch python bot.py alongside production.
DEV starts through scripts/run_dev.py. It loads .env.dev explicitly and fails
closed on matching bot IDs (including rotated tokens), aliased SQLite paths,
Notion IDs, web ports or URLs. Tests never change either operator's allowlist.
Credentials stay ignored by Git and mode 600. Never print tokens or signed URLs.

DEV provisioning already ran. scripts/bootstrap_dev.py --apply uses the existing
authorized Assistant account and BotFather. Do not rerun routinely or create more
bots/tables without a new request.

## Start and inspect

```bash
# DEV; production stays running:
"$SPUR_SESSION_TOOL_DIR/spur-sidecar" --name bot
spur service logs nutrition-bot-5f23 bot --sidecar --limit 30

systemctl --user status nutrition-bot.service
journalctl --user -u nutrition-bot.service -n 60 --no-pager
loginctl show-user alek -p Linger
```

Spur auto-start is disabled; start DEV explicitly for development/testing.
Its watcher reloads changed source and accepts a restart marker for persistence
tests. Stopping DEV affects only the DEV bot, not production's independent service.

## Mandatory update pipeline

Install requirements-live.txt in .venv, ffmpeg with flite, and playwright-cli.
Do not run concurrent live loops. The gate holds .data/reload.lock; meal tests
share .data/dev/live-tests.lock.

nutrition-bot-reload.timer checks every 15 seconds. Changed snapshots run
scripts/reload-if-changed.sh:

1. Run make test: offline compilation and unit tests.
2. Wait for the DEV sidecar to load the exact snapshot.
3. Test English/Russian buttons, /lang, per-account isolation and language saved
   across a DEV process restart.
4. In both languages test real commands, no-food rejection, formatted replies,
   fiber, same-ID reply corrections, text, label photo, album, voice and audio.
   Check SQLite, Notion synchronization and cleanup of each test's own records.
5. Verify real signed DEV Mini App launch, HTTPS, unauthorized denial and totals.
   Run mobile browser language/history/ranges/empty/error/auth/zoom/scroll checks.
6. Recheck source hash, mark it validated, copy product code to .releases/<hash>
   and atomically select .releases/current.
7. Restart production, wait for startup schema readiness, send only /help and
   /today, and verify unchanged diary. Check its real signed Mini App read-only.
8. Write .data/deployed.sha only when all gates pass.

Source, assets, requirements and tests affect the hash; docs and secrets do not.
Failed DEV checks leave production's release untouched. Missing DEV or external
provider failure blocks promotion, not the running production bot.
A failure after promotion is an unverified deployment requiring investigation;
there is no automatic rollback. Failed snapshots retry on change or explicit force.

```bash
journalctl --user -u nutrition-bot-reload.service -n 100 --no-pager
systemctl --user stop nutrition-bot-reload.timer  # planned maintenance
systemctl --user start nutrition-bot-reload.service  # test changed snapshot
bash scripts/reload-if-changed.sh --force  # retry after resolving a failure
systemctl --user enable --now nutrition-bot-reload.timer
```

Manual live tests use .env.dev by default. Only production_smoke.py and
live_mini_app_check.py --production target production, both read-only.
Never create synthetic meals or alter preferences in production tests.
Evidence goes to SPUR_SESSION_ARTIFACTS_DIR when supplied, otherwise
.data/dev/artifacts and the reload journal. Active systemd status alone is not
Telegram acceptance; verify actual replies and stable polling.

## Installation and recovery

Install deploy/ units under /home/alek/.config/systemd/user and run daemon-reload
after unit changes. Enable nutrition-bot.service and nutrition-bot-reload.timer.
New hosts need linger, configured HTTPS and credentials. Remote updates use the systemd timer below; no cron is needed.

scripts/promote_release.py --bootstrap initializes from committed HEAD only when
no release exists. Normal promotion requires the exact DEV-validated snapshot.
Releases link only to production .env and .data. Old releases permit planned code
rollback; reverting code does not reverse SQLite/Notion migrations.

.venv-prod is independent of .venv. DEV pip installs cannot alter production.
Dependency upgrades require a planned production-environment update and acceptance;
the timer does not install packages. Back up data before schema changes.

Production cleanup is never an automated test or deploy operation. Retain private
backups outside Git and require explicit operator authorization for deletion.

## Mini App HTTPS

The dashboard runs inside each bot process, bound to loopback. Separate Funnel
listeners publish it; never reset other listeners, including port 5700.

```bash
tailscale funnel --bg --https=8443 http://127.0.0.1:8765
tailscale funnel --bg --https=10000 http://127.0.0.1:8766
tailscale funnel status
```

Production: https://your-public-host.example:8443
DEV: https://your-public-host.example:10000

Background Funnel configuration persists with tailscaled. Disable only the intended
listener using its --https port with off. Verify public DNS/TLS, not just status.
This is single-host deployment dependent on Tailscale, not high availability.

API access requires fresh Telegram-signed initData and the allowlist before diary
reads. Language comes from the authenticated account's SQLite preference. Public
assets contain no diary data; access logs are disabled and responses are no-store.
Historical meal names are not translated when language changes.

Fiber migration adds a nullable SQLite column automatically. Notion uses numeric
Fiber; unknown remains unknown. Manual Notion operations must load the intended
environment explicitly: inherited shell NOTION_DATABASE_ID may belong to another
project. Never migrate or clean a table based on ambient shell values.

## GitHub main and merged PR deployment

The host tracks origin/main. nutrition-bot-update.timer fetches it every two
minutes; merging a PR and pushing directly to main follow the same path.
scripts/update_from_remote.py only fast-forwards a clean main checkout.
Dirty work, other branches and divergence are preserved. Fetch/merge errors
never stop production. A shared lock prevents pulls during a validation run.

After fetching, the updater requests the full DEV gate described above; it never
directly restarts production. Keep the independent DEV sidecar running for this
gate. Offline CI runs in GitHub without production secrets. Only trusted reviewed
code should enter main: deployment executes repository code on this host.

Dependency changes deliberately block automatic updates because production has
a separate environment. Plan that upgrade and rerun full acceptance. Changed
systemd unit files also require a manual install and daemon-reload.

Install deploy/nutrition-bot-update.service and .timer alongside the other units:

```bash
systemctl --user daemon-reload
systemctl --user enable --now nutrition-bot-update.timer
systemctl --user start nutrition-bot-update.service
journalctl --user -u nutrition-bot-update.service -n 30 --no-pager
```

The timer must not be used while intentionally maintaining another branch.
Public repository preparation excludes env files, sessions, databases and private
artifacts. Run gitleaks with redaction before publishing; never add live credentials
to GitHub Actions or expose a self-hosted workflow runner to untrusted PRs.
