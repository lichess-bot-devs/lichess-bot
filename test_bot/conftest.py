"""Remove files created when testing lichess-bot."""
import shutil
import os
from typing import Any


def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
    """Remove files created when testing lichess-bot."""
    shutil.copyfile("correct_lichess.py", "lichess.py")
    os.remove("correct_lichess.py")
    if os.path.exists("TEMP") and not os.getenv("GITHUB_ACTIONS"):
        shutil.rmtree("TEMP")
    if os.path.exists("logs"):
        shutil.rmtree("logs")
