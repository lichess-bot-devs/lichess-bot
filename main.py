import argparse
import chess
import challenge
import chess.uci
import json
import lichess
import logging
import multiprocessing
import queue
import os
import traceback
import yaml

CONFIG = {}

def upgrade_account(li):
    if li.upgrade_to_bot_account() is None:
        return False

    print("Succesfully upgraded to Bot Account!")
    return True

def clear_finished_games(results):
    return [r for r in results if not r.ready()]

def start(li, user_profile, engine_path, weights=None, threads=None):
    # init
    username = user_profile.get("username")
    print("Welcome {}!".format(username))
    manager = multiprocessing.Manager()
    challenge_queue = manager.Queue(CONFIG["max_queued_challenges"])
    with multiprocessing.Pool(CONFIG['max_concurrent_games']+1) as pool:
        event_stream = li.get_event_stream()
        events = event_stream.iter_lines()
        challenges = []
        results = []

        for evnt in events:
            if evnt:
                event = json.loads(evnt.decode('utf-8'))
                if event["type"] == "challenge":
                    chlng = challenge.Challenge(event["challenge"])
                    description = "challenge #{} from {}!".format(chlng.id, chlng.challenger)

                    results = clear_finished_games(results)
                    if can_accept_challenge(chlng):
                        available_workers = len(results) < CONFIG["max_concurrent_games"]
                        if available_workers:
                            print("Accepting {}".format(description))
                            li.accept_challenge(chlng.id)
                        else:
                            try:
                                challenge_queue.put_nowait(chlng.id)
                            except queue.Full:
                                print("Declining {}".format(description))
                                li.decline_challenge(chlng.id)

                    else:
                        print("Declining {}".format(description))
                        li.decline_challenge(chlng.id)

                if event["type"] == "gameStart":
                    game_id = event["game"]["id"]
                    r = pool.apply_async(play_game, [li, game_id, weights, threads, challenge_queue])
                    results.append(r)


def play_game(li, game_id, weights, threads, challenge_queue):
    username = li.get_profile()["username"]
    stream = li.get_game_stream(game_id)
    updates = stream.iter_lines()

    #Initial response of stream will be the full game info. Store it
    game_info = json.loads(next(updates).decode('utf-8'))
    board = setup_board(game_info)
    engine, info_handler = setup_engine(engine_path, board, weights, threads)

    # need to do this to check if its playing against SF.
    # If Lichess Stockfish is playing response will contain:
    # 'white':{'aiLevel': 6} or 'black':{'aiLevel': 6}
    # instead of user info
    is_white = False
    if game_info.get("white").get("name"):
        is_white = (game_info.get("white")["name"] == username)

    print("Game Info: {}".format(game_info))

    board = play_first_move(game_info, game_id, is_white, engine, board, li)

    for update in updates:
        if update:
            #board = process_update(board, engine, update, movetime, is_white)
            upd = json.loads(update.decode('utf-8'))
            print("Updated moves: {}".format(upd))
            moves = upd.get("moves").split()
            board = update_board(board, moves[-1])

            if is_engine_move(is_white, moves):
                engine.position(board)
                best_move, ponder = engine.go(
                    wtime=upd.get("wtime"),
                    btime=upd.get("btime"),
                    winc=upd.get("winc"),
                    binc=upd.get("binc")
                )
                li.make_move(game_id, best_move)

                print()
                print("Engines best move: {}".format(best_move))
                get_engine_stats(info_handler)

    print("Game over!")
    try:
        challenge_id = challenge_queue.get_nowait()
        li.accept_challenge(challenge_id)
    except queue.Empty:
        pass


def can_accept_challenge(chlng):
    return chlng.is_supported(CONFIG)


def play_first_move(game_info, game_id, is_white, engine, board, li):
    moves = game_info["state"]["moves"].split()
    print("Now playing {}{}".format(li.baseUrl, game_info["id"]))
    if is_engine_move(is_white, moves):
        engine.position(board)
        # need to hardcode first movetime since Lichess has 30 sec limit.
        best_move, ponder = engine.go(movetime=2000)
        li.make_move(game_id, best_move)

    return board


def setup_board(game_info):
    board = chess.Board()
    moves = game_info["state"]["moves"].split()
    for move in moves:
        board = update_board(board, move)

    return board


def setup_engine(engine_path, board, weights=None, threads=None):
    print("Loading Engine!")
    commands = [engine_path]
    if weights:
        commands.append("-w")
        commands.append(weights)
    if threads:
        commands.append("-t")
        commands.append(threads)

    if len(commands) > 1:
        engine = chess.uci.popen_engine(commands)
    else:
        engine = chess.uci.popen_engine(engine_path)

    engine.uci()
    engine.position(board)

    info_handler = chess.uci.InfoHandler()
    engine.info_handlers.append(info_handler)

    return engine, info_handler


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


def get_engine_stats(handler):
    if "string" in handler.info:
        print("{}".format(handler.info["string"]))
    print("Depth: {}".format(handler.info["depth"]))
    print("nps: {}".format(handler.info["nps"]))
    print("Node: {}".format(handler.info["nodes"]))


def load_config():
    global CONFIG
    with open("./config.yml", 'r') as stream:
        CONFIG = yaml.load(stream)


if __name__ == "__main__":
    logger = logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='Play on Lichess with a bot')
    parser.add_argument('-u', action='store_true', help='Add this flag to upgrade your account to a bot account.')
    args = parser.parse_args()

    load_config()
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"])

    user_profile = li.get_profile()
    is_bot = user_profile.get("title") == "BOT"

    if args.u is True and is_bot is False:
        is_bot = upgrade_account(li)

    if is_bot:
        cfg = CONFIG["engine"]
        engine_path = os.path.join(cfg["dir"], cfg["name"])
        weights_path = os.path.join(cfg["dir"], cfg["weights"]) if "weights" in cfg else None
        start(li, user_profile, engine_path, weights_path, cfg.get("threads"))
    else:
        print("{} is not a bot account. Please upgrade your it to a bot account!".format(user_profile["username"]))
