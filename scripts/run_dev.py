"""Sidecar entry point: never use production credentials, data, port or lock."""
import logging
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.environments import dev_values
from source_snapshot import snapshot


def main():
    os.environ.update(dev_values(ROOT))
    version=snapshot()
    from config import load_settings
    from bot import build_application
    from telegram import Update
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    app=build_application(load_settings(None))
    initialize=app.post_init
    async def ready(application):
        await initialize(application)
        marker=ROOT/'.data/dev/running.sha'
        marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text(version)
        (ROOT/'.data/dev/pid').write_text(str(os.getpid()))
        logging.info('DEV runtime ready; production configuration untouched')
    app.post_init=ready
    app.run_polling(allowed_updates=Update.ALL_TYPES,timeout=10)


if __name__=='__main__': main()
