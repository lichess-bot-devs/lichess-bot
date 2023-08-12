"""Test lichess-bot."""
import pytest
import zipfile
import requests
import time
import yaml
import chess
import chess.engine
import threading
import os
import sys
import stat
import shutil
import importlib
import config
from timer import Timer, to_seconds, seconds
from typing import Any
if __name__ == "__main__":
    sys.exit(f"The script {os.path.basename(__file__)} should only be run by pytest.")
shutil.copyfile("lichess.py", "correct_lichess.py")
shutil.copyfile("test_bot/lichess.py", "lichess.py")
lichess_bot = importlib.import_module("lichess-bot")

platform = sys.platform
file_extension = ".exe" if platform == "win32" else ""
stockfish_path = f"./TEMP/sf{file_extension}"


def download_sf() -> None:
    """Download Stockfish 15."""
    if os.path.exists(stockfish_path):
        return
    windows_or_linux = "win" if platform == "win32" else "linux"
    base_name = f"stockfish_15_{windows_or_linux}_x64"
    exec_name = "stockfish_15_x64"
    zip_link = f"https://files.stockfishchess.org/files/{base_name}.zip"
    response = requests.get(zip_link, allow_redirects=True)
    with open("./TEMP/sf_zip.zip", "wb") as file:
        file.write(response.content)
    with zipfile.ZipFile("./TEMP/sf_zip.zip", "r") as zip_ref:
        zip_ref.extractall("./TEMP/")
    shutil.copyfile(f"./TEMP/{base_name}/{exec_name}{file_extension}", stockfish_path)
    if windows_or_linux == "linux":
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


if not os.path.exists("TEMP"):
    os.mkdir("TEMP")
download_sf()
if platform == "win32":
    download_lc0()
    download_sjeng()
logging_level = lichess_bot.logging.DEBUG
lichess_bot.logging_configurer(logging_level, None, None, False)
lichess_bot.logger.info("Downloaded engines")


def thread_for_test() -> None:
    """Play the moves for the opponent of lichess-bot."""
    open("./logs/events.txt", "w").close()
    open("./logs/states.txt", "w").close()
    open("./logs/result.txt", "w").close()

    start_time = seconds(10)
    increment = seconds(0.1)

    board = chess.Board()
    wtime = start_time
    btime = start_time

    with open("./logs/states.txt", "w") as file:
        file.write(f"\n{to_seconds(wtime)},{to_seconds(btime)}")

    engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
    engine.configure({"Skill Level": 0, "Move Overhead": 1000, "Use NNUE": False})

    while not board.is_game_over():
        if len(board.move_stack) % 2 == 0:
            if not board.move_stack:
                move = engine.play(board,
                                   chess.engine.Limit(time=1),
                                   ponder=False)
            else:
                move_timer = Timer()
                move = engine.play(board,
                                   chess.engine.Limit(white_clock=to_seconds(wtime) - 2,
                                                      white_inc=to_seconds(increment)),
                                   ponder=False)
                wtime -= move_timer.time_since_reset()
                wtime += increment
            engine_move = move.move
            if engine_move is None:
                raise RuntimeError("Engine attempted to make null move.")
            board.push(engine_move)

            uci_move = engine_move.uci()
            with open("./logs/states.txt") as states:
                state_str = states.read()
            state = state_str.split("\n")
            state[0] += f" {uci_move}"
            state_str = "\n".join(state)
            with open("./logs/states.txt", "w") as file:
                file.write(state_str)

        else:  # lichess-bot move.
            move_timer = Timer()
            state2 = state_str
            moves_are_correct = False
            while state2 == state_str or not moves_are_correct:
                with open("./logs/states.txt") as states:
                    state2 = states.read()
                time.sleep(0.001)
                moves = state2.split("\n")[0]
                temp_board = chess.Board()
                moves_are_correct = True
                for move_str in moves.split():
                    try:
                        temp_board.push_uci(move_str)
                    except ValueError:
                        moves_are_correct = False
            with open("./logs/states.txt") as states:
                state2 = states.read()
            if len(board.move_stack) > 1:
                btime -= move_timer.time_since_reset()
                btime += increment
            move_str = state2.split("\n")[0].split(" ")[-1]
            board.push_uci(move_str)

        time.sleep(0.001)
        with open("./logs/states.txt") as states:
            state_str = states.read()
        state = state_str.split("\n")
        state[1] = f"{to_seconds(wtime)},{to_seconds(btime)}"
        state_str = "\n".join(state)
        with open("./logs/states.txt", "w") as file:
            file.write(state_str)

    with open("./logs/events.txt", "w") as file:
        file.write("end")
    engine.quit()
    outcome = board.outcome()
    win = outcome.winner == chess.BLACK if outcome else False
    with open("./logs/result.txt", "w") as file:
        file.write("1" if win else "0")


def run_bot(raw_config: dict[str, Any], logging_level: int) -> str:
    """Start lichess-bot."""
    config.insert_default_values(raw_config)
    CONFIG = config.Configuration(raw_config)
    lichess_bot.logger.info(lichess_bot.intro())
    li = lichess_bot.lichess.Lichess(CONFIG.token, CONFIG.url, lichess_bot.__version__)

    user_profile = li.get_profile()
    username = user_profile["username"]
    if user_profile.get("title") != "BOT":
        return "0"
    lichess_bot.logger.info(f"Welcome {username}!")
    lichess_bot.disable_restart()

    thr = threading.Thread(target=thread_for_test)
    thr.start()
    lichess_bot.start(li, user_profile, CONFIG, logging_level, None, None, one_game=True)
    thr.join()

    with open("./logs/result.txt") as file:
        data = file.read()
    return data


@pytest.mark.timeout(150, method="thread")
def test_sf() -> None:
    """Test lichess-bot with Stockfish (UCI)."""
    if platform != "linux" and platform != "win32":
        assert True
        return
    if os.path.exists("logs"):
        shutil.rmtree("logs")
    os.mkdir("logs")
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["dir"] = "./TEMP/"
    CONFIG["engine"]["name"] = f"sf{file_extension}"
    CONFIG["engine"]["uci_options"]["Threads"] = 1
    CONFIG["pgn_directory"] = "TEMP/sf_game_record"
    win = run_bot(CONFIG, logging_level)
    shutil.rmtree("logs")
    lichess_bot.logger.info("Finished Testing SF")
    assert win == "1"
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_lc0() -> None:
    """Test lichess-bot with Leela Chess Zero (UCI)."""
    if platform != "win32":
        assert True
        return
    if os.path.exists("logs"):
        shutil.rmtree("logs")
    os.mkdir("logs")
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
    shutil.rmtree("logs")
    lichess_bot.logger.info("Finished Testing LC0")
    assert win == "1"
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_sjeng() -> None:
    """Test lichess-bot with Sjeng (XBoard)."""
    if platform != "win32":
        assert True
        return
    if os.path.exists("logs"):
        shutil.rmtree("logs")
    os.mkdir("logs")
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
    shutil.rmtree("logs")
    lichess_bot.logger.info("Finished Testing Sjeng")
    assert win == "1"
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))


@pytest.mark.timeout(150, method="thread")
def test_homemade() -> None:
    """Test lichess-bot with a homemade engine running Stockfish (Homemade)."""
    if platform != "linux" and platform != "win32":
        assert True
        return
    with open("strategies.py") as file:
        original_strategies = file.read()

    with open("strategies.py", "a") as file:
        file.write(f"""
class Stockfish(ExampleEngine):
    def __init__(self, commands, options, stderr, draw_or_resign, **popen_args):
        super().__init__(commands, options, stderr, draw_or_resign, **popen_args)
        import chess
        self.engine = chess.engine.SimpleEngine.popen_uci('{stockfish_path}')

    def search(self, board, time_limit, *args):
        return self.engine.play(board, time_limit)
""")
    if os.path.exists("logs"):
        shutil.rmtree("logs")
    os.mkdir("logs")
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG["token"] = ""
    CONFIG["engine"]["name"] = "Stockfish"
    CONFIG["engine"]["protocol"] = "homemade"
    CONFIG["pgn_directory"] = "TEMP/homemade_game_record"
    win = run_bot(CONFIG, logging_level)
    shutil.rmtree("logs")
    with open("strategies.py", "w") as file:
        file.write(original_strategies)
    lichess_bot.logger.info("Finished Testing Homemade")
    assert win == "1"
    assert os.path.isfile(os.path.join(CONFIG["pgn_directory"],
                                       "bo vs b - zzzzzzzz.pgn"))
