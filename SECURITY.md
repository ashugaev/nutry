# Security and public repository safety

This repository contains application code, not a public food diary. Live env files,
Telegram user sessions, SQLite databases, backups and evidence are private and
excluded from Git. Never upload them to issues, pull requests or workflow artifacts.

The Telegram bot accepts only allowlisted users in private chats. Mini App assets
are public, but diary APIs require fresh Telegram-signed initData and the allowlist.
Do not log bot tokens, signed launch URLs or request headers. Nutritional estimates
are sent to the configured OpenAI account; Notion mirroring is optional.

Development must use a separate bot, SQLite and Notion database. Synthetic live
tests never target production. GitHub CI runs offline on hosted runners without
production secrets. Do not use pull_request_target to execute contributor code.

Only trusted reviewed changes should reach main: the host fetches main and runs
its test/deploy scripts. Repository write access is therefore deployment authority.
Enable branch protection and secret scanning in GitHub where available. Scan the
commit history with gitleaks --redact before initial publication. If a secret ever
enters Git, revoke it first; deleting the current file does not remove Git history.

Report vulnerabilities privately to the repository owner. Do not attach personal
meal data or credentials to public reports. Deployment paths in example units are
host-specific and must be adapted by other operators.
