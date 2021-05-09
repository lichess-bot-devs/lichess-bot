import pytest
import zipfile
import requests
from shutil import copyfile
copyfile('lichess-bot.py', 'lichess_bot.py')
import lichess_bot


def test_nothing():
    assert True


def download_sf():
    response = requests.get('https://stockfishchess.org/files/stockfish_13_win_x64.zip', allow_redirects=True)
    with open('sf_zip.zip', 'wb') as file:
        file.write(response.content)
    with zipfile.ZipFile('sf_zip.zip', 'r') as zip_ref:
        zip_ref.extractall('.')
    copyfile('./stockfish_13_win_x64/stockfish_13_win_x64.exe', 'sf.exe')


def run_bot(logging_level):
    lichess_bot.logger.info(lichess_bot.intro())
    CONFIG = {'token': 'INSERT TOKEN HERE', 'url': 'https://lichess.org/', 'engine': {'dir': '.', 'name': 'sf.exe', 'protocol': 'uci', 'uci_ponder': True, 'polyglot': {'enabled': False}, 'uci_options': {'Move Overhead': 1000}, 'silence_stderr': False}, 'abort_time': 20, 'fake_think_time': False, 'move_overhead': 2000, 'challenge': {'concurrency': 0, 'sort_by': 'best', 'accept_bot': False, 'only_bot': False, 'max_increment': 180, 'min_increment': 0, 'max_base': 600, 'min_base': 0, 'variants': ['standard'], 'time_controls': ['bullet', 'blitz'], 'modes': ['casual', 'rated']}}
    li = lichess_bot.lichess.Lichess(CONFIG["token"], CONFIG["url"], lichess_bot.__version__)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    lichess_bot.logger.info("Welcome {}!".format(username))

    if not is_bot:
        is_bot = lichess_bot.upgrade_account(li)

    games = li.current_games()['nowPlaying']
    game_ids = list(map(lambda game: game['gameId'], games))
    for game in game_ids:
        try:
            li.abort(game)
        except:
            pass

    if is_bot:
        engine_factory = lichess_bot.partial(lichess_bot.engine_wrapper.create_engine, CONFIG)
        li.challenge_ai()
        lichess_bot.start(li, user_profile, engine_factory, CONFIG, logging_level, None, one_game=True)
    else:
        lichess_bot.logger.error("{} is not a bot account. Please upgrade it to a bot account!".format(user_profile["username"]))
    games = li.current_games()['nowPlaying']
    game_ids = list(map(lambda game: game['gameId'], games))
    for game in game_ids:
        try:
            li.abort(game)
        except:
            pass


def test_bot():
    logging_level = lichess_bot.logging.INFO  # lichess_bot.logging_level.DEBUG
    lichess_bot.logging.basicConfig(level=logging_level, filename=None, format="%(asctime)-15s: %(message)s")
    lichess_bot.enable_color_logging(debug_lvl=logging_level)
    download_sf()
    lichess_bot.logger.info("Downloaded SF")
    run_bot(logging_level)


if __name__ == '__main__':
    test_bot()
