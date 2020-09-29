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
import traceback
import logging_pool
import signal
import sys
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
        except:
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

    with logging_pool.LoggingPool(max_games+1) as pool:
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
                        li.decline_challenge(chlng.id)
                        logger.info("    Decline {}".format(chlng))
                    except:
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
            while ((queued_processes + busy_processes) < max_games and challenge_queue): # keep processing the queue until empty or max_games is reached
                chlng = challenge_queue.pop(0)
                try:
                    logger.info("    Accept {}".format(chlng))
                    queued_processes += 1
                    response = li.accept_challenge(chlng.id)
                    logger.info("--- Process Queue. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
                except (HTTPError, ReadTimeout) as exception:
                    if isinstance(exception, HTTPError) and exception.response.status_code == 404: # ignore missing challenge
                        logger.info("    Skip missing {}".format(chlng))
                    queued_processes -= 1

    logger.info("Terminated")
    control_stream.terminate()
    control_stream.join()

ponder_results = {}

@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=is_final)
def play_game(li, game_id, control_queue, engine_factory, user_profile, config, challenge_queue):
    response = li.get_game_stream(game_id)
    lines = response.iter_lines()

    #Initial response of stream will be the full game info. Store it
    initial_state = json.loads(next(lines).decode('utf-8'))
    game = model.Game(initial_state, user_profile["username"], li.baseUrl, config.get("abort_time", 20))
    board = setup_board(game)
    engine = engine_factory(board)
    engine.get_opponent_info(game)
    conversation = Conversation(game, engine, li, __version__, challenge_queue)

    logger.info("+++ {}".format(game))

    engine_cfg = config["engine"]
    is_uci = engine_cfg["protocol"] == "uci"
    is_uci_ponder = is_uci and engine_cfg.get("uci_ponder", False)
    move_overhead = config.get("move_overhead", 1000)
    polyglot_cfg = engine_cfg.get("polyglot", {})
    book_cfg = polyglot_cfg.get("book", {})

    ponder_thread = None
    deferredFirstMove = False

    ponder_uci = None
    def ponder_thread_func(game, engine, board, wtime, btime, winc, binc):
        global ponder_results        
        best_move , ponder_move = engine.search_with_ponder(board, wtime, btime, winc, binc, True)
        ponder_results[game.id] = ( best_move , ponder_move )

    engine.set_time_control(game)

    if len(board.move_stack) < 2:
        while not terminated:
            try:
                if not polyglot_cfg.get("enabled") or not play_first_book_move(game, engine, board, li, book_cfg):
                    if not play_first_move(game, engine, board, li):
                        deferredFirstMove = True
                break
            except (HTTPError) as exception:
                if exception.response.status_code == 400: # fallthrough
                    break
    else:
        moves = game.state["moves"].split()
        if not is_game_over(game) and is_engine_move(game, moves):
            book_move = None
            best_move = None
            ponder_move = None
            wtime = game.state["wtime"]
            btime = game.state["btime"]
            if board.turn == chess.WHITE:
                wtime = max(0, wtime - move_overhead)
            else:
                btime = max(0, btime - move_overhead)
            if polyglot_cfg.get("enabled") and len(moves) <= polyglot_cfg.get("max_depth", 8) * 2 - 1:
                book_move = get_book_move(board, book_cfg)
            if book_move == None:
                logger.info("Searching for wtime {} btime {}".format(wtime, btime))
                best_move , ponder_move = engine.search_with_ponder(board, wtime, btime, game.state["winc"], game.state["binc"])
                engine.print_stats()
            else:
                best_move = book_move

            if is_uci_ponder and not ( ponder_move is None ):
                ponder_board = board.copy()
                ponder_board.push(best_move)
                ponder_board.push(ponder_move)
                ponder_uci = ponder_move.uci()
                logger.info("Pondering for wtime {} btime {}".format(wtime, btime))
                ponder_thread = threading.Thread(target = ponder_thread_func, args = (game, engine, ponder_board, wtime, btime, game.state["winc"], game.state["binc"]))
                ponder_thread.start()
            li.make_move(game.id, best_move)

    while not terminated:
        try:
            binary_chunk = next(lines)
        except(StopIteration):
            break
        try:
            upd = json.loads(binary_chunk.decode('utf-8')) if binary_chunk else None
            u_type = upd["type"] if upd else "ping"
            if u_type == "chatLine":
                conversation.react(ChatLine(upd), game)
            elif u_type == "gameState":
                game.state = upd
                moves = upd["moves"].split()
                board = update_board(board, moves[-1])
                if not is_game_over(game) and is_engine_move(game, moves):
                    if config.get("fake_think_time") and len(moves) > 9:
                        delay = min(game.clock_initial, game.my_remaining_seconds()) * 0.015
                        accel = 1 - max(0, min(100, len(moves) - 20)) / 150
                        sleep = min(5, delay * accel)
                        time.sleep(sleep)

                    book_move = None
                    best_move = None
                    ponder_move = None
                    if not ( ponder_thread is None ):
                        move_uci = moves[-1]
                        if ponder_uci == move_uci:
                            engine.engine.ponderhit()
                            ponder_thread.join()
                            ponder_thread = None
                            best_move , ponder_move = ponder_results[game.id]
                            engine.print_stats()
                        else:
                            engine.engine.stop()
                            ponder_thread.join()
                            ponder_thread = None
                        ponder_uci = None

                    wtime = upd["wtime"]
                    btime = upd["btime"]
                    if board.turn == chess.WHITE:
                        wtime = max(0, wtime - move_overhead)
                    else:
                        btime = max(0, btime - move_overhead)

                    if not deferredFirstMove:
                        if polyglot_cfg.get("enabled") and len(moves) <= polyglot_cfg.get("max_depth", 8) * 2 - 1:
                            book_move = get_book_move(board, book_cfg)
                        if best_move == None:
                            if book_move == None:
                                logger.info("Searching for wtime {} btime {}".format(wtime, btime))
                                best_move , ponder_move = engine.search_with_ponder(board, wtime, btime, upd["winc"], upd["binc"])
                                engine.print_stats()
                            else:
                                best_move = book_move
                        else:
                            if not ( book_move == None ):
                                best_move = book_move
                                ponder_move = None

                        if is_uci_ponder and not ( ponder_move is None ):
                            ponder_board = board.copy()
                            ponder_board.push(best_move)
                            ponder_board.push(ponder_move)
                            ponder_uci = ponder_move.uci()
                            logger.info("Pondering for wtime {} btime {}".format(wtime, btime))
                            ponder_thread = threading.Thread(target = ponder_thread_func, args = (game, engine, ponder_board, wtime, btime, upd["winc"], upd["binc"]))
                            ponder_thread.start()
                        li.make_move(game.id, best_move)
                    else:
                        if not polyglot_cfg.get("enabled") or not play_first_book_move(game, engine, board, li, book_cfg):
                            play_first_move(game, engine, board, li)
                        deferredFirstMove = False
                if board.turn == chess.WHITE:
                    game.ping(config.get("abort_time", 20), (upd["wtime"] + upd["winc"]) / 1000 + 60)
                else:
                    game.ping(config.get("abort_time", 20), (upd["btime"] + upd["binc"]) / 1000 + 60)
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
        except (HTTPError, ReadTimeout, RemoteDisconnected, ChunkedEncodingError, ConnectionError, ProtocolError) as e:
            ongoing_games = li.get_ongoing_games()
            game_over = True
            for ongoing_game in ongoing_games:
                if ongoing_game["gameId"] == game.id:
                    game_over = False
                    break
            if not game_over:
                continue
            else:
                break

    logger.info("--- {} Game over".format(game.url()))
    engine.engine.stop()
    engine.quit()
    if not ( ponder_thread is None ):
        ponder_thread.join()
        ponder_thread = None

    # This can raise queue.NoFull, but that should only happen if we're not processing
    # events fast enough and in this case I believe the exception should be raised
    control_queue.put_nowait({"type": "local_game_done"})


def play_first_move(game, engine, board, li):
    moves = game.state["moves"].split()
    if is_engine_move(game, moves):
        # need to hardcode first movetime since Lichess has 30 sec limit.
        best_move = engine.first_search(board, 10000)
        engine.print_stats()
        li.make_move(game.id, best_move)
        return True
    return False


def play_first_book_move(game, engine, board, li, config):
    moves = game.state["moves"].split()
    if is_engine_move(game, moves):
        book_move = get_book_move(board, config)
        if book_move:
            li.make_move(game.id, book_move)
            return True
        else:
            return play_first_move(game, engine, board, li)
    return False


def get_book_move(board, config):
    if board.uci_variant == "chess":
        book = config["standard"]
    else:
        if config.get("{}".format(board.uci_variant)):
            book = config["{}".format(board.uci_variant)]
        else:
            return None

    with chess.polyglot.open_reader(book) as reader:
        try:
            selection = config.get("selection", "weighted_random")
            if selection == "weighted_random":
                move = reader.weighted_choice(board).move()
            elif selection == "uniform_random":
                move = reader.choice(board, minimum_weight=config.get("min_weight", 1)).move()
            elif selection == "best_move":
                move = reader.find(board, minimum_weight=config.get("min_weight", 1)).move()
        except IndexError:
            # python-chess raises "IndexError" if no entries found
            move = None

    if move is not None:
        logger.info("Got move {} from book {}".format(move, book))

    return move


def setup_board(game):
    if game.variant_name.lower() == "chess960":
        board = chess.Board(game.initial_fen, chess960=True)
    elif game.variant_name == "From Position":
        board = chess.Board(game.initial_fen)
    else:
        VariantBoard = find_variant(game.variant_name)
        board = VariantBoard()
    moves = game.state["moves"].split()
    for move in moves:
        board = update_board(board, move)

    return board


def is_white_to_move(game, moves):
    return len(moves) % 2 == (0 if game.white_starts else 1)


def is_engine_move(game, moves):
    return game.is_white == is_white_to_move(game, moves)


def is_game_over(game):
    return game.state["status"] != "started"


def update_board(board, move):
    uci_move = chess.Move.from_uci(move)
    if board.is_legal(uci_move):
        board.push(uci_move)
    else:
        logger.debug('Ignoring illegal move {} on board {}'.format(move, board.fen()))
    return board

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
