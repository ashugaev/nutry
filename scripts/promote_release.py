"""Promote validated source into an immutable production release, without secrets."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path
from source_snapshot import ROOT, snapshot


def promote(expected=None, bootstrap=False):
    releases=ROOT/'.releases'; releases.mkdir(exist_ok=True)
    if bootstrap:
        if (releases/'current').exists():
            raise RuntimeError('Production release already exists')
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        version='baseline-'+revision
        paths=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD','--','bot.py','config.py','services','web'],cwd=ROOT,text=True).splitlines()
    else:
        if expected!=snapshot() or (ROOT/'.data/dev/validated.sha').read_text().strip()!=expected:
            raise RuntimeError('Source must match the successfully tested DEV snapshot')
        version=expected
        paths=['bot.py','config.py']+[str(p.relative_to(ROOT)) for pattern in ('services/*.py','web/*') for p in ROOT.glob(pattern) if p.is_file()]
    release=releases/version
    if not release.exists():
        release.mkdir()
        for name in paths:
            target=release/name; target.parent.mkdir(parents=True,exist_ok=True)
            if bootstrap:
                target.write_bytes(subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT))
            else:
                shutil.copy2(ROOT/name,target)
        for name,target in (('.env',ROOT/'.env'),('.data',ROOT/'.data')):
            (release/name).symlink_to(target)
    if not bootstrap and snapshot()!=expected:
        raise RuntimeError('Source changed during promotion')
    # Dependency environment is independent from DEV pip installs.
    if not (ROOT/'.venv-prod').exists():
        shutil.copytree(ROOT/'.venv',ROOT/'.venv-prod',symlinks=True)
    temporary=releases/('next-'+str(os.getpid()))
    temporary.symlink_to(release)
    os.replace(temporary,releases/'current')
    print('Production release selected: '+version)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--expected'); parser.add_argument('--bootstrap',action='store_true')
    args=parser.parse_args()
    if not args.bootstrap and not args.expected: parser.error('--expected is required after DEV validation')
    promote(args.expected,args.bootstrap)
