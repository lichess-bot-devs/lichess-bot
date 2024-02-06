"""Remove files created when testing lichess-bot."""
import shutil
import os
from typing import Any


def pytest_configure(config: Any) -> None:
    """Set pytest flag, so we know that lichess-bot is being run under pytest."""
    from test_bot import test_options
    test_options._called_from_test["in_test"] = True


def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
    """Remove files created when testing lichess-bot."""
    if os.path.exists("TEMP") and not os.getenv("GITHUB_ACTIONS"):
        shutil.rmtree("TEMP")
    if os.path.exists("logs"):
        shutil.rmtree("logs")
