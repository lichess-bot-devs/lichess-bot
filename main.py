import argparse
import chess
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
import yaml
import logging_pool
from conversation import Conversation, ChatLine

CONFIG = {}

def upgrade_account(li):
    if li.upgrade_to_bot_account() is None:
        return False

    print("Succesfully upgraded to Bot Account!")
    return True

def watch_control_stream(control_queue, li):
    with logging_pool.LoggingPool(CONFIG['max_concurrent_games']+1) as pool:
        for evnt in li.get_event_stream().iter_lines():
            if evnt:
                event = json.loads(evnt.decode('utf-8'))
                control_queue.put_nowait(event)

def start(li, user_profile, engine_path, weights=None, threads=None):
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
    with logging_pool.LoggingPool(CONFIG['max_concurrent_games']+1) as pool:
        events = li.get_event_stream().iter_lines()

        quit = False
        while not quit:
            event = control_queue.get()
            if event["type"] == "local_game_done":
                busy_processes -= 1
                print("+++ Process Free. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))
            elif event["type"] == "challenge":
                chlng = model.Challenge(event["challenge"])
                if len(challenge_queue) < CONFIG["max_queued_challenges"] and can_accept_challenge(chlng):
                    challenge_queue.append(chlng)
                    print("    Queue {}".format(chlng.show()))
                else:
                    print("    Decline {}".format(chlng.show()))
                    li.decline_challenge(chlng.id)
            elif event["type"] == "gameStart":
                if queued_processes <= 0:
                    print("Something went wrong. Game is starting and we don't have a queued process")
                else:
                    queued_processes -= 1
                game_id = event["game"]["id"]
                pool.apply_async(play_game, [li, game_id, engine_path, weights, threads, control_queue])
                busy_processes += 1
                print("--- Process Used. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))

            if (queued_processes + busy_processes) < CONFIG["max_concurrent_games"] and challenge_queue :
                chlng = challenge_queue.pop(0)
                print("    Accept {}".format(chlng.show()))
                response = li.accept_challenge(chlng.id)
                if response is not None:
                    # TODO: Probably warrants better checking.
                    queued_processes += 1
                    print("--- Process Queue. Total Queued: {}. Total Used: {}".format(queued_processes, busy_processes))

    control_stream.terminate()
    control_stream.join()


def play_game(li, game_id, engine_path, weights, threads, control_queue):
    username = li.get_profile()["username"]
    updates = li.get_game_stream(game_id).iter_lines()

    #Initial response of stream will be the full game info. Store it
    game = model.Game(json.loads(next(updates).decode('utf-8')), username, li.baseUrl)
    board = setup_board(game.state)
    engine = setup_engine(engine_path, board, weights, threads)
    conversation = Conversation(game, engine, li)

    print("+++ {}".format(game.show()))

    engine.pre_game(game)

    board = play_first_move(game, engine, board, li)

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
                if CONFIG.get("print_engine_stats"):
                    engine.print_stats()

    print("--- {} Game over".format(game.url()))
    engine.quit()
    # This can raise queue.NoFull, but that should only happen if we're not processing
    # events fast enough and in this case I believe the exception should be raised
    control_queue.put_nowait({"type": "local_game_done"})


def can_accept_challenge(chlng):
    return chlng.is_supported(CONFIG)


def play_first_move(game, engine, board, li):
    moves = game.state["moves"].split()
    if is_engine_move(game.is_white, moves):
        # need to hardcode first movetime since Lichess has 30 sec limit.
        best_move = engine.first_search(board, 2000)
        li.make_move(game.id, best_move)

    return board


def setup_board(state):
    board = chess.Board()
    moves = state["moves"].split()
    for move in moves:
        board = update_board(board, move)

    return board


def setup_engine(engine_path, board, weights=None, threads=None):
    # print("Loading Engine!")
    commands = [engine_path]
    if weights:
        commands.append("-w")
        commands.append(weights)
    if threads:
        commands.append("-t")
        commands.append(threads)

    global CONFIG
    if CONFIG["engine"].get("protocol") == "xboard":
        return engine_wrapper.XBoardEngine(board, commands)

    return engine_wrapper.UCIEngine(board, commands, CONFIG.get("ucioptions"))


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


def load_config():
    global CONFIG
    with open("./config.yml", 'r') as stream:
        try:
            CONFIG = yaml.load(stream)
        except e:
            print("There appears to be a syntax problem with your config.yml")
            raise e

        #[section, type, error message]
        sections = [["token", str, "Section `token` must be a string wrapped in quotes."],
                    ["url", str, "Section `url` must be a string wrapped in quotes."],
                    ["engine", dict, "Section `engine` must be a dictionary with indented keys followed by colons.."],
                    ["max_concurrent_games", int, "Section `max_concurrent_games` must be an integer number without quotes."],
                    ["max_queued_challenges", int, "Section `max_queued_challenges` must be an integer number without quotes."],
                    ["supported_tc", list, "Section `supported_tc` must be a list with indented entries starting with dashes.."],
                    ["supported_modes", list, "Section `supported_modes` must be a list with indented entries starting with dashes.."]]
        for section in sections:
            if section[0] not in CONFIG:
                raise Exception("Your config.yml does not have required section `{}`.".format(section))
            elif not isinstance(CONFIG[section[0]], section[1]):
                raise Exception(section[2])


        engine_sections = ["dir", "name"]
        for subsection in engine_sections:
            if subsection not in CONFIG["engine"]:
                raise Exception("Your config.yml does not have required `engine` subsection `{}`.".format(subsection))
            if not isinstance(CONFIG["engine"][subsection], str):
                raise Exception("Engine subsection `{}` must be a string wrapped in quotes.".format(subsection))

        if CONFIG["token"] == "xxxxxxxxxxxxxxxx":
            raise Exception("Your config.yml has the default Lichess API token. This is probably wrong.")

        if not os.path.isdir(CONFIG["engine"]["dir"]):
            raise Exception("Your engine directory `{}` is not a directory.")

        if not os.path.exists(CONFIG["engine"]["dir"] + CONFIG["engine"]["name"]):
            raise Exception("The engine specified does not exist.")

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
