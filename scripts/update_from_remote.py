"""Fast-forward a clean main checkout; production still requires the DEV gate."""
import fcntl
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sync(root=ROOT):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    if git('branch', '--show-current') != 'main':
        return 'skip: checkout is not main'
    if git('status', '--porcelain'):
        return 'skip: checkout has local changes'
    git('fetch', '--quiet', 'origin', 'main')
    if git('rev-parse', 'HEAD') == git('rev-parse', 'origin/main'):
        return 'unchanged'
    # Dependencies need a planned production environment upgrade, not a blind restart.
    changed = git('diff', '--name-only', 'HEAD', 'origin/main').splitlines()
    if any(name.startswith('requirements') and name.endswith('.txt') for name in changed):
        return 'blocked: dependency changes require a planned environment upgrade'
    git('merge', '--ff-only', 'origin/main')
    return 'updated'


def main():
    (ROOT / '.data').mkdir(exist_ok=True)
    with (ROOT / '.data/reload.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('skip: validation is running')
            return
        result = sync()
    print(result)
    if result == 'updated':
        subprocess.run(['systemctl', '--user', 'start', '--no-block',
                        'nutrition-bot-reload.service'], check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Git errors can contain credential-bearing remote URLs.
        print('Remote update failed: ' + type(exc).__name__)
        raise SystemExit(1) from None
