import argparse
import chess
import chess.pgn
from chess.variant import find_variant
import engine_wrapper
import model
import matchmaking
import json
import lichess
import logging
import logging.handlers
import multiprocessing
import signal
import time
import backoff
import sys
import os
import io
import copy
import math
from config import load_config
from conversation import Conversation, ChatLine
from timer import Timer
from requests.exceptions import ChunkedEncodingError, ConnectionError, HTTPError, ReadTimeout
from rich.logging import RichHandler
from collections import defaultdict
from http.client import RemoteDisconnected

logger = logging.getLogger(__name__)

__version__ = "2022.11.22.2"

terminated = False
restart = True


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
                    event = json.loads(line.decode("utf-8"))
                    control_queue.put_nowait(event)
                else:
                    control_queue.put_nowait({"type": "ping"})
        except Exception:
            pass


def do_correspondence_ping(control_queue, period):
    while not terminated:
        time.sleep(period)
        control_queue.put_nowait({"type": "correspondence_ping"})


def logging_configurer(level, filename):
    console_handler = RichHandler()
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    all_handlers = [console_handler]

    if filename:
        file_handler = logging.FileHandler(filename, delay=True)
        FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
        file_formatter = logging.Formatter(FORMAT)
        file_handler.setFormatter(file_formatter)
        all_handlers.append(file_handler)

    logging.basicConfig(level=level,
                        handlers=all_handlers,
                        force=True)


def logging_listener_proc(queue, configurer, level, log_filename):
    configurer(level, log_filename)
    logger = logging.getLogger()
    while not terminated:
        try:
            logger.handle(queue.get())
        except Exception:
            pass


def game_logging_configurer(queue, level):
    if sys.platform == "win32":
        h = logging.handlers.QueueHandler(queue)
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(h)
        root.setLevel(level)


def game_error_handler(error):
    logger.exception("Game ended due to error:", exc_info=error)


def start(li, user_profile, config, logging_level, log_filename, one_game=False):
    logger.info(f"You're now connected to {config['url']} and awaiting challenges.")
    manager = multiprocessing.Manager()
    challenge_queue = manager.list()
    control_queue = manager.Queue()
    control_stream = multiprocessing.Process(target=watch_control_stream, args=[control_queue, li])
    control_stream.start()
    correspondence_cfg = config.get("correspondence") or {}
    correspondence_checkin_period = correspondence_cfg.get("checkin_period", 600)
    correspondence_pinger = multiprocessing.Process(target=do_correspondence_ping,
                                                    args=[control_queue,
                                                          correspondence_checkin_period])
    correspondence_pinger.start()
    correspondence_queue = manager.Queue()
    correspondence_queue.put("")

    logging_queue = manager.Queue()
    logging_listener = multiprocessing.Process(target=logging_listener_proc,
                                               args=(logging_queue,
                                                     logging_configurer,
                                                     logging_level,
                                                     log_filename))
    logging_listener.start()

    try:
        lichess_bot_main(li,
                         user_profile,
                         config,
                         logging_level,
                         log_filename,
                         challenge_queue,
                         control_queue,
                         correspondence_queue,
                         logging_queue,
                         one_game)
    finally:
        control_stream.terminate()
        control_stream.join()
        correspondence_pinger.terminate()
        correspondence_pinger.join()
        logging_listener.terminate()
        logging_listener.join()


def log_proc_count(change, active_games):
    symbol = "+++" if change == "Freed" else "---"
    logger.info(f"{symbol} Process {change}. Count: {len(active_games)}. IDs: {active_games or None}")


def lichess_bot_main(li,
                     user_profile,
                     config,
                     logging_level,
                     log_filename,
                     challenge_queue,
                     control_queue,
                     correspondence_queue,
                     logging_queue,
                     one_game):
    challenge_config = config["challenge"]
    max_games = challenge_config.get("concurrency", 1)

    one_game_completed = False

    all_games = li.get_ongoing_games()
    startup_correspondence_games = [game["gameId"]
                                    for game in all_games
                                    if game["speed"] == "correspondence"]
    active_games = set(game["gameId"]
                       for game in all_games
                       if game["gameId"] not in startup_correspondence_games)
    low_time_games = []

    last_check_online_time = Timer(60 * 60)  # one hour interval
    matchmaker = matchmaking.Matchmaking(li, config, user_profile)

    play_game_args = {"li": li,
                      "control_queue": control_queue,
                      "user_profile": user_profile,
                      "config": config,
                      "challenge_queue": challenge_queue,
                      "correspondence_queue": correspondence_queue,
                      "logging_queue": logging_queue,
                      "game_logging_configurer": game_logging_configurer,
                      "logging_level": logging_level}

    recent_bot_challenges = defaultdict(list)

    with multiprocessing.pool.Pool(max_games + 1) as pool:
        while not (terminated or (one_game and one_game_completed) or restart):
            event = next_event(control_queue)
            if not event:
                continue

            if event["type"] == "terminated":
                break
            elif event["type"] in ["local_game_done", "gameFinish"]:
                active_games.discard(event["game"]["id"])
                matchmaker.last_game_ended_delay.reset()
                log_proc_count("Freed", active_games)
                one_game_completed = True
            elif event["type"] == "challenge":
                handle_challenge(event, li, challenge_queue, challenge_config, user_profile, matchmaker, recent_bot_challenges, config)
            elif event["type"] == "challengeDeclined":
                matchmaker.declined_challenge(event)
            elif event["type"] == "gameStart":
                start_game(event,
                           pool,
                           play_game_args,
                           config,
                           matchmaker,
                           startup_correspondence_games,
                           correspondence_queue,
                           active_games,
                           low_time_games)

            start_low_time_games(low_time_games, active_games, max_games, pool, play_game_args)
            check_in_on_correspondence_games(pool,
                                             event,
                                             correspondence_queue,
                                             challenge_queue,
                                             play_game_args,
                                             active_games,
                                             max_games)
            accept_challenges(li, challenge_queue, active_games, max_games)
            matchmaker.challenge(active_games, challenge_queue)
            check_online_status(li, user_profile, last_check_online_time)

            control_queue.task_done()

    logger.info("Terminated")


def next_event(control_queue):
    try:
        event = control_queue.get()
    except InterruptedError:
        return {}

    if "type" not in event:
        log_bad_event(event)
        return {}

    if event.get("type") != "ping":
        logger.debug(f"Event: {event}")

    return event


wait_for_correspondence_ping = False


def check_in_on_correspondence_games(pool,
                                     event,
                                     correspondence_queue,
                                     challenge_queue,
                                     play_game_args,
                                     active_games,
                                     max_games):
    global wait_for_correspondence_ping

    is_correspondence_ping = event["type"] == "correspondence_ping"
    is_local_game_done = event["type"] == "local_game_done"
    if (is_correspondence_ping or (is_local_game_done and not wait_for_correspondence_ping)) and not challenge_queue:
        if is_correspondence_ping and wait_for_correspondence_ping:
            correspondence_queue.put("")

        wait_for_correspondence_ping = False
        while len(active_games) < max_games:
            game_id = correspondence_queue.get()
            # Stop checking in on games if we have checked in on all
            # games since the last correspondence_ping.
            if not game_id:
                if is_correspondence_ping and not correspondence_queue.empty():
                    correspondence_queue.put("")
                else:
                    wait_for_correspondence_ping = True
                    break
            else:
                active_games.add(game_id)
                log_proc_count("Used", active_games)
                play_game_args["game_id"] = game_id
                pool.apply_async(play_game,
                                 kwds=play_game_args,
                                 error_callback=game_error_handler)


def start_low_time_games(low_time_games, active_games, max_games, pool, play_game_args):
    low_time_games.sort(key=lambda g: g.get("secondsLeft", math.inf))
    while low_time_games and len(active_games) < max_games:
        game_id = low_time_games.pop(0)["id"]
        active_games.add(game_id)
        log_proc_count("Used", active_games)
        play_game_args["game_id"] = game_id
        pool.apply_async(play_game,
                         kwds=play_game_args,
                         error_callback=game_error_handler)


def accept_challenges(li, challenge_queue, active_games, max_games):
    while len(active_games) < max_games and challenge_queue:
        chlng = challenge_queue.pop(0)
        if chlng.from_self:
            continue

        try:
            logger.info(f"Accept {chlng}")
            li.accept_challenge(chlng.id)
            active_games.add(chlng.id)
            log_proc_count("Queued", active_games)
        except (HTTPError, ReadTimeout) as exception:
            if isinstance(exception, HTTPError) and exception.response.status_code == 404:
                logger.info(f"Skip missing {chlng}")


def check_online_status(li, user_profile, last_check_online_time):
    global restart

    if last_check_online_time.is_expired():
        if not li.is_online(user_profile["id"]):
            logger.info("Will restart lichess-bot")
            restart = True
        last_check_online_time.reset()


def sort_challenges(challenge_queue, challenge_config):
    if challenge_config.get("sort_by", "best") == "best":
        list_c = list(challenge_queue)
        list_c.sort(key=lambda c: -c.score())
        challenge_queue[:] = list_c


def start_game(event,
               pool,
               play_game_args,
               config,
               matchmaker,
               startup_correspondence_games,
               correspondence_queue,
               active_games,
               low_time_games):
    game_id = event["game"]["id"]
    if matchmaker.challenge_id == game_id:
        matchmaker.challenge_id = None
    if game_id in startup_correspondence_games:
        if enough_time_to_queue(event, config):
            logger.info(f'--- Enqueue {config["url"] + game_id}')
            correspondence_queue.put(game_id)
        else:
            logger.info(f'--- Will start {config["url"] + game_id} as soon as possible')
            low_time_games.append(event["game"])
        startup_correspondence_games.remove(game_id)
    else:
        active_games.add(game_id)
        log_proc_count("Used", active_games)
        play_game_args["game_id"] = game_id
        pool.apply_async(play_game,
                         kwds=play_game_args,
                         error_callback=game_error_handler)


def enough_time_to_queue(event, config):
    corr_cfg = config.get("correspondence") or {}
    checkin_time = corr_cfg.get("checkin_period") or 600
    move_time = corr_cfg.get("move_time") or 60
    minimum_time = (checkin_time + move_time) * 10
    game = event["game"]
    return not game["isMyTurn"] or game.get("secondsLeft", math.inf) > minimum_time


def handle_challenge(event, li, challenge_queue, challenge_config, user_profile, matchmaker, recent_bot_challenges ):
    chlng = model.Challenge(event["challenge"], user_profile)

    time_window = challenge_config.get('recent_bot_challenge_age', None)
    max_recent_challenges = challenge_config.get('max_recent_bot_challenges')

    is_supported, decline_reason = chlng.is_supported(challenge_config)

    if is_supported and chlng.challenger_is_bot and time_window is not None and max_recent_challenges is not None:
        op = chlng.challenger_name
        # Filter out old challenges
        recent_bot_challenges[op] = [t for t in recent_bot_challenges[op] if not t.is_expired()]
        if len(recent_bot_challenges[op]) >= max_recent_challenges:
            is_supported = False
            decline_reason = "later"
        else:
            recent_bot_challenges[op].append(Timer(time_window))

    if is_supported:
        challenge_queue.append(chlng)
        sort_challenges(challenge_queue, challenge_config)
    elif chlng.id != matchmaker.challenge_id:
        li.decline_challenge(chlng.id, reason=decline_reason)


def log_bad_event(event):
    logger.warning("Unable to handle response from lichess.org:")
    logger.warning(event)
    if event.get("error") == "Missing scope":
        logger.warning('Please check that the API access token for your bot has the scope "Play games with the bot API".')


@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=is_final)
def play_game(li,
              game_id,
              control_queue,
              user_profile,
              config,
              challenge_queue,
              correspondence_queue,
              logging_queue,
              game_logging_configurer,
              logging_level):

    game_logging_configurer(logging_queue, logging_level)
    logger = logging.getLogger(__name__)

    response = li.get_game_stream(game_id)
    lines = response.iter_lines()

    # Initial response of stream will be the full game info. Store it
    initial_state = json.loads(next(lines).decode("utf-8"))
    logger.debug(f"Initial state: {initial_state}")
    abort_time = config.get("abort_time", 20)
    game = model.Game(initial_state, user_profile["username"], li.baseUrl, abort_time)

    engine = engine_wrapper.create_engine(config)
    engine.get_opponent_info(game)
    conversation = Conversation(game, engine, li, __version__, challenge_queue)

    logger.info(f"+++ {game}")

    is_correspondence = game.speed == "correspondence"
    correspondence_cfg = config.get("correspondence") or {}
    correspondence_move_time = correspondence_cfg.get("move_time", 60) * 1000
    correspondence_disconnect_time = correspondence_cfg.get("disconnect_time", 300)

    engine_cfg = config["engine"]
    ponder_cfg = correspondence_cfg if is_correspondence else engine_cfg
    can_ponder = ponder_cfg.get("uci_ponder", False) or ponder_cfg.get("ponder", False)
    move_overhead = config.get("move_overhead", 1000)
    delay_seconds = config.get("rate_limiting_delay", 0)/1000

    greeting_cfg = config.get("greeting") or {}
    keyword_map = defaultdict(str, me=game.me.name, opponent=game.opponent.name)
    hello = get_greeting("hello", greeting_cfg, keyword_map)
    goodbye = get_greeting("goodbye", greeting_cfg, keyword_map)
    hello_spectators = get_greeting("hello_spectators", greeting_cfg, keyword_map)
    goodbye_spectators = get_greeting("goodbye_spectators", greeting_cfg, keyword_map)

    disconnect_time = correspondence_disconnect_time if not game.state.get("moves") else 0
    prior_game = None
    upd = game.state
    while not terminated:
        move_attempted = False
        try:
            upd = upd or next_update(lines)
            u_type = upd["type"] if upd else "ping"
            if u_type == "chatLine":
                conversation.react(ChatLine(upd), game)
            elif u_type == "gameState":
                game.state = upd
                board = setup_board(game)
                if not is_game_over(game) and is_engine_move(game, prior_game, board):
                    disconnect_time = correspondence_disconnect_time
                    say_hello(conversation, hello, hello_spectators, board)
                    start_time = time.perf_counter_ns()
                    fake_thinking(config, board, game)
                    print_move_number(board)
                    move_attempted = True
                    engine.play_move(board,
                                     game,
                                     li,
                                     start_time,
                                     move_overhead,
                                     can_ponder,
                                     is_correspondence,
                                     correspondence_move_time,
                                     engine_cfg)
                    time.sleep(delay_seconds)
                elif is_game_over(game):
                    engine.report_game_result(game, board)
                    tell_user_game_result(game, board)
                    conversation.send_message("player", goodbye)
                    conversation.send_message("spectator", goodbye_spectators)

                wb = "w" if board.turn == chess.WHITE else "b"
                terminate_time = (upd[f"{wb}time"] + upd[f"{wb}inc"]) / 1000 + 60
                game.ping(abort_time, terminate_time, disconnect_time)
                prior_game = copy.deepcopy(game)
            elif u_type == "ping" and should_exit_game(board, game, prior_game, li, is_correspondence):
                break
        except (HTTPError, ReadTimeout, RemoteDisconnected, ChunkedEncodingError, ConnectionError, StopIteration) as e:
            stopped = isinstance(e, StopIteration)
            is_ongoing = game.id in (ongoing_game["gameId"] for ongoing_game in li.get_ongoing_games())
            if stopped or (not move_attempted and not is_ongoing):
                break
        finally:
            upd = None

    engine.stop()
    engine.quit()

    try_print_pgn_game_record(li, config, game, board, engine)
    final_queue_entries(control_queue, correspondence_queue, game, is_correspondence)


def get_greeting(greeting, greeting_cfg, keyword_map):
    return str(greeting_cfg.get(greeting) or "").format_map(keyword_map)


def say_hello(conversation, hello, hello_spectators, board):
    if len(board.move_stack) < 2:
        conversation.send_message("player", hello)
        conversation.send_message("spectator", hello_spectators)


def fake_thinking(config, board, game):
    if config.get("fake_think_time") and len(board.move_stack) > 9:
        delay = min(game.clock_initial, game.my_remaining_seconds()) * 0.015
        accel = 1 - max(0, min(100, len(board.move_stack) - 20)) / 150
        sleep = min(5, delay * accel)
        time.sleep(sleep)


def print_move_number(board):
    logger.info("")
    logger.info(f"move: {len(board.move_stack) // 2 + 1}")


def next_update(lines):
    binary_chunk = next(lines)
    upd = json.loads(binary_chunk.decode("utf-8")) if binary_chunk else None
    if upd:
        logger.debug(f"Game state: {upd}")
    return upd


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
        except ValueError:
            logger.exception(f"Ignoring illegal move {move} on board {board.fen()}")

    return board


def is_engine_move(game, prior_game, board):
    return game_changed(game, prior_game) and game.is_white == (board.turn == chess.WHITE)


def is_game_over(game):
    return game.state["status"] != "started"


def should_exit_game(board, game, prior_game, li, is_correspondence):
    if (is_correspondence
            and not is_engine_move(game, prior_game, board)
            and game.should_disconnect_now()):
        return True
    elif game.should_abort_now():
        logger.info(f"Aborting {game.url()} by lack of activity")
        li.abort(game.id)
        return True
    elif game.should_terminate_now():
        logger.info(f"Terminating {game.url()} by lack of activity")
        if game.is_abortable():
            li.abort(game.id)
        return True
    else:
        return False


def final_queue_entries(control_queue, correspondence_queue, game, is_correspondence):
    if is_correspondence and not is_game_over(game):
        logger.info(f"--- Disconnecting from {game.url()}")
        correspondence_queue.put(game.id)
    else:
        logger.info(f"--- {game.url()} Game over")

    control_queue.put_nowait({"type": "local_game_done", "game": {"id": game.id}})


def game_changed(current_game, prior_game):
    if prior_game is None:
        return True

    return current_game.state["moves"] != prior_game.state["moves"]


def tell_user_game_result(game, board):
    winner = game.state.get("winner")
    termination = game.state.get("status")

    winning_name = game.white.name if winner == "white" else game.black.name
    losing_name = game.white.name if winner == "black" else game.black.name

    if winner is not None:
        logger.info(f"{winning_name} won!")
    elif termination == engine_wrapper.Termination.DRAW:
        logger.info("Game ended in draw.")
    else:
        logger.info("Game adjourned.")

    simple_endings = {engine_wrapper.Termination.MATE: "Game won by checkmate.",
                      engine_wrapper.Termination.TIMEOUT: f"{losing_name} forfeited on time.",
                      engine_wrapper.Termination.RESIGN: f"{losing_name} resigned.",
                      engine_wrapper.Termination.ABORT: "Game aborted."}

    if termination in simple_endings:
        logger.info(simple_endings[termination])
    elif termination == engine_wrapper.Termination.DRAW:
        if board.is_fifty_moves():
            logger.info("Game drawn by 50-move rule.")
        elif board.is_repetition():
            logger.info("Game drawn by threefold repetition.")
        else:
            logger.info("Game drawn by agreement.")
    elif termination:
        logger.info(f"Game ended by {termination}")


def try_print_pgn_game_record(li, config, game, board, engine):
    try:
        print_pgn_game_record(li, config, game, board, engine)
    except Exception:
        logger.exception("Error writing game record:")


def print_pgn_game_record(li, config, game, board, engine):
    game_directory = config.get("pgn_directory")
    if not game_directory:
        return

    try:
        os.mkdir(game_directory)
    except FileExistsError:
        pass

    game_file_name = f"{game.white.name} vs {game.black.name} - {game.id}.pgn"
    game_file_name = "".join(c for c in game_file_name if c not in '<>:"/\\|?*')
    game_path = os.path.join(game_directory, game_file_name)

    lichess_game_record = chess.pgn.read_game(io.StringIO(li.get_game_pgn(game.id)))
    try:
        # Recall previously written PGN file to retain engine evaluations.
        with open(game_path) as game_data:
            game_record = chess.pgn.read_game(game_data)
        game_record.headers.update(lichess_game_record.headers)
    except FileNotFoundError:
        game_record = lichess_game_record

    current_node = game_record.game()
    lichess_node = lichess_game_record.game()
    for index, move in enumerate(board.move_stack):
        if current_node.is_end() or current_node.next().move != move:
            current_node = current_node.add_main_variation(move)
        else:
            current_node = current_node.next()

        if not lichess_node.is_end():
            lichess_node = lichess_node.next()
            current_node.set_clock(lichess_node.clock())
            if current_node.comment != lichess_node.comment:
                current_node.comment = f"{current_node.comment} {lichess_node.comment}".strip()

        commentary = engine.comment_for_board_index(index)
        pv_node = current_node.parent.add_line(commentary["pv"]) if "pv" in commentary else current_node
        pv_node.set_eval(commentary.get("score"), commentary.get("depth"))

    with open(game_path, "w") as game_record_destination:
        pgn_writer = chess.pgn.FileExporter(game_record_destination)
        game_record.accept(pgn_writer)


def intro():
    return fr"""
    .   _/|
    .  // o\
    .  || ._)  lichess-bot {__version__}
    .  //__\
    .  )___(   Play on Lichess with a bot
    """


def start_lichess_bot():
    parser = argparse.ArgumentParser(description="Play on Lichess with a bot")
    parser.add_argument("-u", action="store_true", help="Upgrade your account to a bot account.")
    parser.add_argument("-v", action="store_true", help="Make output more verbose. Include all communication with lichess.")
    parser.add_argument("--config", help="Specify a configuration file (defaults to ./config.yml).")
    parser.add_argument("-l", "--logfile", help="Record all console output to a log file.", default=None)
    args = parser.parse_args()

    logging_level = logging.DEBUG if args.v else logging.INFO
    logging_configurer(logging_level, args.logfile)
    logger.info(intro(), extra={"highlighter": None})
    CONFIG = load_config(args.config or "./config.yml")
    max_retries = (CONFIG["engine"].get("online_moves") or {}).get("max_retries") or 2
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"], __version__, logging_level, max_retries)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    logger.info(f"Welcome {username}!")

    if args.u and not is_bot:
        is_bot = upgrade_account(li)

    if is_bot:
        start(li, user_profile, CONFIG, logging_level, args.logfile)
    else:
        logger.error(f"{username} is not a bot account. Please upgrade it to a bot account!")


if __name__ == "__main__":
    try:
        while restart:
            restart = False
            start_lichess_bot()
            time.sleep(10 if restart else 0)
    except Exception:
        logger.exception("Quitting lichess-bot due to an error:")
