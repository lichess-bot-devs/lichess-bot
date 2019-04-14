import argparse
import backoff
import json
import logging
import multiprocessing
import traceback
import signal

from functools import partial
from requests.exceptions import ChunkedEncodingError, ConnectionError, HTTPError
from urllib3.exceptions import ProtocolError

from src import logging_pool, lichess, engine_wrapper
from src.models.game import Game
from src.models.challenge import Challenge
from src.models.book import Book
from src.config import load_config
from src.conversation import Conversation, ChatLine
from src.color_logger import enable_color_logging

logger = logging.getLogger(__name__)

try:
    from http.client import RemoteDisconnected
    # New in version 3.5: Previously, BadStatusLine('') was raised.
except ImportError:
    from http.client import BadStatusLine as RemoteDisconnected

__version__ = "1.1.5"
terminated = False


def signal_handler(signal, frame):
    global terminated
    logger.debug("Recieved SIGINT. Terminating client.")
    terminated = True


signal.signal(signal.SIGINT, signal_handler)


def is_final(exception):
    return isinstance(exception, HTTPError) and exception.response.status_code < 500


def upgrade_account(li):
    if li.upgrade_to_bot_account() is None:
        return False

    logger.info("Succesfully upgraded to Bot Account!")
    return True


@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=is_final)
def watch_control_stream(control_queue, li):
    response = li.get_event_stream()
    try:
        for line in response.iter_lines():
            if line:
                event = json.loads(line.decode('utf-8'))
                control_queue.put_nowait(event)
            else:
                control_queue.put_nowait({"type": "ping"})
    except (RemoteDisconnected, ChunkedEncodingError, ConnectionError, ProtocolError) as exception:
        logger.error("Terminating client due to connection error")
        traceback.print_exception(type(exception), exception, exception.__traceback__)
        control_queue.put_nowait({"type": "terminated"})


def start(li, profile, engine_factory, config):
    challenge_config = config["challenge"]
    max_games = challenge_config.get("concurrency", 1)
    logger.info("You're now connected to {} and awaiting challenges.".format(config["url"]))
    manager = multiprocessing.Manager()
    challenge_queue = manager.list()
    control_queue = manager.Queue()
    control_stream = multiprocessing.Process(target=watch_control_stream, args=[control_queue, li])
    control_stream.start()
    busy_processes = 0
    queued_processes = 0

    with logging_pool.LoggingPool(max_games + 1) as pool:
        while not terminated:
            event = control_queue.get()
            if event["type"] == "terminated":
                break
            elif event["type"] == "local_game_done":
                busy_processes -= 1
                logger.info("+++ Process Free. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
            elif event["type"] == "challenge":
                chlng = Challenge(event["challenge"])
                if chlng.is_supported(challenge_config):
                    challenge_queue.append(chlng)
                    if challenge_config.get("sort_by", "best") == "best":
                        list_c = list(challenge_queue)
                        list_c.sort(key=lambda c: -c.score())
                        challenge_queue = list_c
                else:
                    try:
                        li.decline_challenge(chlng.id)
                        logger.info("    Decline {}".format(chlng))
                    except HTTPError as exception:
                        if exception.response.status_code != 404: # ignore missing challenge
                            raise exception
            elif event["type"] == "gameStart":
                if queued_processes <= 0:
                    logger.debug("Something went wrong. Game is starting and we don't have a queued process")
                else:
                    queued_processes -= 1
                game_id = event["game"]["id"]
                pool.apply_async(
                    play_game,
                    [li, game_id, control_queue, engine_factory, profile, config, challenge_queue]
                )
                busy_processes += 1
                logger.info("--- Process Used. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
            # keep processing the queue until empty or max_games is reached
            while (queued_processes + busy_processes) < max_games and challenge_queue:
                chlng = challenge_queue.pop(0)
                try:
                    response = li.accept_challenge(chlng.id)
                    logger.info("    Accept {}".format(chlng))
                    queued_processes += 1
                    logger.info("--- Process Queue. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
                except HTTPError as exception:
                    if exception.response.status_code == 404: # ignore missing challenge
                        logger.info("    Skip missing {}".format(chlng))
                    else:
                        raise exception
    logger.info("Terminated")
    control_stream.terminate()
    control_stream.join()


@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=is_final)
def play_game(li, game_id, control_queue, engine_factory, profile, config, challenge_queue):
    response = li.get_game_stream(game_id)
    lines = response.iter_lines()

    # Initial response of stream will be the full game info. Store it
    game = Game(
        json.loads(next(lines).decode('utf-8')),
        profile["username"],
        li.baseUrl,
        config.get("abort_time", 20),
        config.get("fake_think_time", 0)
    )
    engine = engine_factory(game.board)
    conversation = Conversation(game, engine, li, __version__, challenge_queue)
    book = Book(config["engine"].get("polyglot", {}), game.board.uci_variant)

    logger.info("+++ {}".format(game))

    try:
        best_move = None
        if book.is_enabled() and game.is_my_move():
            best_move = book.get_move(game.board)
        if best_move is None:
            best_move = engine.first_search(game.board, 10000)

        li.make_move(game.id, best_move)
        engine.set_time_control(game)

        for binary_chunk in lines:
            upd = json.loads(binary_chunk.decode('utf-8')) if binary_chunk else None
            u_type = upd["type"] if upd else "ping"
            if u_type == "chatLine":
                conversation.react(ChatLine(upd), game)
            elif u_type == "gameState":
                game.state = upd
                moves = upd["moves"].split()
                game.update_board(moves[-1])

                if not game.board.is_game_over() and game.is_my_move():
                    game.fake_think()
                    best_move = None
                    if book.enabled and len(moves) <= book.max_depth:
                        best_move = book.get_move(game.board)
                    if not best_move:
                        best_move = engine.search(
                            game.board,
                            upd["wtime"],
                            upd["btime"],
                            upd["winc"],
                            upd["binc"]
                        )
                    li.make_move(game.id, best_move)
                    game.update_abort_time()
            elif u_type == "ping":
                if game.should_abort_now():
                    logger.info("    Aborting {} by lack of activity".format(game.url()))
                    li.abort(game.id)
    except HTTPError as e:
        ongoing_games = li.get_ongoing_games()
        game_over = True
        for ongoing_game in ongoing_games:
            if ongoing_game["gameId"] == game.id:
                game_over = False
                break
        if not game_over:
            logger.warn("Abandoning game due to HTTP "+response.status_code)
    except (RemoteDisconnected, ChunkedEncodingError, ConnectionError, ProtocolError) as exception:
        logger.error("Abandoning game due to connection error")
        traceback.print_exception(type(exception), exception, exception.__traceback__)
    finally:
        logger.info("--- {} Game over".format(game.url()))
        engine.quit()
        # This can raise queue.NoFull, but that should only happen if we're not processing
        # events fast enough and in this case I believe the exception should be raised
        control_queue.put_nowait({"type": "local_game_done"})


def intro():
    return r"""
    .   _/|
    .  // o\
    .  || ._)  lichess-bot %s
    .  //__\
    .  )___(   Play on Lichess with a bot
    """ % __version__


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Play on Lichess with a bot')
    parser.add_argument('-u', action='store_true', help='Add this flag to upgrade your account to a bot account.')
    parser.add_argument('-v', action='store_true', help='Verbose output. Changes log level from INFO to DEBUG.')
    parser.add_argument('--config', help='Specify a configuration file (defaults to ./config.yml)')
    parser.add_argument('-l', '--logfile', help="Log file to append logs to.", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO, filename=args.logfile,
                        format="%(asctime)-15s: %(message)s")
    enable_color_logging(debug_lvl=logging.DEBUG if args.v else logging.INFO)
    logger.info(intro())
    CONFIG = load_config(args.config or "./config.yml")
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"], __version__)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    logger.info("Welcome {}!".format(username))

    if args.u is True and is_bot is False:
        is_bot = upgrade_account(li)

    if is_bot:
        engine_factory = partial(engine_wrapper.create_engine, CONFIG)
        start(li, user_profile, engine_factory, CONFIG)
    else:
        logger.error("{} is not a bot account. Please upgrade it to a bot account!".format(user_profile["username"]))
