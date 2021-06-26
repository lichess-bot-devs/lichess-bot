import argparse
import chess
from chess import engine
from chess import variant
import chess.polyglot
import engine_wrapper
import model
import json
import lichess
import logging
import multiprocessing
from multiprocessing import Process
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
import os
import threading

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
    logger.info("start")
    while not terminated:
        try:
            response = li.get_event_stream()
            lines = response.iter_lines()
            for line in lines:
                if line:
                    event = json.loads(line.decode('utf-8'))
                    control_queue.put_nowait(event)
                    logger.info(event)
        except:
            logger.info("except")
            pass

def start(li, user_profile, engine_factory, config):
    challenge_config = config["challenge"]
    max_games = challenge_config.get("concurrency", 1)
    logger.info("You're now connected to {} and awaiting challenges.".format(config["url"]))
    control_queue=multiprocessing.Manager().Queue()
    control_stream = Process(target=watch_control_stream, args=[control_queue,li])
    control_stream.start()
    gamesip=[]
    while not terminated:
        event=control_queue.get()
        if event["type"] == "terminated":
            break
        elif event["type"] == "challenge":
            logger.info("chlng detected")
            chlng = model.Challenge(event["challenge"])
            if chlng.is_supported(challenge_config):
                logger.info("chlng supported")
                try:
                    logger.info("    Accept {}".format(chlng))
                    response = li.accept_challenge(chlng.id)
                    ppp={"type":"gameStart", "game":{"id":chlng.id}}
                    control_queue.put_nowait(ppp)
                    logger.info(chlng.id)
                except (HTTPError, ReadTimeout) as exception:
                    if isinstance(exception, HTTPError) and exception.response.status_code == 404: # ignore missing challenge
                        logger.info("    Skip missing {}".format(chlng))
            else:
                try:
                    li.decline_challenge(chlng.id)
                    logger.info("    Decline {}".format(chlng))
                except:
                    pass
        elif event["type"] == "gameStart":
            logger.info("game detected")
            game_id = event["game"]["id"]
            gamesip.append(threading.Thread(target=play_game,args=(li, game_id, engine_factory, user_profile, config,)))
            gamesip[-1].start()
            
    logger.info("Terminated")
    control_stream.terminate()
    control_stream.join()

ponder_results = {}

@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=is_final)
def play_game(li, game_id, engine_factory, user_profile, config):
    li.chat(game_id,"player","Hello")
    li.chat(game_id,"spectator","Hi all!,")
    response = li.get_game_stream(game_id)
    lines = response.iter_lines()
    bullet=False
    #Initial response of stream will be the full game info. Store it
    initial_state = json.loads(next(lines).decode('utf-8'))
    game = model.Game(initial_state, user_profile["username"], li.baseUrl, config.get("abort_time", 10))
    timelim=game.state["btime"]/1000
    timelim=timelim/60
    if timelim>=0.5 and timelim<=2:
        bullet=True
    time=round(timelim/150*60,1)
    if time>6:
        time=6
    elif time<0.3:
        time=0.3
    if bullet:
        time=0.2
    board = setup_board(game)
    cfg = config["engine"]

    if type(board).uci_variant=="chess":
        engine_path = os.path.join(cfg["dir"], cfg["name"])
        bookname="book.bin"
    elif type(board).uci_variant=="atomic":
        engine_path = os.path.join(cfg["dir"], cfg["lcname"])
        bookname="bookchen.bin"
    else:
        engine_path = os.path.join(cfg["dir"], cfg["fairyname"])
        bookname="bookchen.bin"
    engineeng = engine.SimpleEngine.popen_uci(engine_path)

    logger.info("+++ {}".format(game))

    if is_engine_move(game, board.move_stack) and not is_game_over(game):
        with chess.polyglot.open_reader(bookname) as reader:
            movesob=[]
            weight=[]
            for entry in reader.find_all(board):
                movesob.append(entry.move)
                weight.append(entry.weight)
        if len(weight)==0:
            move=engineeng.play(board,engine.Limit(time=time))
            board.push(move.move)
            li.make_move(game.id, move.move)
        else:
            move=movesob[weight.index(max(weight))]
            board.push(move)
            li.make_move(game.id, move)

    with chess.polyglot.open_reader(bookname) as reader:
        while not terminated:
            try:
                binary_chunk = next(lines)
            except(StopIteration):
                break
            upd = json.loads(binary_chunk.decode('utf-8')) if binary_chunk else None
            u_type = upd["type"] if upd else "ping"
            if not board.is_game_over():
                if u_type == "gameState":
                    game.state=upd
                    moves = upd["moves"].split()
                    board = update_board(board, moves[-1])
                    if not is_game_over(game) and is_engine_move(game, moves):
                        moves=[]
                        weight=[]
                        for entry in reader.find_all(board):
                            moves.append(entry.move)
                            weight.append(entry.weight)
                        if len(weight)==0:
                            move=engineeng.play(board,engine.Limit(time=time))
                            board.push(move.move)
                            li.make_move(game.id, move.move)
                        else:
                            move=moves[weight.index(max(weight))]
                            board.push(move)
                            li.make_move(game.id, move)
                            
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
            else:
                logger.info("game over")
                engineeng.quit()
                break

def is_white_to_move(game, moves):
    return len(moves) % 2 == (0 if game.white_starts else 1)


def setup_board(game):
    if game.variant_name.lower() == "chess960":
        board = chess.Board(game.initial_fen, chess960=True)
    elif game.variant_name == "From Position":
        board = chess.Board(game.initial_fen)
    else:
        VariantBoard = variant.find_variant(game.variant_name)
        board = VariantBoard()
    moves = game.state["moves"].split()
    for move in moves:
        board = update_board(board, move)

    return board


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

if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Play on Lichess with a bot')
    parser.add_argument('-u', action='store_true', help='Add this flag to upgrade your account to a bot account.')
    parser.add_argument('-v', action='store_true', help='Verbose output. Changes log level from INFO to DEBUG.')
    parser.add_argument('--config', help='Specify a configuration file (defaults to ./config.yml)')
    parser.add_argument('-l', '--logfile', help="Log file to append logs to.", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO, filename=args.logfile,
                        format="%(asctime)-15s: %(message)s")
    logger.info(intro())
    CONFIG = load_config(args.config or "./config.yml")
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"], __version__)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    logger.info("Welcome {}!".format(username))

    if is_bot is False:
        is_bot = upgrade_account(li)

    if is_bot:
        engine_factory = partial(engine_wrapper.create_engine, CONFIG)
        start(li, user_profile, engine_factory, CONFIG)
    else:
        logger.error("{} is not a bot account. Please upgrade it to a bot account!".format(user_profile["username"]))
