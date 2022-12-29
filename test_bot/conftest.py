import shutil
import os
from typing import Any


def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
    shutil.copyfile("correct_lichess.py", "lichess.py")
    os.remove("correct_lichess.py")
    if os.path.exists("TEMP"):
        shutil.rmtree("TEMP")
    if os.path.exists("logs"):
        shutil.rmtree("logs")
