"""Test lichess-bot."""
import pytest
import zipfile
import requests
import yaml
import chess
import chess.engine
import threading
import os
import sys
import stat
import shutil
import tarfile
import datetime
import logging
from multiprocessing import Manager
from queue import Queue
import test_bot.lichess
from lib import config
from lib.timer import Timer, to_seconds, seconds
from typing import Optional
from lib.engine_wrapper import test_suffix
from lib.lichess_types import CONFIG_DICT_TYPE
if "pytest" not in sys.modules:
    sys.exit(f"The script {os.path.basename(__file__)} should only be run by pytest.")
from lib import lichess_bot

platform = sys.platform
archive_ext = "zip" if platform == "win32" else "tar"
file_extension = ".exe" if platform == "win32" else ""


def download_sf() -> None:
    """Download Stockfish 16."""
    stockfish_path = f"./TEMP/sf{file_extension}"
    if os.path.exists(stockfish_path):
        return

    windows_linux_mac = "windows" if platform == "win32" else ("macos" if platform == "darwin" else "ubuntu")
    sf_base = f"stockfish-{windows_linux_mac}-x86-64-modern"
    archive_link = f"https://github.com/official-stockfish/Stockfish/releases/download/sf_16/{sf_base}.{archive_ext}"

    response = requests.get(archive_link, allow_redirects=True)
    response.raise_for_status()
    archive_name = f"./TEMP/sf_zip.{archive_ext}"
    with open(archive_name, "wb") as file:
        file.write(response.content)

    if archive_ext == "zip":
        with zipfile.ZipFile(archive_name, "r") as archive_ref:
            archive_ref.extractall("./TEMP/")  # noqa: S202
    else:
        with tarfile.TarFile(archive_name, "r") as archive_ref:
            archive_ref.extractall("./TEMP/", filter="data")

    exe_ext = ".exe" if platform == "win32" else ""
    shutil.copyfile(f"./TEMP/stockfish/{sf_base}{exe_ext}", stockfish_path)

    if platform != "win32":
        st = os.stat(stockfish_path)
        os.chmod(stockfish_path, st.st_mode | stat.S_IEXEC)


def download_lc0() -> None:
    """Download Leela Chess Zero 0.29.0."""
    if os.path.exists("./TEMP/lc0.exe"):
        return

    response = requests.get("https://github.com/LeelaChessZero/lc0/releases/download/v0.29.0/lc0-v0.29.0-windows-cpu-dnnl.zip",
                            allow_redirects=True)
    response.raise_for_status()
    with open("./TEMP/lc0_zip.zip", "wb") as file:
        file.write(response.content)
    with zipfile.ZipFile("./TEMP/lc0_zip.zip", "r") as zip_ref:
        zip_ref.extractall("./TEMP/")  # noqa: S202


def download_arasan() -> None:
    """Download Arasan."""
    if os.path.exists(f"./TEMP/arasan{file_extension}"):
        return
    if platform == "win32":
        response = requests.get("https://arasanchess.org/arasan24.1.zip", allow_redirects=True)
    else:
        response = requests.get("https://arasanchess.org/arasan-linux-binaries-24.2.2.tar.gz", allow_redirects=True)
    response.raise_for_status()
    with open(f"./TEMP/arasan.{archive_ext}", "wb") as file:
        file.write(response.content)
    if archive_ext == "zip":
        with zipfile.ZipFile(f"./TEMP/arasan.{archive_ext}", "r") as archive_ref:
            archive_ref.extractall("./TEMP/")  # noqa: S202
    else:
        with tarfile.TarFile(f"./TEMP/arasan.{archive_ext}", "r") as archive_ref:
            archive_ref.extractall("./TEMP/", filter="data")
    shutil.copyfile(f"./TEMP/arasanx-64{file_extension}", f"./TEMP/arasan{file_extension}")
    if platform != "win32":
        st = os.stat(f"./TEMP/arasan{file_extension}")
        os.chmod(f"./TEMP/arasan{file_extension}", st.st_mode | stat.S_IEXEC)


os.makedirs("TEMP", exist_ok=True)
logging_level = logging.DEBUG
testing_log_file_name = None
lichess_bot.logging_configurer(logging_level, testing_log_file_name, True)
logger = logging.getLogger(__name__)


class TrivialEngine:
    """A trivial engine that should be trivial to beat."""

    def play(self, board: chess.Board, *_: object) -> chess.engine.PlayResult:
        """Choose the first legal move."""
        return chess.engine.PlayResult(next(iter(board.legal_moves)), None)

    def quit(self) -> None:
        """Do nothing."""


def lichess_org_simulator(opponent_path: Optional[str],
                          move_queue: Queue[Optional[chess.Move]],
                          board_queue: Queue[chess.Board],
                          clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]],
                          results: Queue[bool]) -> None:
    """
    Run a mocked version of the lichess.org server to provide an opponent for a test. This opponent always plays white.

    :param opponent_path: The path to the executable of the opponent. Usually Stockfish.
    :param move_queue: An interprocess queue that supplies the moves chosen by the bot being tested.
    :param board_queue: An interprocess queue where this function sends the updated board after choosing a move.
    :param clock_queue: An interprocess queue where this function sends the updated game clock after choosing a move.
    :param results: An interprocess queue where this function sends the result of the game to the testing function.
    """
    start_time = seconds(10)
    increment = seconds(0.1)

    board = chess.Board()
    wtime = start_time
    btime = start_time

    engine = chess.engine.SimpleEngine.popen_uci(opponent_path) if opponent_path else TrivialEngine()

    while not board.is_game_over():
        if board.turn == chess.WHITE:
            if not board.move_stack:
                move = engine.play(board, chess.engine.Limit(time=1))
            else:
                move_timer = Timer()
                move = engine.play(board,
                                   chess.engine.Limit(white_clock=to_seconds(wtime - seconds(2.0)),
                                                      white_inc=to_seconds(increment),
                                                      black_clock=to_seconds(btime),
                                                      black_inc=to_seconds(increment)))
                wtime -= move_timer.time_since_reset()
                wtime += increment
            engine_move = move.move
            if engine_move is None:
                raise RuntimeError("Engine attempted to make null move.")
            board.push(engine_move)
            board_queue.put(board)
            clock_queue.put((wtime, btime, increment))
        else:
            move_timer = Timer()
            while (bot_move := move_queue.get()) is None:
                board_queue.put(board)
                clock_queue.put((wtime, btime, increment))
                move_queue.task_done()
            board.push(bot_move)
            move_queue.task_done()
            if len(board.move_stack) > 2:
                btime -= move_timer.time_since_reset()
                btime += increment

    board_queue.put(board)
    clock_queue.put((wtime, btime, increment))
    engine.quit()
    outcome = board.outcome()
    results.put(outcome is not None and outcome.winner == chess.BLACK)


def run_bot(raw_config: CONFIG_DICT_TYPE, logging_level: int, opponent_path: Optional[str] = None) -> bool:
    """
    Start lichess-bot test with a mocked version of the lichess.org site.

    :param raw_config: A dictionary of values to specify the engine to test. This engine will play as white.
    :param logging_level: The level of logging to use during the test. Usually logging.DEBUG.
    :param opponent_path: The path to the executable that will play the opponent. The opponent plays as black.
    """
    config.insert_default_values(raw_config)
    CONFIG = config.Configuration(raw_config)
    logger.info(lichess_bot.intro())
    manager = Manager()
    board_queue: Queue[chess.Board] = manager.Queue()
    clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]] = manager.Queue()
    move_queue: Queue[Optional[chess.Move]] = manager.Queue()
    li = test_bot.lichess.Lichess(move_queue, board_queue, clock_queue)

    user_profile = li.get_profile()
    username = user_profile["username"]
    if user_profile.get("title") != "BOT":
        return False
    logger.info(f"Welcome {username}!")
    lichess_bot.disable_restart()

    results: Queue[bool] = manager.Queue()
    thr = threading.Thread(target=lichess_org_simulator, args=[opponent_path, move_queue, board_queue, clock_queue, results])
    thr.start()
    lichess_bot.start(li, user_profile, CONFIG, logging_level, testing_log_file_name, True, one_game=True)

    result = results.get()
    results.task_done()

    results.join()
    board_queue.join()
    clock_queue.join()
    move_queue.join()

    thr.join()

    return result


@pytest.mark.timeout(180, method="thread")
def test_sf() -> None:
    """Test lichess-bot with Stockfish (UCI)."""
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "./TEMP/"
    CONFIG["engine"]["name"] = f"sf{file_extension}"
    CONFIG["engine"]["uci_options"]["Threads"] = 1
    CONFIG["pgn_directory"] = "TEMP/sf_game_record"
    logger.info("Downloading Stockfish")
    try:
        download_sf()
    except Exception:
        logger.exception("Could not download the Stockfish chess engine")
        pytest.skip("Could not download the Stockfish chess engine")
    win = run_bot(CONFIG, logging_level)
    logger.info("Finished Testing SF")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(180, method="thread")
def test_lc0() -> None:
    """Test lichess-bot with Leela Chess Zero (UCI)."""
    if platform != "win32":
        pytest.skip("Platform must be Windows.")
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "./TEMP/"
    CONFIG["engine"]["working_dir"] = "./TEMP/"
    CONFIG["engine"]["name"] = "lc0.exe"
    CONFIG["engine"]["uci_options"]["Threads"] = 1
    CONFIG["engine"]["uci_options"].pop("Hash", None)
    CONFIG["engine"]["uci_options"].pop("Move Overhead", None)
    CONFIG["pgn_directory"] = "TEMP/lc0_game_record"
    logger.info("Downloading LC0")
    try:
        download_lc0()
    except Exception:
        logger.exception("Could not download the LC0 chess engine")
        pytest.skip("Could not download the LC0 chess engine")
    win = run_bot(CONFIG, logging_level)
    logger.info("Finished Testing LC0")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_arasan() -> None:
    """Test lichess-bot with Arasan (XBoard)."""
    if platform not in ("linux", "win32"):
        pytest.skip("Platform must be Windows or Linux.")
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "./TEMP/"
    CONFIG["engine"]["working_dir"] = "./TEMP/"
    CONFIG["engine"]["protocol"] = "xboard"
    CONFIG["engine"]["name"] = f"arasan{file_extension}"
    CONFIG["engine"]["ponder"] = False
    CONFIG["pgn_directory"] = "TEMP/arasan_game_record"
    logger.info("Downloading Arasan")
    try:
        download_arasan()
    except Exception:
        logger.exception("Could not download the Arasan chess engine")
        pytest.skip("Could not download the Arasan chess engine")
    win = run_bot(CONFIG, logging_level)
    logger.info("Finished Testing Arasan")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(180, method="thread")
def test_homemade() -> None:
    """Test lichess-bot with a homemade engine running Stockfish (Homemade)."""
    try:
        download_sf()
    except Exception:
        logger.exception("Could not download the Stockfish chess engine")
        pytest.skip("Could not download the Stockfish chess engine")

    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["name"] = f"Stockfish{test_suffix}"
    CONFIG["engine"]["protocol"] = "homemade"
    CONFIG["pgn_directory"] = "TEMP/homemade_game_record"
    win = run_bot(CONFIG, logging_level)
    logger.info("Finished Testing Homemade")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(60, method="thread")
def test_buggy_engine() -> None:
    """Test lichess-bot with an engine that causes a timeout error within python-chess."""
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "test_bot"

    def engine_path(CONFIG: CONFIG_DICT_TYPE) -> str:
        directory: str = CONFIG["engine"]["dir"]
        name: str = CONFIG["engine"]["name"].removesuffix(".py")
        path = os.path.join(directory, name)
        if platform == "win32":
            path += ".bat"
        else:
            if platform == "darwin":
                path += "_macos"
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        return path

    CONFIG["engine"]["name"] = "buggy_engine.py"
    CONFIG["engine"]["interpreter"] = "python" if platform == "win32" else "python3"
    CONFIG["engine"]["uci_options"] = {"go_commands": {"movetime": 100}}
    CONFIG["pgn_directory"] = "TEMP/bug_game_record"

    win = run_bot(CONFIG, logging_level, engine_path(CONFIG))
    logger.info("Finished Testing buggy engine")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))
