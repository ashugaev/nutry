#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$repo_root"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; skipping Codex project checks"
  exit 0
fi

python3 <<'PY'
from pathlib import Path
import tomllib

for path in sorted(Path(".codex").rglob("*.toml")):
    with path.open("rb") as handle:
        tomllib.load(handle)


def check_frontmatter(path: Path, expected_name: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{path}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SystemExit(f"{path}: unclosed YAML frontmatter")
    fields = {}
    for line in text[4:end].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise SystemExit(f"{path}: invalid frontmatter line: {line}")
        key, value = stripped.split(":", 1)
        fields[key.strip()] = value.strip().strip("\"'")
    if fields.get("name") != expected_name:
        raise SystemExit(f"{path}: name must be {expected_name}")
    if not fields.get("description"):
        raise SystemExit(f"{path}: description is required")


for tree in (Path(".agents"), Path(".claude")):
    for path in sorted((tree / "skills").glob("*/SKILL.md")):
        check_frontmatter(path, path.parent.name)
    for path in sorted((tree / "agents").glob("*.md")):
        check_frontmatter(path, path.stem)

print("Codex config and frontmatter OK")
PY

python3 -m py_compile bot.py config.py services/*.py tests/*.py
