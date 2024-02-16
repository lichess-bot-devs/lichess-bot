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
import importlib
import tarfile
import datetime
from multiprocessing import Manager
from queue import Queue
import test_bot.lichess
from lib import config
from lib.timer import Timer, to_seconds, seconds
from typing import Any, Optional
from lib.engine_wrapper import test_suffix
if "pytest" not in sys.modules:
    sys.exit(f"The script {os.path.basename(__file__)} should only be run by pytest.")
lichess_bot = importlib.import_module("lichess-bot")

platform = sys.platform
file_extension = ".exe" if platform == "win32" else ""
stockfish_path = f"./TEMP/sf{file_extension}"


def download_sf() -> None:
    """Download Stockfish 15."""
    if os.path.exists(stockfish_path):
        return

    windows_or_linux = "windows" if platform == "win32" else "ubuntu"
    sf_base = f"stockfish-{windows_or_linux}-x86-64-modern"
    archive_ext = "zip" if platform == "win32" else "tar"
    archive_link = f"https://github.com/official-stockfish/Stockfish/releases/download/sf_16/{sf_base}.{archive_ext}"

    response = requests.get(archive_link, allow_redirects=True)
    archive_name = f"./TEMP/sf_zip.{archive_ext}"
    with open(archive_name, "wb") as file:
        file.write(response.content)

    archive_open = zipfile.ZipFile if archive_ext == "zip" else tarfile.TarFile
    with archive_open(archive_name, "r") as archive_ref:
        archive_ref.extractall("./TEMP/")

    exe_ext = ".exe" if platform == "win32" else ""
    shutil.copyfile(f"./TEMP/stockfish/{sf_base}{exe_ext}", stockfish_path)

    if windows_or_linux == "ubuntu":
        st = os.stat(stockfish_path)
        os.chmod(stockfish_path, st.st_mode | stat.S_IEXEC)


def download_lc0() -> None:
    """Download Leela Chess Zero 0.29.0."""
    if os.path.exists("./TEMP/lc0.exe"):
        return
    response = requests.get("https://github.com/LeelaChessZero/lc0/releases/download/v0.29.0/lc0-v0.29.0-windows-cpu-dnnl.zip",
                            allow_redirects=True)
    with open("./TEMP/lc0_zip.zip", "wb") as file:
        file.write(response.content)
    with zipfile.ZipFile("./TEMP/lc0_zip.zip", "r") as zip_ref:
        zip_ref.extractall("./TEMP/")


def download_sjeng() -> None:
    """Download Sjeng."""
    if os.path.exists("./TEMP/sjeng.exe"):
        return
    response = requests.get("https://sjeng.org/ftp/Sjeng112.zip", allow_redirects=True)
    with open("./TEMP/sjeng_zip.zip", "wb") as file:
        file.write(response.content)
    with zipfile.ZipFile("./TEMP/sjeng_zip.zip", "r") as zip_ref:
        zip_ref.extractall("./TEMP/")
    shutil.copyfile("./TEMP/Release/Sjeng112.exe", "./TEMP/sjeng.exe")


os.makedirs("TEMP", exist_ok=True)
download_sf()
if platform == "win32":
    download_lc0()
    download_sjeng()
logging_level = lichess_bot.logging.DEBUG
testing_log_file_name = None
lichess_bot.logging_configurer(logging_level, testing_log_file_name, None, False)
lichess_bot.logger.info("Downloaded engines")


def lichess_org_simulator(opponent_path: str,
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

    engine = chess.engine.SimpleEngine.popen_uci(opponent_path)
    engine.configure({"Skill Level": 0, "Move Overhead": 1000, "Use NNUE": False}
                     if opponent_path == stockfish_path else {})

    while not board.is_game_over():
        if board.turn == chess.WHITE:
            if not board.move_stack:
                move = engine.play(board,
                                   chess.engine.Limit(time=1),
                                   ponder=False)
            else:
                move_timer = Timer()
                move = engine.play(board,
                                   chess.engine.Limit(white_clock=to_seconds(wtime - seconds(2.0)),
                                                      white_inc=to_seconds(increment),
                                                      black_clock=to_seconds(btime),
                                                      black_inc=to_seconds(increment)),
                                   ponder=False)
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


def run_bot(raw_config: dict[str, Any], logging_level: int, opponent_path: str = stockfish_path) -> bool:
    """
    Start lichess-bot test with a mocked version of the lichess.org site.

    :param raw_config: A dictionary of values to specify the engine to test. This engine will play as white.
    :param logging_level: The level of logging to use during the test. Usually logging.DEBUG.
    :param opponent_path: The path to the executable that will play the opponent. The opponent plays as black.
    """
    config.insert_default_values(raw_config)
    CONFIG = config.Configuration(raw_config)
    lichess_bot.logger.info(lichess_bot.intro())
    manager = Manager()
    board_queue: Queue[chess.Board] = manager.Queue()
    clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]] = manager.Queue()
    move_queue: Queue[Optional[chess.Move]] = manager.Queue()
    li = test_bot.lichess.Lichess(move_queue, board_queue, clock_queue)

    user_profile = li.get_profile()
    username = user_profile["username"]
    if user_profile.get("title") != "BOT":
        return False
    lichess_bot.logger.info(f"Welcome {username}!")
    lichess_bot.disable_restart()

    results: Queue[bool] = manager.Queue()
    thr = threading.Thread(target=lichess_org_simulator, args=[opponent_path, move_queue, board_queue, clock_queue, results])
    thr.start()
    lichess_bot.start(li, user_profile, CONFIG, logging_level, testing_log_file_name, None, one_game=True)

    result = results.get()
    results.task_done()

    results.join()
    board_queue.join()
    clock_queue.join()
    move_queue.join()

    thr.join()

    return result


@pytest.mark.timeout(150, method="thread")
def test_sf() -> None:
    """Test lichess-bot with Stockfish (UCI)."""
    if platform != "linux" and platform != "win32":
        assert True
        return
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "./TEMP/"
    CONFIG["engine"]["name"] = f"sf{file_extension}"
    CONFIG["engine"]["uci_options"]["Threads"] = 1
    CONFIG["pgn_directory"] = "TEMP/sf_game_record"
    win = run_bot(CONFIG, logging_level)
    lichess_bot.logger.info("Finished Testing SF")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_lc0() -> None:
    """Test lichess-bot with Leela Chess Zero (UCI)."""
    if platform != "win32":
        assert True
        return
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
    win = run_bot(CONFIG, logging_level)
    lichess_bot.logger.info("Finished Testing LC0")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_sjeng() -> None:
    """Test lichess-bot with Sjeng (XBoard)."""
    if platform != "win32":
        assert True
        return
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "./TEMP/"
    CONFIG["engine"]["working_dir"] = "./TEMP/"
    CONFIG["engine"]["protocol"] = "xboard"
    CONFIG["engine"]["name"] = "sjeng.exe"
    CONFIG["engine"]["ponder"] = False
    CONFIG["pgn_directory"] = "TEMP/sjeng_game_record"
    win = run_bot(CONFIG, logging_level)
    lichess_bot.logger.info("Finished Testing Sjeng")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_homemade() -> None:
    """Test lichess-bot with a homemade engine running Stockfish (Homemade)."""
    if platform != "linux" and platform != "win32":
        assert True
        return
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["name"] = f"Stockfish{test_suffix}"
    CONFIG["engine"]["protocol"] = "homemade"
    CONFIG["pgn_directory"] = "TEMP/homemade_game_record"
    win = run_bot(CONFIG, logging_level)
    lichess_bot.logger.info("Finished Testing Homemade")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(30, method="thread")
def test_buggy_engine() -> None:
    """Test lichess-bot with an engine that causes a timeout error within python-chess."""
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "test_bot"

    def engine_path(CONFIG: dict[str, Any]) -> str:
        dir: str = CONFIG["engine"]["dir"]
        name: str = CONFIG["engine"]["name"]
        return os.path.join(dir, name)

    if platform == "win32":
        CONFIG["engine"]["name"] = "buggy_engine.bat"
    else:
        CONFIG["engine"]["name"] = "buggy_engine"
        st = os.stat(engine_path(CONFIG))
        os.chmod(engine_path(CONFIG), st.st_mode | stat.S_IEXEC)
    CONFIG["engine"]["uci_options"] = {"go_commands": {"movetime": 100}}
    CONFIG["pgn_directory"] = "TEMP/bug_game_record"

    win = run_bot(CONFIG, logging_level, engine_path(CONFIG))
    lichess_bot.logger.info("Finished Testing buggy engine")
    assert win
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))
