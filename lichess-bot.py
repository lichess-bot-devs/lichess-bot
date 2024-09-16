"""Starting point for lichess-bot."""
import multiprocessing
import time
import logging
from lib.lichess_bot import should_restart, disable_restart, start_lichess_bot

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn')
    try:
        while should_restart():
            disable_restart()
            start_lichess_bot()
            time.sleep(10 if should_restart() else 0)
    except Exception:
        logger.exception("Quitting lichess-bot due to an error:")
