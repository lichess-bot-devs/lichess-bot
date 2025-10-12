"""Remove files created when testing lichess-bot."""
import shutil
import os
from _pytest.config import ExitCode
from _pytest.main import Session


def pytest_sessionfinish(session: Session, exitstatus: int | ExitCode) -> None:  # noqa: ARG001
    """
    Remove files created when testing lichess-bot.

    The only exception is if running in a GitHub action, in which case we save the engines to the cache.
    """
    if os.path.exists("TEMP") and not os.getenv("GITHUB_ACTIONS"):
        shutil.rmtree("TEMP")
