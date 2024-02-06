"""Remove files created when testing lichess-bot."""
import shutil
import os
from typing import Any


def pytest_configure(config):
    import sys
    sys._called_from_test = True


def pytest_unconfigure(config):
    import sys
    del sys._called_from_test


def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
    """Remove files created when testing lichess-bot."""
    if os.path.exists("TEMP") and not os.getenv("GITHUB_ACTIONS"):
        shutil.rmtree("TEMP")
    if os.path.exists("logs"):
        shutil.rmtree("logs")
