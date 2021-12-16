import pytest
import pytest_timeout
import zipfile
import requests
import time
import yaml
import chess
import chess.engine
import threading
from shutil import copyfile
import importlib
copyfile('./test/lichess.py', 'lichess.py')
lichess_bot = importlib.import_module("lichess-bot")


def download_sf():
    response = requests.get('https://stockfishchess.org/files/stockfish_14.1_win_x64.zip', allow_redirects=True)
    with open('sf_zip.zip', 'wb') as file:
        file.write(response.content)
    with zipfile.ZipFile('sf_zip.zip', 'r') as zip_ref:
        zip_ref.extractall('.')
    copyfile('./stockfish_14.1_win_x64/stockfish_14.1_win_x64.exe', 'sf.exe')
    copyfile('./stockfish_14.1_win_x64/stockfish_14.1_win_x64.exe', 'sf2.exe')


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

        @pytest.mark.timeout(300)
        def run_test():

            def test_thr():
                open('events.txt', 'w').close()

                board = chess.Board()
                wtime = 60
                btime = 60

                with open('states.txt', 'w') as file:
                    file.write('\n60,60')

                engine = chess.engine.SimpleEngine.popen_uci('sf2.exe')
                engine.configure({'Skill Level': 0, 'Move Overhead': 1000})

                while True:
                    if board.is_game_over():
                        with open('events.txt', 'w') as file:
                            file.write('end')
                        break

                    if len(board.move_stack) % 2 == 0:
                        if not board.move_stack:
                            move = engine.play(board, chess.engine.Limit(time=10), ponder=False)
                        else:
                            start_time = time.perf_counter_ns()
                            move = engine.play(board, chess.engine.Limit(white_clock=wtime - 2, white_inc=2), ponder=False)
                            end_time = time.perf_counter_ns()
                            wtime -= (end_time - start_time) / 1e9
                            wtime += 2
                        board.push(move.move)

                        with open('states.txt') as states:
                            state = states.read().split('\n')
                        state[0] += ' ' + move.move.uci()
                        state = '\n'.join(state)
                        with open('states.txt', 'w') as file:
                            file.write(state)

                    else:  # lichess-bot move
                        start_time = time.perf_counter_ns()
                        while True:
                            with open('states.txt') as states:
                                state2 = states.read()
                            time.sleep(0.001)
                            if state != state2:
                                break
                        with open('states.txt') as states:
                            state2 = states.read()
                        end_time = time.perf_counter_ns()
                        if len(board.move_stack) > 1:
                            btime -= (end_time - start_time) / 1e9
                            btime += 2
                        move = state2.split('\n')[0].split(' ')[-1]
                        board.push_uci(move)

                    time.sleep(0.001)
                    with open('states.txt') as states:
                        state = states.read().split('\n')
                    state[1] = f'{wtime},{btime}'
                    state = '\n'.join(state)
                    with open('states.txt', 'w') as file:
                        file.write(state)

                engine.quit()
                win = board.is_checkmate() and board.turn == chess.WHITE
                assert win
            
            thr = threading.Thread(target=test_thr)
            thr.start()
            lichess_bot.start(li, user_profile, engine_factory, CONFIG, logging_level, None, one_game=True)
            thr.join()

        run_test()
    else:
        lichess_bot.logger.error("{} is not a bot account. Please upgrade it to a bot account!".format(user_profile["username"]))


def test_bot():
    logging_level = lichess_bot.logging.INFO  # lichess_bot.logging_level.DEBUG
    lichess_bot.logging.basicConfig(level=logging_level, filename=None, format="%(asctime)-15s: %(message)s")
    lichess_bot.enable_color_logging(debug_lvl=logging_level)
    download_sf()
    lichess_bot.logger.info("Downloaded SF")
    with open("./config.yml.default") as file:
        CONFIG = yaml.safe_load(file)
    CONFIG['token'] = ''
    CONFIG['engine']['dir'] = './'
    CONFIG['engine']['name'] = 'sf.exe'
    CONFIG['engine']['uci_options']['Threads'] = 1
    run_bot(CONFIG, logging_level)


if __name__ == '__main__':
    test_bot()
