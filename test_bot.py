import pytest
import pytest_timeout
import zipfile
import requests
import time
import yaml
from wrapt_timeout_decorator import timeout
import chess
import chess.engine
import threading
import os
import sys
import shutil
import importlib
shutil.copyfile('lichess.py', 'correct_lichess.py')
shutil.copyfile('./test/lichess.py', 'lichess.py')
lichess_bot = importlib.import_module("lichess-bot")

platform = sys.platform
assert platform == 'linux' or platform == 'win32'
file_extension = '.exe' if platform == 'win32' else ''
windows_or_linux = 'win' if platform == 'win32' else 'linux'


def download_sf():
    response = requests.get(f'https://stockfishchess.org/files/stockfish_14.1_{windows_or_linux}_x64.zip', allow_redirects=True)
    with open('./TEMP/sf_zip.zip', 'wb') as file:
        file.write(response.content)
    with zipfile.ZipFile('./TEMP/sf_zip.zip', 'r') as zip_ref:
        zip_ref.extractall('./TEMP/')
    shutil.copyfile(f'./TEMP/stockfish_14.1_{windows_or_linux}_x64/stockfish_14.1_{windows_or_linux}_x64{file_extension}', f'./TEMP/sf{file_extension}')
    shutil.copyfile(f'./TEMP/sf{file_extension}', f'./TEMP/sf2{file_extension}')


def run_bot(CONFIG, logging_level):
    lichess_bot.logger.info(lichess_bot.intro())
    li = lichess_bot.lichess.Lichess(CONFIG["token"], CONFIG["url"], lichess_bot.__version__)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    lichess_bot.logger.info("Welcome {}!".format(username))

    if not is_bot:
        is_bot = lichess_bot.upgrade_account(li)

    if is_bot:
        engine_factory = lichess_bot.partial(lichess_bot.engine_wrapper.create_engine, CONFIG)

        @timeout(120)
        def run_test():

            def thread_for_test():
                open('./logs/events.txt', 'w').close()

                start_time = 10
                increment = 0.1

                board = chess.Board()
                wtime = start_time
                btime = start_time

                with open('./logs/states.txt', 'w') as file:
                    file.write(f'\n{wtime},{btime}')

                engine = chess.engine.SimpleEngine.popen_uci(f'./TEMP/sf2{file_extension}')
                engine.configure({'Skill Level': 0, 'Move Overhead': 1000})

                while True:
                    if board.is_game_over():
                        with open('./logs/events.txt', 'w') as file:
                            file.write('end')
                        break

                    if len(board.move_stack) % 2 == 0:
                        if not board.move_stack:
                            move = engine.play(board, chess.engine.Limit(time=1), ponder=False)
                        else:
                            start_time = time.perf_counter_ns()
                            move = engine.play(board, chess.engine.Limit(white_clock=wtime - 2, white_inc=2), ponder=False)
                            end_time = time.perf_counter_ns()
                            wtime -= (end_time - start_time) / 1e9
                            wtime += increment
                        board.push(move.move)

                        with open('./logs/states.txt') as states:
                            state = states.read().split('\n')
                        state[0] += ' ' + move.move.uci()
                        state = '\n'.join(state)
                        with open('./logs/states.txt', 'w') as file:
                            file.write(state)

                    else:  # lichess-bot move
                        start_time = time.perf_counter_ns()
                        while True:
                            with open('./logs/states.txt') as states:
                                state2 = states.read()
                            time.sleep(0.001)
                            if state != state2:
                                break
                        with open('./logs/states.txt') as states:
                            state2 = states.read()
                        end_time = time.perf_counter_ns()
                        if len(board.move_stack) > 1:
                            btime -= (end_time - start_time) / 1e9
                            btime += increment
                        move = state2.split('\n')[0].split(' ')[-1]
                        board.push_uci(move)

                    time.sleep(0.001)
                    with open('./logs/states.txt') as states:
                        state = states.read().split('\n')
                    state[1] = f'{wtime},{btime}'
                    state = '\n'.join(state)
                    with open('./logs/states.txt', 'w') as file:
                        file.write(state)

                engine.quit()
                win = board.is_checkmate() and board.turn == chess.WHITE
                assert win
            
            thr = threading.Thread(target=thread_for_test)
            thr.start()
            lichess_bot.start(li, user_profile, engine_factory, CONFIG, logging_level, None, one_game=True)
            thr.join()

        try:
            run_test()
        except TimeoutError:
            assert False

    else:
        lichess_bot.logger.error("{} is not a bot account. Please upgrade it to a bot account!".format(user_profile["username"]))


@pytest.mark.timeout(150)
def test_bot():
    if os.path.exists('TEMP'):
        shutil.rmtree('TEMP')
    os.mkdir('TEMP')
    if os.path.exists('logs'):
        shutil.rmtree('logs')
    os.mkdir('logs')
    logging_level = lichess_bot.logging.INFO  # lichess_bot.logging_level.DEBUG
    lichess_bot.logging.basicConfig(level=logging_level, filename=None, format="%(asctime)-15s: %(message)s")
    lichess_bot.enable_color_logging(debug_lvl=logging_level)
    download_sf()
    lichess_bot.logger.info("Downloaded SF")
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG['token'] = ''
    CONFIG['engine']['dir'] = './TEMP/'
    CONFIG['engine']['name'] = f'sf{file_extension}'
    CONFIG['engine']['uci_options']['Threads'] = 1
    run_bot(CONFIG, logging_level)
    shutil.rmtree('TEMP')
    try:
        shutil.copyfile('correct_lichess.py', 'lichess.py')
        os.remove('correct_lichess.py')
    except Exception:
        pass


if __name__ == '__main__':
    test_bot()
