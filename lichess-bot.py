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
import backoff
from config import load_config
from conversation import Conversation, ChatLine
from functools import partial
from requests.exceptions import ChunkedEncodingError, ConnectionError, HTTPError
from urllib3.exceptions import ProtocolError
import threading
import time

try:
    from http.client import RemoteDisconnected
    # New in version 3.5: Previously, BadStatusLine('') was raised.
except ImportError:
    from http.client import BadStatusLine as RemoteDisconnected

__version__ = "1.0.0-rc.1"

def upgrade_account(li):
    if li.upgrade_to_bot_account() is None:
        return False

    print("Succesfully upgraded to Bot Account!")
    return True

@backoff.on_exception(backoff.expo, BaseException, max_time=600)
def watch_control_stream(control_queue, li):
    for evnt in li.get_event_stream().iter_lines():
        if evnt:
            event = json.loads(evnt.decode('utf-8'))
            control_queue.put_nowait(event)
        else:
            control_queue.put_nowait({"type": "ping"})

def start(li, user_profile, engine_factory, config):
    # init
    max_games = config["max_concurrent_games"]
    print("You're now connected to {} and awaiting challenges.".format(config["url"]))
    manager = multiprocessing.Manager()
    challenge_queue = []
    control_queue = manager.Queue()
    control_stream = multiprocessing.Process(target=watch_control_stream, args=[control_queue, li])
    control_stream.start()
    busy_processes = 0
    queued_processes = 0
    challenge_config = config["challenge"]

    with logging_pool.LoggingPool(max_games+1) as pool:
        while True:
            event = control_queue.get()
            if event["type"] == "local_game_done":
                busy_processes -= 1
                print("+++ Process Free. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
            elif event["type"] == "challenge":
                chlng = model.Challenge(event["challenge"])
                if chlng.is_supported(challenge_config):
                    challenge_queue.append(chlng)
                    if (challenge_config.get("sort_by", "best") == "best"):
                        challenge_queue.sort(key=lambda c: -c.score())
                else:
                    try:
                        li.decline_challenge(chlng.id)
                        print("    Decline {}".format(chlng))
                    except HTTPError as exception:
                        if exception.response.status_code != 404: # ignore missing challenge
                            raise exception
            elif event["type"] == "gameStart":
                if queued_processes <= 0:
                    print("Something went wrong. Game is starting and we don't have a queued process")
                else:
                    queued_processes -= 1
                game_id = event["game"]["id"]
                pool.apply_async(play_game, [li, game_id, control_queue, engine_factory, user_profile, config])
                busy_processes += 1
                print("--- Process Used. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
            while ((queued_processes + busy_processes) < max_games and challenge_queue): # keep processing the queue until empty or max_games is reached
                chlng = challenge_queue.pop(0)
                try:
                    response = li.accept_challenge(chlng.id)
                    print("    Accept {}".format(chlng))
                    queued_processes += 1
                    print("--- Process Queue. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
                except HTTPError as exception:
                    if exception.response.status_code == 404: # ignore missing challenge
                        print("    Skip missing {}".format(chlng))
                    else:
                        raise exception

    control_stream.terminate()
    control_stream.join()

ponder_results = {}

@backoff.on_exception(backoff.expo, BaseException, max_time=600)
def play_game(li, game_id, control_queue, engine_factory, user_profile, config):
    updates = li.get_game_stream(game_id).iter_lines()

    #Initial response of stream will be the full game info. Store it
    game = model.Game(json.loads(next(updates).decode('utf-8')), user_profile["username"], li.baseUrl, config.get("abort_time", 20))
    board = setup_board(game)
    engine = engine_factory(board)
    conversation = Conversation(game, engine, li, __version__)

    print("+++ {}".format(game))

    engine_cfg = config["engine"]
    is_uci = engine_cfg["protocol"] == "uci"
    is_uci_ponder = is_uci and engine_cfg.get("uci_ponder", False)
    polyglot_cfg = engine_cfg.get("polyglot", {})

    if not polyglot_cfg.get("enabled") or not play_first_book_move(game, engine, board, li, polyglot_cfg):
        play_first_move(game, engine, board, li)

    engine.set_time_control(game)

    ponder_thread = None
    ponder_uci = None

    def ponder_thread_func(game, engine, board, wtime, btime, winc, binc):
        global ponder_results        
        best_move , ponder_move = engine.search_with_ponder(board, wtime, btime, winc, binc)
        ponder_results[game.id] = ( best_move , ponder_move )

    try:
        for binary_chunk in updates:            
            upd = json.loads(binary_chunk.decode('utf-8')) if binary_chunk else None            
            u_type = upd["type"] if upd else "ping"
            if u_type == "chatLine":
                conversation.react(ChatLine(upd), game)
            elif u_type == "gameState":
                game.state = upd
                moves = upd["moves"].split()
                board = update_board(board, moves[-1])                
                if is_engine_move(game, moves):
                    best_move = None                                        
                    ponder_move = None
                    thinking_started_at = time.time()
                    if not ( ponder_thread is None ):
                        move_uci = moves[-1]
                        if ponder_uci == move_uci:                            
                            ponder_thread.join()
                            ponder_thread = None
                            best_move , ponder_move = ponder_results[game.id]
                        else:                            
                            engine.engine.stop()
                            ponder_thread.join()
                            ponder_thread = None
                        ponder_uci = None
                    if ( best_move is None ) and polyglot_cfg.get("enabled") and len(moves) <= polyglot_cfg.get("max_depth", 8) * 2 - 1:
                        best_move = get_book_move(board, polyglot_cfg)
                    if best_move == None:
                        wtime = int(upd["wtime"])
                        btime = int(upd["btime"])
                        winc = int(upd["winc"])
                        binc = int(upd["binc"])
                        best_move , ponder_move = engine.search_with_ponder(board, wtime, btime, winc, binc)                                        
                    if is_uci_ponder and not ( ponder_move is None ):
                        mwtime = wtime
                        mbtime = btime
                        elapsed_thinking_time_ms = int ( ( time.time() - thinking_started_at ) * 1000 )
                        if game.is_white:
                            mwtime = wtime - elapsed_thinking_time_ms
                        else:
                            mbtime = btime - elapsed_thinking_time_ms
                        if ( mwtime > 0 ) and ( mbtime > 0 ):
                            ponder_board = board.copy()
                            ponder_board.push(best_move)
                            ponder_board.push(ponder_move)
                            ponder_uci = ponder_move.uci()                            
                            ponder_thread = threading.Thread(target = ponder_thread_func, args = (game, engine, ponder_board, mwtime, mbtime, winc, binc))
                            ponder_thread.start()
                    li.make_move(game.id, best_move)
                    game.abort_in(config.get("abort_time", 20))
            elif u_type == "ping":
                if game.should_abort_now():
                    print("    Aborting {} by lack of activity".format(game.url()))
                    li.abort(game.id)
    except (RemoteDisconnected, ChunkedEncodingError, ConnectionError, ProtocolError, HTTPError) as exception:
        print("Abandoning game due to connection error")
        traceback.print_exception(type(exception), exception, exception.__traceback__)
    finally:
        print("--- {} Game over".format(game.url()))
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
    with chess.polyglot.open_reader(config["book"]) as reader:
        try: # python-chess can raise "IndexError"
            if config.get("random"):
                return reader.choice(board).move()
            else:
                return reader.find(board, config.get("min_weight", 1)).move()
        except:
            pass


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


def update_board(board, move):
    uci_move = chess.Move.from_uci(move)
    board.push(uci_move)
    return board

def intro():
    return r"""
.   _/|
.  // o\
.  || ._)  lichess-bot %s
.  //__\
.  )___(   Play on Lichess with a bot
""".lstrip() % __version__

if __name__ == "__main__":
    print(intro())
    parser = argparse.ArgumentParser(description='Play on Lichess with a bot')
    parser.add_argument('-u', action='store_true', help='Add this flag to upgrade your account to a bot account.')
    parser.add_argument('-v', action='store_true', help='Verbose output. Changes log level from INFO to DEBUG.')
    parser.add_argument('--config', help='Specify a configuration file (defaults to ./config.yml)')
    args = parser.parse_args()

    logger = logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO)

    CONFIG = load_config(args.config or "./config.yml")
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"], __version__)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    print("Welcome {}!".format(username))

    if args.u is True and is_bot is False:
        is_bot = upgrade_account(li)

    if is_bot:
        engine_factory = partial(engine_wrapper.create_engine, CONFIG)
        start(li, user_profile, engine_factory, CONFIG)
    else:
        print("{} is not a bot account. Please upgrade your it to a bot account!".format(user_profile["username"]))
