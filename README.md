# Nutrition Bot

Owner-only Telegram nutrition diary. Send dish text, photos, label photos, mixed photo albums, voice notes, or audio. The bot estimates calories and macros with OpenAI and stores every result in local SQLite. Notion mirroring is optional.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
make test
make run
```

Set `TELEGRAM_TOKEN`, `OPENAI_API_KEY`, and numeric `OWNER_USER_ID`. Access fails closed before downloads or provider calls. Defaults use `gpt-6-astra` for nutrition and `whisper-1` for transcription. Override models and paths through `.env`.

English is the default, even for Russian Telegram clients. `/start` offers language buttons; `/lang`, `/lang en` and `/lang ru` change the selection. SQLite persists it per account across restarts. Bot replies, new estimates, command menus and the Mini App follow that selection. Accounts share food records, not language preferences. Historical dish names are not translated retroactively. `RESPONSE_LANGUAGE` is only the standalone analyzer fallback; it does not override user preferences or the English default.

## Commands

`OWNER_USER_ID` remains required. `ALLOWED_USER_IDS` optionally adds comma-separated
positive Telegram user IDs. All allowed accounts share the same diary; only private
chats are accepted. An invalid allowlist prevents startup.

- `/start`: usage and English/Russian language picker
- `/help`: usage; `/lang`: change language
- `/log description`: explicitly log food; `/day` aliases `/today`
- `/today`: today's calories and macros
- `/recent`: last 10 entries
- `/correct ID description`: replace an estimate
- Reply to a saved or corrected bot message with text, voice, or a photo to correct that same entry. The current dish and nutrition are included as context. Reply links persist across restarts; earlier `Saved: #ID` bot messages also work.
- `/delete ID`: delete a local entry

## Notion

Set `NOTION_TOKEN` and `NOTION_DATABASE_ID` only for a dedicated database with these properties: `Name` (title), `Date` (date), `Calories`, `Protein`, `Carbs`, `Fat`, `Fiber` (number), and `Source` (select). A mirror failure never loses the local entry. Corrections update the linked page and deletes archive it when the entry was mirrored successfully.

Nutrition values are estimates and are not medical advice.
If no food or ingredients can be identified, the bot explains this without adding
an entry or overwriting an existing correction target. An explicitly identified
zero-calorie drink is still valid; an unidentified zero-calorie placeholder is not.

Production runs under `nutrition-bot.service`, independently of Spur sessions.
See [deployment and logs](docs/deployment.md). The development sidecar does not auto-start.
Successful Telegram polling requests are logged without message content or credentials.
The reload timer checks source changes every 15 seconds. It runs offline tests and
full English/Russian live flows in the isolated DEV sidecar before promoting an
immutable production release. Production acceptance uses read-only commands and
Mini App checks, never synthetic food; see deployment documentation.
OpenAI requests have a 60-second timeout and one retry. A local save remains successful
even if subsequent mirroring or message delivery fails.

## Live Telegram acceptance

With account-owner authorization, live scripts use Assistant's existing Telegram
session against the isolated DEV bot configured in `.env.dev`. They never change
the allowlist or write production meals. Install optional tooling from
`requirements-live.txt` and ffmpeg with flite. The automatic gate tests both
languages, persisted selection after a DEV restart, text, labels, albums, voice,
audio, reply edits, fiber, no-food rejection, SQLite and Notion cleanup, plus signed
Mini App access and mobile browser flows. Run only one live loop at a time.
Evidence goes to `$SPUR_SESSION_ARTIFACTS_DIR` when supplied, otherwise
`.data/dev/artifacts/`; the reload service journal records the complete gate.
# Telegram Mini App

Dietary fiber is tracked as `fiber_g` in grams per consumed portion, alongside
calories/macros. It appears in meal confirmations, `/today`, `/recent`, the
dashboard and Notion's numeric `Fiber` property. Unknown/legacy fiber is null,
displayed as a dash, never silently converted to a measured zero. Partial daily
totals show a lower bound and missing-record count. Reply to an old entry or use
`/correct` to re-estimate it; historical entries are not bulk-rewritten.

Before deploying to an existing Notion mirror, run
`.venv/bin/python scripts/ensure_notion_fiber.py --apply` to add only the numeric
`Fiber` property. It verifies the configured nutrition schema first. SQLite adds
its nullable column automatically on startup; local persistence is independent
of Notion availability.

The Mini App keeps a fixed touch scale, with normal page/chart scrolling and no
refresh button. Data reloads on opening, returning to the app and changing the
history period. Close and reopen the app to retry a failed request.

Saved and corrected meal messages use native Telegram HTML: bold dish name and
calories, a separate macro line, and italic notes when present. Generated text is
escaped. The repeated correction footer is omitted; replying still edits the entry.

Use the **Calories** chat-menu button, `/stats`, or the button below `/help`.
The read-only dashboard shows calories, macros and meals for today or a selected
day, plus 7/30/90-day history. Empty days are explicitly unlogged, not assumed fasting.
Both allowlisted accounts see the same diary. Corrections/deletions are reflected
on reopening or changing the history period. All values are estimates; no calorie goal is inferred.

`MINI_APP_URL` enables the dashboard and must be a publicly reachable HTTPS URL.
The bot serves it on loopback `MINI_APP_PORT` (default 8765); an HTTPS reverse proxy
is required. No diary data is embedded in public HTML. API access requires Telegram
signed `initData`, no older than one hour, and an allowlisted user. Reopen the app
when authorization expires. See [deployment](docs/deployment.md) for this host.

Every update requires offline and real flow acceptance; see the
[flow-testing skill](.agents/skills/flow-testing/SKILL.md). Install optional live
tooling with `.venv/bin/pip install -r requirements-live.txt`; media tests also use
`ffmpeg` with `flite`. Live tests never change the operator allowlist.
