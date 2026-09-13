"""Stable hash for code, assets and offline/live tests; excludes credentials/data."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def snapshot(root=ROOT):
    files=[root/'Makefile',root/'bot.py',root/'config.py']
    for pattern in ('requirements*.txt','services/*.py','tests/*.py','scripts/*.py','scripts/*.sh','scripts/*.js','web/*'):
        files.extend(path for path in root.glob(pattern) if path.is_file())
    digest=hashlib.sha256()
    for path in sorted(set(files)):
        digest.update(str(path.relative_to(root)).encode()); digest.update(b'\0'); digest.update(path.read_bytes())
    return digest.hexdigest()


if __name__=='__main__': print(snapshot())
