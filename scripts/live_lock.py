"""Serialize synthetic-meal tests across manual runs and the reload service."""
import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def live_lock():
    directory = Path(__file__).resolve().parents[1] / '.data/dev'
    directory.mkdir(parents=True,exist_ok=True)
    with (directory / 'live-tests.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another live flow is running; wait for its cleanup') from None
        yield
