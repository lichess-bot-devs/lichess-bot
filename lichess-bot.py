import argparse
import chess
from chess.variant import find_variant
import chess.polyglot
import engine_wrapper
import model
import json
import lichess
import logging
import multiprocessing
import logging_pool
import signal
import time
import backoff
import threading
from config import load_config
from conversation import Conversation, ChatLine
from functools import partial
from requests.exceptions import ChunkedEncodingError, ConnectionError, HTTPError, ReadTimeout
from urllib3.exceptions import ProtocolError
from ColorLogger import enable_color_logging

logger = logging.getLogger(__name__)

try:
    from http.client import RemoteDisconnected
    # New in version 3.5: Previously, BadStatusLine('') was raised.
except ImportError:
    from http.client import BadStatusLine as RemoteDisconnected

__version__ = "1.2.0"

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


def watch_control_stream(control_queue, li):
    while not terminated:
        try:
            response = li.get_event_stream()
            lines = response.iter_lines()
            for line in lines:
                if line:
                    event = json.loads(line.decode('utf-8'))
                    control_queue.put_nowait(event)
                else:
                    control_queue.put_nowait({"type": "ping"})
        except Exception:
            pass


def start(li, user_profile, engine_factory, config):
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
                chlng = model.Challenge(event["challenge"])
                if chlng.is_supported(challenge_config):
                    challenge_queue.append(chlng)
                    if (challenge_config.get("sort_by", "best") == "best"):
                        list_c = list(challenge_queue)
                        list_c.sort(key=lambda c: -c.score())
                        challenge_queue = list_c
                else:
                    try:
                        reason = "generic"
                        challenge = config["challenge"]
                        if not chlng.is_supported_variant(challenge["variants"]):
                            reason = "variant"
                        if not chlng.is_supported_time_control(challenge["time_controls"], challenge.get("max_increment", 180), challenge.get("min_increment", 0)):
                            reason = "timeControl"
                        if not chlng.is_supported_mode(challenge["modes"]):
                            reason = "casual" if chlng.rated else "rated"
                        if not challenge.get("accept_bot", False) and chlng.challenger_is_bot:
                            reason = "noBot"
                        if challenge.get("only_bot", False) and not chlng.challenger_is_bot:
                            reason = "onlyBot"
                        li.decline_challenge(chlng.id, reason=reason)
                        logger.info("    Decline {} for reason '{}'".format(chlng, reason))
                    except Exception:
                        pass
            elif event["type"] == "gameStart":
                if queued_processes <= 0:
                    logger.debug("Something went wrong. Game is starting and we don't have a queued process")
                else:
                    queued_processes -= 1
                busy_processes += 1
                logger.info("--- Process Used. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
                game_id = event["game"]["id"]
                pool.apply_async(play_game, [li, game_id, control_queue, engine_factory, user_profile, config, challenge_queue])
            while ((queued_processes + busy_processes) < max_games and challenge_queue):  # keep processing the queue until empty or max_games is reached
                chlng = challenge_queue.pop(0)
                try:
                    logger.info("    Accept {}".format(chlng))
                    queued_processes += 1
                    li.accept_challenge(chlng.id)
                    logger.info("--- Process Queue. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
                except (HTTPError, ReadTimeout) as exception:
                    if isinstance(exception, HTTPError) and exception.response.status_code == 404:  # ignore missing challenge
                        logger.info("    Skip missing {}".format(chlng))
                    queued_processes -= 1

            control_queue.task_done()

    logger.info("Terminated")
    control_stream.terminate()
    control_stream.join()


ponder_results = {}


@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=is_final)
def play_game(li, game_id, control_queue, engine_factory, user_profile, config, challenge_queue):
    response = li.get_game_stream(game_id)
    lines = response.iter_lines()

    # Initial response of stream will be the full game info. Store it
    initial_state = json.loads(next(lines).decode('utf-8'))
    game = model.Game(initial_state, user_profile["username"], li.baseUrl, config.get("abort_time", 20))
    engine = engine_factory()
    engine.get_opponent_info(game)
    engine.set_time_control(game)
    conversation = Conversation(game, engine, li, __version__, challenge_queue)

    logger.info("+++ {}".format(game))

    engine_cfg = config["engine"]
    is_uci = engine_cfg["protocol"] == "uci"
    is_uci_ponder = is_uci and engine_cfg.get("uci_ponder", False)
    move_overhead = config.get("move_overhead", 1000)
    polyglot_cfg = engine_cfg.get("polyglot", {})

    ponder_thread = None
    ponder_uci = None

    first_move = True
    while not terminated:
        try:
            if first_move:
                upd = game.state
                first_move = False
            else:
                binary_chunk = next(lines)
                upd = json.loads(binary_chunk.decode('utf-8')) if binary_chunk else None

            u_type = upd["type"] if upd else "ping"
            if u_type == "chatLine":
                conversation.react(ChatLine(upd), game)
            elif u_type == "gameState":
                game.state = upd
                board = setup_board(game)
                if not is_game_over(game) and is_engine_move(game, board):
                    start_time = time.perf_counter_ns()
                    fake_thinking(config, board, game)

                    best_move, ponder_move = get_book_move(board, polyglot_cfg), None
                    if best_move is None:
                        if len(board.move_stack) < 2:
                            best_move, ponder_move = choose_first_move(engine, board)
                        else:
                            best_move, ponder_move = get_pondering_results(ponder_thread, ponder_uci, game, board, engine)
                            if best_move is None:
                                best_move, ponder_move = choose_move(engine, board, game, start_time, move_overhead)
                    li.make_move(game.id, best_move)
                    ponder_thread, ponder_uci = start_pondering(engine, board, game, is_uci_ponder, best_move, ponder_move, start_time, move_overhead)

                wb = 'w' if board.turn == chess.WHITE else 'b'
                game.ping(config.get("abort_time", 20), (upd[f"{wb}time"] + upd[f"{wb}inc"]) / 1000 + 60)
            elif u_type == "ping":
                if game.should_abort_now():
                    logger.info("    Aborting {} by lack of activity".format(game.url()))
                    li.abort(game.id)
                    break
                elif game.should_terminate_now():
                    logger.info("    Terminating {} by lack of activity".format(game.url()))
                    if game.is_abortable():
                        li.abort(game.id)
                    break
        except (HTTPError, ReadTimeout, RemoteDisconnected, ChunkedEncodingError, ConnectionError, ProtocolError):
            if game.id not in (ongoing_game["gameId"] for ongoing_game in li.get_ongoing_games()):
                break
        except StopIteration:
            break

    logger.info("--- {} Game over".format(game.url()))
    engine.stop()
    engine.quit()
    if ponder_thread is not None:
        ponder_thread.join()

    # This can raise queue.NoFull, but that should only happen if we're not processing
    # events fast enough and in this case I believe the exception should be raised
    control_queue.put_nowait({"type": "local_game_done"})


def choose_first_move(engine, board):
    # need to hardcode first movetime (10000 ms) since Lichess has 30 sec limit.
    return engine.first_search(board, 10000)


def get_book_move(board, polyglot_cfg):
    if not polyglot_cfg.get("enabled") or len(board.move_stack) > polyglot_cfg.get("max_depth", 8) * 2 - 1:
        return None

    book_config = polyglot_cfg.get("book", {})

    if board.uci_variant == "chess":
        books = book_config["standard"]
    else:
        if book_config.get("{}".format(board.uci_variant)):
            books = book_config["{}".format(board.uci_variant)]
        else:
            return None

    if isinstance(books, str):
        books = [books]

    for book in books:
        with chess.polyglot.open_reader(book) as reader:
            try:
                selection = book_config.get("selection", "weighted_random")
                if selection == "weighted_random":
                    move = reader.weighted_choice(board).move
                elif selection == "uniform_random":
                    move = reader.choice(board, minimum_weight=book_config.get("min_weight", 1)).move
                elif selection == "best_move":
                    move = reader.find(board, minimum_weight=book_config.get("min_weight", 1)).move
            except IndexError:
                # python-chess raises "IndexError" if no entries found
                move = None

        if move is not None:
            logger.info("Got move {} from book {}".format(move, book))
            return move

    return None


def choose_move(engine, board, game, start_time, move_overhead):
    wtime = game.state["wtime"]
    btime = game.state["btime"]
    pre_move_time = int((time.perf_counter_ns() - start_time) / 1000000)
    if board.turn == chess.WHITE:
        wtime = max(0, wtime - move_overhead - pre_move_time)
    else:
        btime = max(0, btime - move_overhead - pre_move_time)

    logger.info("Searching for wtime {} btime {}".format(wtime, btime))
    return engine.search_with_ponder(board, wtime, btime, game.state["winc"], game.state["binc"])


def start_pondering(engine, board, game, is_uci_ponder, best_move, ponder_move, start_time, move_overhead):
    if not is_uci_ponder or ponder_move is None:
        return None, None

    ponder_board = board.copy()
    ponder_board.push(best_move)
    ponder_board.push(ponder_move)

    wtime = game.state["wtime"]
    btime = game.state["btime"]
    setup_time = int((time.perf_counter_ns() - start_time) / 1000000)
    if board.turn == chess.WHITE:
        wtime = max(0, wtime - move_overhead - setup_time + game.state["winc"])
    else:
        btime = max(0, btime - move_overhead - setup_time + game.state["binc"])

    def ponder_thread_func(game, engine, board, wtime, btime, winc, binc):
        global ponder_results
        best_move, ponder_move = engine.search_with_ponder(board, wtime, btime, winc, binc, True)
        ponder_results[game.id] = (best_move, ponder_move)

    logger.info("Pondering for wtime {} btime {}".format(wtime, btime))
    ponder_thread = threading.Thread(target=ponder_thread_func, args=(game, engine, ponder_board, wtime, btime, game.state["winc"], game.state["binc"]))
    ponder_thread.start()
    return ponder_thread, ponder_move.uci()


def get_pondering_results(ponder_thread, ponder_uci, game, board, engine):
    if ponder_thread is None:
        return None, None

    move_uci = board.move_stack[-1].uci()
    if ponder_uci == move_uci:
        engine.ponderhit()
        ponder_thread.join()
        return ponder_results[game.id]
    else:
        engine.stop()
        ponder_thread.join()
        return None, None


def fake_thinking(config, board, game):
    if config.get("fake_think_time") and len(board.move_stack) > 9:
        delay = min(game.clock_initial, game.my_remaining_seconds()) * 0.015
        accel = 1 - max(0, min(100, len(board.move_stack) - 20)) / 150
        sleep = min(5, delay * accel)
        time.sleep(sleep)


def setup_board(game):
    if game.variant_name.lower() == "chess960":
        board = chess.Board(game.initial_fen, chess960=True)
    elif game.variant_name == "From Position":
        board = chess.Board(game.initial_fen)
    else:
        VariantBoard = find_variant(game.variant_name)
        board = VariantBoard()

    for move in game.state["moves"].split():
        try:
            board.push_uci(move)
        except ValueError as e:
            logger.debug('Ignoring illegal move {} on board {} ({})'.format(move, board.fen(), e))

    return board


def is_engine_move(game, board):
    return game.is_white == (board.turn == chess.WHITE)


def is_game_over(game):
    return game.state["status"] != "started"


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

    if args.u and not is_bot:
        is_bot = upgrade_account(li)

    if is_bot:
        engine_factory = partial(engine_wrapper.create_engine, CONFIG)
        start(li, user_profile, engine_factory, CONFIG)
    else:
        logger.error("{} is not a bot account. Please upgrade it to a bot account!".format(user_profile["username"]))
