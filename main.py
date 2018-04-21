import argparse
import chess
from chess.variant import find_variant
import engine_wrapper
import model
import json
import lichess
import logging
import multiprocessing
import queue
import os
import os.path
import traceback
import logging_pool
from config import load_config
from conversation import Conversation, ChatLine
from functools import partial
from http.client import RemoteDisconnected
from requests.exceptions import ConnectionError, HTTPError
from urllib3.exceptions import ProtocolError

__version__ = "0.3"

def upgrade_account(li):
    if li.upgrade_to_bot_account() is None:
        return False

    print("Succesfully upgraded to Bot Account!")
    return True

def watch_control_stream(control_queue, li):
    for evnt in li.get_event_stream().iter_lines():
        if evnt:
            event = json.loads(evnt.decode('utf-8'))
            control_queue.put_nowait(event)
        else:
            control_queue.put_nowait({"type": "ping"})

def start(li, user_profile, max_games, max_queued, engine_factory, config):
    # init
    username = user_profile.get("username")
    print("Welcome {}!".format(username))
    manager = multiprocessing.Manager()
    challenge_queue = []
    control_queue = manager.Queue()
    control_stream = multiprocessing.Process(target=watch_control_stream, args=[control_queue, li])
    control_stream.start()
    busy_processes = 0
    queued_processes = 0

    with logging_pool.LoggingPool(max_games+1) as pool:
        events = li.get_event_stream().iter_lines()

        quit = False
        while not quit:
            event = control_queue.get()
            if event["type"] == "local_game_done":
                busy_processes -= 1
                print("+++ Process Free. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
            elif event["type"] == "challenge":
                chlng = model.Challenge(event["challenge"])
                if len(challenge_queue) < max_queued and can_accept_challenge(chlng, config):
                    challenge_queue.append(chlng)
                    print("    Queue {}".format(chlng.show()))
                else:
                    try:
                        li.decline_challenge(chlng.id)
                        print("    Decline {}".format(chlng.show()))
                    except HTTPError as exception:
                        if exception.response.status_code != 404: # ignore missing challenge
                            raise exception
            elif event["type"] == "gameStart":
                if queued_processes <= 0:
                    print("Something went wrong. Game is starting and we don't have a queued process")
                else:
                    queued_processes -= 1
                game_id = event["game"]["id"]
                pool.apply_async(play_game, [li, game_id, control_queue, engine_factory])
                busy_processes += 1
                print("--- Process Used. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))

            while ((queued_processes + busy_processes) < max_games and challenge_queue): # keep processing the queue until empty or max_games is reached
                chlng = challenge_queue.pop(0)
                try:
                    response = li.accept_challenge(chlng.id)
                    print("    Accept {}".format(chlng.show()))
                    queued_processes += 1
                    print("--- Process Queue. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
                except HTTPError as exception:
                    if exception.response.status_code == 404: # ignore missing challenge
                        print("    Skip missing {}".format(chlng.show()))
                    else:
                        raise exception

    control_stream.terminate()
    control_stream.join()


def play_game(li, game_id, control_queue, engine_factory):
    username = li.get_profile()["username"]
    updates = li.get_game_stream(game_id).iter_lines()

    #Initial response of stream will be the full game info. Store it
    game = model.Game(json.loads(next(updates).decode('utf-8')), username, li.baseUrl)
    board = setup_board(game)
    engine = engine_factory(board)
    conversation = Conversation(game, engine, li)

    print("+++ {}".format(game.show()))

    engine.pre_game(game)

    board = play_first_move(game, engine, board, li)

    try:
        for binary_chunk in updates:
            upd = json.loads(binary_chunk.decode('utf-8')) if binary_chunk else None
            u_type = upd["type"] if upd else "ping"
            if u_type == "chatLine":
                conversation.react(ChatLine(upd))
            elif u_type == "gameState":
                moves = upd.get("moves").split()
                board = update_board(board, moves[-1])

                if is_engine_move(game.is_white, moves):
                    best_move = engine.search(board, upd.get("wtime"), upd.get("btime"), upd.get("winc"), upd.get("binc"))
                    li.make_move(game.id, best_move)
    except (RemoteDisconnected, ConnectionError, ProtocolError, HTTPError) as exception:
        print("Abandoning game due to connection error")
        traceback.print_exception(type(exception), exception, exception.__traceback__)
    finally:
        print("--- {} Game over".format(game.url()))
        engine.quit()
        # This can raise queue.NoFull, but that should only happen if we're not processing
        # events fast enough and in this case I believe the exception should be raised
        control_queue.put_nowait({"type": "local_game_done"})


def can_accept_challenge(chlng, config):
    return chlng.is_supported(config)


def play_first_move(game, engine, board, li):
    moves = game.state["moves"].split()
    if is_engine_move(game.is_white, moves):
        # need to hardcode first movetime since Lichess has 30 sec limit.
        best_move = engine.first_search(board, 2000)
        li.make_move(game.id, best_move)

    return board


def setup_board(game):
    if game.variant_name.lower() == "chess960":
        board = chess.Board(game.initial_fen, chess960=True)
    else:
        VariantBoard = find_variant(game.variant_name);
        board = VariantBoard()
    moves = game.state["moves"].split()
    for move in moves:
        board = update_board(board, move)

    return board


def is_white_to_move(moves):
    return (len(moves) % 2) == 0


def is_engine_move(is_white, moves):
    is_w = (is_white and is_white_to_move(moves))
    is_b = (is_white is False and is_white_to_move(moves) is False)

    return (is_w or is_b)


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
    logger = logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='Play on Lichess with a bot')
    parser.add_argument('-u', action='store_true', help='Add this flag to upgrade your account to a bot account.')
    args = parser.parse_args()
    CONFIG = load_config()
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"])

    user_profile = li.get_profile()
    is_bot = user_profile.get("title") == "BOT"

    if args.u is True and is_bot is False:
        is_bot = upgrade_account(li)

    if is_bot:
        max_games = CONFIG["max_concurrent_games"]
        max_queued = CONFIG["max_queued_challenges"]
        engine_factory = partial(engine_wrapper.create_engine, CONFIG)
        start(li, user_profile, max_games, max_queued, engine_factory, CONFIG)
    else:
        print("{} is not a bot account. Please upgrade your it to a bot account!".format(user_profile["username"]))
