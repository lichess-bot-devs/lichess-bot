"""The main module that controls lichess-bot."""
import argparse
import chess
import chess.pgn
from chess.variant import find_variant
from lib import engine_wrapper, model, lichess, matchmaking
import json
import logging
import logging.handlers
import multiprocessing
import signal
import time
import datetime
import backoff
import os
import io
import copy
import math
import sys
import yaml
import traceback
import itertools
import glob
import platform
import importlib.metadata
import contextlib
from lib.config import load_config, Configuration, log_config
from lib.conversation import Conversation, ChatLine
from lib.timer import Timer, seconds, msec, hours, to_seconds
from lib.lichess_types import (UserProfileType, EventType, GameType, GameEventType, CONTROL_QUEUE_TYPE,
                               CORRESPONDENCE_QUEUE_TYPE, LOGGING_QUEUE_TYPE, PGN_QUEUE_TYPE)
from requests.exceptions import ChunkedEncodingError, ConnectionError as RequestsConnectionError, HTTPError, ReadTimeout
from rich.logging import RichHandler
from collections import defaultdict
from collections.abc import Iterator, MutableSequence
from http.client import RemoteDisconnected
from queue import Empty
from multiprocessing.pool import Pool
from collections import Counter
from typing import Optional, Union, TypedDict, cast
from types import FrameType
MULTIPROCESSING_LIST_TYPE = MutableSequence[model.Challenge]
POOL_TYPE = Pool


class PlayGameArgsType(TypedDict, total=False):
    """Type hint for `play_game_args`."""

    li: lichess.Lichess
    control_queue: CONTROL_QUEUE_TYPE
    user_profile: UserProfileType
    config: Configuration
    challenge_queue: MULTIPROCESSING_LIST_TYPE
    correspondence_queue: CORRESPONDENCE_QUEUE_TYPE
    logging_queue: LOGGING_QUEUE_TYPE
    pgn_queue: PGN_QUEUE_TYPE
    game_id: str


class VersioningType(TypedDict):
    """Type hint for the versioning information from lib/versioning.yml."""

    lichess_bot_version: str
    minimum_python_version: str
    deprecated_python_version: str
    deprecation_date: datetime.date


logger = logging.getLogger(__name__)

with open("lib/versioning.yml") as version_file:
    versioning_info: VersioningType = yaml.safe_load(version_file)

__version__ = versioning_info["lichess_bot_version"]

terminated = False
force_quit = False
restart = True


def should_restart() -> bool:
    """Decide whether to restart lichess-bot when exiting main program."""
    return restart


def disable_restart() -> None:
    """Disable restarting lichess-bot when errors occur. Used during testing."""
    global restart
    restart = False


def signal_handler(signal: int, frame: Optional[FrameType]) -> None:  # noqa: ARG001
    """Terminate lichess-bot."""
    global terminated
    global force_quit
    in_starting_thread = __name__ == "__main__"
    if not terminated:
        if in_starting_thread:
            logger.debug("Received SIGINT. Terminating client.")
        terminated = True
    else:
        if in_starting_thread:
            logger.debug("Received second SIGINT. Quitting now.")
        force_quit = True


signal.signal(signal.SIGINT, signal_handler)


def upgrade_account(li: lichess.Lichess) -> bool:
    """Upgrade the account to a BOT account."""
    try:
        li.upgrade_to_bot_account()
    except HTTPError:
        logger.exception("Failed to upgrade to Bot Account.")
        return False

    logger.info("Successfully upgraded to Bot Account!")
    return True


def watch_control_stream(control_queue: CONTROL_QUEUE_TYPE, li: lichess.Lichess) -> None:
    """Put the events in a queue."""
    error = None
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
            error = traceback.format_exc()
            break

    control_queue.put_nowait({"type": "terminated", "error": error})


def do_correspondence_ping(control_queue: CONTROL_QUEUE_TYPE, period: datetime.timedelta) -> None:
    """
    Tell the engine to check the correspondence games.

    :param period: How many seconds to wait before sending a correspondence ping.
    """
    while not terminated:
        time.sleep(to_seconds(period))
        control_queue.put_nowait({"type": "correspondence_ping"})


def write_pgn_records(pgn_queue: PGN_QUEUE_TYPE, config: Configuration, username: str) -> None:
    """Write PGN records to files as games finish."""
    while True:
        mark_task_done = False
        try:
            event = pgn_queue.get()
            mark_task_done = True
            save_pgn_record(event, config, username)
        except InterruptedError:
            pass
        except Exception:
            logger.exception("Could not write PGN to file")

        if mark_task_done:
            pgn_queue.task_done()


def logging_configurer(level: int, filename: Optional[str], disable_auto_logs: bool) -> None:
    """
    Configure the logger.

    :param level: The logging level. Either `logging.INFO` or `logging.DEBUG`.
    :param filename: The filename to write the logs to. If it is `None` then the logs aren't written to a file.
    :param auto_log_filename: The filename for the automatic logger. If it is `None` then the logs aren't written to a file.
    """
    console_handler = RichHandler()
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    all_handlers: list[logging.Handler] = [console_handler]

    if filename:
        file_handler = logging.FileHandler(filename, delay=True, encoding="utf-8")
        FORMAT = "%(asctime)s %(name)s (%(filename)s:%(lineno)d) %(levelname)s %(message)s"
        file_formatter = logging.Formatter(FORMAT)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        all_handlers.append(file_handler)

    if not disable_auto_logs:
        os.makedirs(auto_log_directory, exist_ok=True)

        # Set up automatic logging.
        auto_log_filename = os.path.join(auto_log_directory, "lichess-bot.log")
        auto_file_handler = logging.handlers.TimedRotatingFileHandler(auto_log_filename,
                                                                      delay=True,
                                                                      encoding="utf-8",
                                                                      when="midnight",
                                                                      backupCount=7)
        auto_file_handler.setLevel(logging.DEBUG)

        FORMAT = "%(asctime)s %(name)s (%(filename)s:%(lineno)d) %(levelname)s %(message)s"
        file_formatter = logging.Formatter(FORMAT)
        auto_file_handler.setFormatter(file_formatter)
        all_handlers.append(auto_file_handler)

    logging.basicConfig(level=logging.DEBUG,
                        handlers=all_handlers,
                        force=True)


def logging_listener_proc(queue: LOGGING_QUEUE_TYPE, level: int, log_filename: Optional[str],
                          disable_auto_logging: bool) -> None:
    """
    Handle events from the logging queue.

    This allows the logs from inside a thread to be printed.
    They are added to the queue, so they are printed outside the thread.
    """
    logging_configurer(level, log_filename, disable_auto_logging)
    logger = logging.getLogger()
    while True:
        task: Optional[logging.LogRecord] = None
        try:
            task = queue.get(block=False)
        except Empty:
            time.sleep(0.1)
        except InterruptedError:
            pass
        except Exception:  # noqa: S110
            pass

        if task is None:
            continue

        logger.handle(task)
        queue.task_done()


def thread_logging_configurer(queue: LOGGING_QUEUE_TYPE) -> None:
    """Configure the game logger."""
    h = logging.handlers.QueueHandler(queue)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(h)
    root.setLevel(logging.DEBUG)


def start(li: lichess.Lichess, user_profile: UserProfileType, config: Configuration, logging_level: int,
          log_filename: Optional[str], disable_auto_logging: bool, one_game: bool = False) -> None:
    """
    Start lichess-bot.

    :param li: Provides communication with lichess.org.
    :param user_profile: Information on our bot.
    :param config: The config that the bot will use.
    :param logging_level: The logging level. Either `logging.INFO` or `logging.DEBUG`.
    :param log_filename: The filename to write the logs to. If it is `None` then the logs aren't written to a file.
    :param auto_log_filename: The filename for the automatic logger. If it is `None` then the logs aren't written to a file.
    :param one_game: Whether the bot should play only one game. Only used in `test_bot/test_bot.py` to test lichess-bot.
    """
    logger.info(f"You're now connected to {config.url} and awaiting challenges.")
    manager = multiprocessing.Manager()
    challenge_queue: MULTIPROCESSING_LIST_TYPE = manager.list()
    control_queue: CONTROL_QUEUE_TYPE = manager.Queue()
    control_stream = multiprocessing.Process(target=watch_control_stream, args=(control_queue, li))
    control_stream.start()
    correspondence_pinger = multiprocessing.Process(target=do_correspondence_ping,
                                                    args=(control_queue,
                                                          seconds(config.correspondence.checkin_period)))
    correspondence_pinger.start()
    correspondence_queue: CORRESPONDENCE_QUEUE_TYPE = manager.Queue()

    logging_queue = manager.Queue()
    logging_listener = multiprocessing.Process(target=logging_listener_proc,
                                               args=(logging_queue,
                                                     logging_level,
                                                     log_filename,
                                                     disable_auto_logging))
    logging_listener.start()

    pgn_queue = manager.Queue()
    pgn_listener = multiprocessing.Process(target=write_pgn_records,
                                           args=(pgn_queue,
                                                 config,
                                                 user_profile["username"]))
    pgn_listener.start()

    thread_logging_configurer(logging_queue)

    try:
        lichess_bot_main(li,
                         user_profile,
                         config,
                         challenge_queue,
                         control_queue,
                         correspondence_queue,
                         logging_queue,
                         pgn_queue,
                         one_game)
    finally:
        control_stream.terminate()
        control_stream.join()
        correspondence_pinger.terminate()
        correspondence_pinger.join()
        time.sleep(1.0)  # Allow final messages in logging_queue to be handled.
        logging_configurer(logging_level, log_filename, disable_auto_logging)
        logging_listener.terminate()
        logging_listener.join()
        pgn_listener.terminate()
        pgn_listener.join()


def log_proc_count(change: str, active_games: set[str]) -> None:
    """
    Log the number of active games and their IDs.

    :param change: Either "Freed", "Used", or "Queued".
    :param active_games: A set containing the IDs of the active games.
    """
    symbol = "+++" if change == "Freed" else "---"
    logger.info(f"{symbol} Process {change}. Count: {len(active_games)}. IDs: {active_games or None}")


def lichess_bot_main(li: lichess.Lichess,
                     user_profile: UserProfileType,
                     config: Configuration,
                     challenge_queue: MULTIPROCESSING_LIST_TYPE,
                     control_queue: CONTROL_QUEUE_TYPE,
                     correspondence_queue: CORRESPONDENCE_QUEUE_TYPE,
                     logging_queue: LOGGING_QUEUE_TYPE,
                     pgn_queue: PGN_QUEUE_TYPE,
                     one_game: bool) -> None:
    """
    Handle all the games and challenges.

    :param li: Provides communication with lichess.org.
    :param user_profile: Information on our bot.
    :param config: The config that the bot will use.
    :param challenge_queue: The queue containing the challenges.
    :param control_queue: The queue containing all the events.
    :param correspondence_queue: The queue containing the correspondence games.
    :param logging_queue: The logging queue. Used by `logging_listener_proc`.
    :param one_game: Whether the bot should play only one game. Only used in `test_bot/test_bot.py` to test lichess-bot.
    """
    global restart

    max_games = config.challenge.concurrency

    one_game_completed = False

    all_games = li.get_ongoing_games()
    prune_takeback_records(all_games)
    startup_correspondence_games = [game["gameId"]
                                    for game in all_games
                                    if game["speed"] == "correspondence"]
    active_games = {game["gameId"]
                    for game in all_games
                    if game["gameId"] not in startup_correspondence_games}
    low_time_games: list[GameType] = []

    last_check_online_time = Timer(hours(1))
    matchmaker = matchmaking.Matchmaking(li, config, user_profile)
    matchmaker.show_earliest_challenge_time()

    play_game_args = PlayGameArgsType(li=li, control_queue=control_queue, user_profile=user_profile,
                                      config=config, challenge_queue=challenge_queue,
                                      correspondence_queue=correspondence_queue, logging_queue=logging_queue,
                                      pgn_queue=pgn_queue)

    recent_bot_challenges: defaultdict[str, list[Timer]] = defaultdict(list)

    if config.quit_after_all_games_finish:
        logger.info("When quitting, lichess-bot will first wait for all running games to finish.")
        logger.info("Press Ctrl-C twice to quit immediately.")

    with multiprocessing.pool.Pool(max_games + 1) as pool:
        while not (terminated or (one_game and one_game_completed) or restart):
            event = next_event(control_queue)
            if not event:
                continue

            if event["type"] == "terminated":
                restart = True
                logger.debug(f"Terminating exception:\n{event['error']}")
                control_queue.task_done()
                break

            if event["type"] == "local_game_done":
                active_games.discard(event["game"]["id"])
                matchmaker.game_done()
                log_proc_count("Freed", active_games)
                one_game_completed = True
            elif event["type"] == "challenge":
                handle_challenge(event, li, challenge_queue, config.challenge, user_profile, recent_bot_challenges)
            elif event["type"] == "challengeDeclined":
                matchmaker.declined_challenge(event)
            elif event["type"] == "gameStart":
                matchmaker.accepted_challenge(event)
                start_game(event,
                           pool,
                           play_game_args,
                           config,
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
            matchmaker.challenge(active_games, challenge_queue, max_games)
            check_online_status(li, user_profile, last_check_online_time)

            control_queue.task_done()

        close_pool(pool, active_games, config)


def close_pool(pool: POOL_TYPE, active_games: set[str], config: Configuration) -> None:
    """Shut down pool after possibly waiting on games to finish depending on the configuration."""
    if config.quit_after_all_games_finish:
        if active_games:
            logger.info("Waiting for games to finish before quitting.")
        pool.close()
        pool.join()


def next_event(control_queue: CONTROL_QUEUE_TYPE) -> EventType:
    """Get the next event from the control queue."""
    try:
        event = control_queue.get()
        if event is None:
            return {}
    except InterruptedError:
        return {}

    if "type" not in event:
        logger.warning("Unable to handle response from lichess.org:")
        logger.warning(event)
        control_queue.task_done()
        return {}

    if event.get("type") != "ping":
        logger.debug(f"Event: {event}")

    return event


correspondence_games_to_start = 0


def check_in_on_correspondence_games(pool: POOL_TYPE,
                                     event: EventType,
                                     correspondence_queue: CORRESPONDENCE_QUEUE_TYPE,
                                     challenge_queue: MULTIPROCESSING_LIST_TYPE,
                                     play_game_args: PlayGameArgsType,
                                     active_games: set[str],
                                     max_games: int) -> None:
    """Start correspondence games."""
    global correspondence_games_to_start

    if event["type"] == "correspondence_ping":
        correspondence_games_to_start = correspondence_queue.qsize()
    elif event["type"] != "local_game_done":
        return

    if challenge_queue:
        return

    while len(active_games) < max_games and correspondence_games_to_start > 0:
        game_id = correspondence_queue.get_nowait()
        correspondence_games_to_start -= 1
        correspondence_queue.task_done()
        start_game_thread(active_games, game_id, play_game_args, pool)


def start_low_time_games(low_time_games: list[GameType], active_games: set[str], max_games: int,
                         pool: POOL_TYPE, play_game_args: PlayGameArgsType) -> None:
    """Start the games based on how much time we have left."""
    low_time_games.sort(key=lambda g: g.get("secondsLeft", math.inf))
    while low_time_games and len(active_games) < max_games:
        game_id = low_time_games.pop(0)["id"]
        start_game_thread(active_games, game_id, play_game_args, pool)


def accept_challenges(li: lichess.Lichess, challenge_queue: MULTIPROCESSING_LIST_TYPE, active_games: set[str],
                      max_games: int) -> None:
    """Accept a challenge."""
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
            if isinstance(exception, HTTPError) and exception.response is not None and exception.response.status_code == 404:
                logger.info(f"Skip missing {chlng}")


def check_online_status(li: lichess.Lichess, user_profile: UserProfileType, last_check_online_time: Timer) -> None:
    """Check if lichess.org thinks the bot is online or not. If it isn't, we restart it."""
    global restart

    if last_check_online_time.is_expired():
        try:
            if not li.is_online(user_profile["id"]):
                logger.info("Will restart lichess-bot")
                restart = True
            last_check_online_time.reset()
        except (HTTPError, ReadTimeout):
            pass


def sort_challenges(challenge_queue: MULTIPROCESSING_LIST_TYPE, challenge_config: Configuration) -> None:
    """
    Sort the challenges.

    They can be sorted either by rating (the best challenger is accepted first),
    or by time (the first challenger is accepted first). The bot can also
    prioritize playing against humans or bots.
    """
    challenge_list = list(challenge_queue)
    if challenge_config.sort_by == "best":
        challenge_list.sort(key=lambda challenger: challenger.score(), reverse=True)
    if challenge_config.preference != "none":
        challenge_list.sort(key=lambda challenger: challenger.challenger.is_bot, reverse=challenge_config.preference == "bot")
    challenge_queue[:] = challenge_list


def game_is_active(li: lichess.Lichess, game_id: str) -> bool:
    """Determine if a game is still being played."""
    return game_id in (ongoing_game["gameId"] for ongoing_game in li.get_ongoing_games())


def start_game_thread(active_games: set[str], game_id: str, play_game_args: PlayGameArgsType, pool: POOL_TYPE) -> None:
    """Start a game thread."""
    active_games.add(game_id)
    log_proc_count("Used", active_games)
    play_game_args["game_id"] = game_id

    def game_error_handler(error: BaseException) -> None:
        logger.exception("Game ended due to error:", exc_info=error)
        control_queue = play_game_args["control_queue"]
        pgn_queue = play_game_args["pgn_queue"]
        li = play_game_args["li"]
        control_queue.put_nowait({"type": "local_game_done", "game": {"id": game_id}})
        pgn_queue.put_nowait({"game": {"id": game_id,
                                       "pgn": li.get_game_pgn(game_id),
                                       "complete": not game_is_active(li, game_id)}})

    pool.apply_async(play_game,
                     kwds=play_game_args,
                     error_callback=game_error_handler)


def start_game(event: EventType,
               pool: POOL_TYPE,
               play_game_args: PlayGameArgsType,
               config: Configuration,
               startup_correspondence_games: list[str],
               correspondence_queue: CORRESPONDENCE_QUEUE_TYPE,
               active_games: set[str],
               low_time_games: list[GameType]) -> None:
    """
    Start a game.

    :param event: The gameStart event.
    :param pool: The thread pool that the game is added to, so they can be run asynchronously.
    :param play_game_args: The args passed to `play_game`.
    :param config: The config the bot will use.
    :param startup_correspondence_games: A list of correspondence games that have to be started.
    :param correspondence_queue: The queue that correspondence games are added to, to be started.
    :param active_games: A set of all the games that aren't correspondence games.
    :param low_time_games: A list of games, in which we don't have much time remaining.
    """
    game_id = event["game"]["id"]
    if game_id in startup_correspondence_games:
        if enough_time_to_queue(event, config):
            logger.info(f"--- Enqueue {config.url + game_id}")
            correspondence_queue.put_nowait(game_id)
        else:
            logger.info(f"--- Will start {config.url + game_id} as soon as possible")
            low_time_games.append(event["game"])
        startup_correspondence_games.remove(game_id)
    else:
        start_game_thread(active_games, game_id, play_game_args, pool)


def enough_time_to_queue(event: EventType, config: Configuration) -> bool:
    """Check whether the correspondence must be started now or if it can wait."""
    corr_cfg = config.correspondence
    minimum_time = (corr_cfg.checkin_period + corr_cfg.move_time) * 10
    game = event["game"]
    return not game["isMyTurn"] or game.get("secondsLeft", math.inf) > minimum_time


def handle_challenge(event: EventType, li: lichess.Lichess, challenge_queue: MULTIPROCESSING_LIST_TYPE,
                     challenge_config: Configuration, user_profile: UserProfileType,
                     recent_bot_challenges: defaultdict[str, list[Timer]]) -> None:
    """Handle incoming challenges. It either accepts, declines, or queues them to accept later."""
    chlng = model.Challenge(event["challenge"], user_profile)
    if chlng.from_self:
        return

    players_with_active_games = Counter(game["opponent"]["username"] for game in li.get_ongoing_games())

    is_supported, decline_reason = chlng.is_supported(challenge_config, recent_bot_challenges, players_with_active_games)
    if is_supported:
        challenge_queue.append(chlng)
        sort_challenges(challenge_queue, challenge_config)
        time_window = challenge_config.recent_bot_challenge_age
        if time_window is not None:
            recent_bot_challenges[chlng.challenger.name].append(Timer(seconds(time_window)))
    else:
        li.decline_challenge(chlng.id, reason=decline_reason)


@backoff.on_exception(backoff.expo, BaseException, max_time=600, giveup=lichess.is_final,  # type: ignore[arg-type]
                      on_backoff=lichess.backoff_handler)
def play_game(li: lichess.Lichess,
              game_id: str,
              control_queue: CONTROL_QUEUE_TYPE,
              user_profile: UserProfileType,
              config: Configuration,
              challenge_queue: MULTIPROCESSING_LIST_TYPE,
              correspondence_queue: CORRESPONDENCE_QUEUE_TYPE,
              logging_queue: LOGGING_QUEUE_TYPE,
              pgn_queue: PGN_QUEUE_TYPE) -> None:
    """
    Play a game.

    :param li: Provides communication with lichess.org.
    :param game_id: The id of the game.
    :param control_queue: The control queue that contains events (adds `local_game_done` to the queue).
    :param user_profile: Information on our bot.
    :param config: The config that the bot will use.
    :param challenge_queue: The queue containing the challenges.
    :param correspondence_queue: The queue containing the correspondence games.
    :param logging_queue: The logging queue. Used by `logging_listener_proc`.
    """
    thread_logging_configurer(logging_queue)
    logger = logging.getLogger(__name__)

    response = li.get_game_stream(game_id)
    lines = response.iter_lines()

    # Initial response of stream will be the full game info. Store it.
    initial_state = json.loads(next(lines).decode("utf-8"))
    logger.debug(f"Initial state: {initial_state}")
    abort_time = seconds(config.abort_time)
    game = model.Game(initial_state, user_profile["username"], li.baseUrl, abort_time)

    with engine_wrapper.create_engine(config, game) as engine:
        engine.get_opponent_info(game)
        logger.debug(f"The engine for game {game_id} has pid={engine.get_pid()}")
        conversation = Conversation(game, engine, li, __version__, challenge_queue)

        logger.info(f"+++ {game}")

        is_correspondence = game.speed == "correspondence"
        correspondence_cfg = config.correspondence
        correspondence_move_time = seconds(correspondence_cfg.move_time)
        correspondence_disconnect_time = seconds(correspondence_cfg.disconnect_time)

        engine_cfg = config.engine
        ponder_cfg = correspondence_cfg if is_correspondence else engine_cfg
        can_ponder = ponder_cfg.uci_ponder or ponder_cfg.ponder
        move_overhead = msec(config.move_overhead)
        delay = msec(config.rate_limiting_delay)

        takebacks_accepted = read_takeback_record(game)
        max_takebacks_accepted = config.max_takebacks_accepted

        keyword_map: defaultdict[str, str] = defaultdict(str, me=game.me.name, opponent=game.opponent.name)
        hello = get_greeting("hello", config.greeting, keyword_map)
        goodbye = get_greeting("goodbye", config.greeting, keyword_map)
        hello_spectators = get_greeting("hello_spectators", config.greeting, keyword_map)
        goodbye_spectators = get_greeting("goodbye_spectators", config.greeting, keyword_map)

        disconnect_time = correspondence_disconnect_time if not game.state.get("moves") else seconds(0)
        prior_game = None
        board = chess.Board()
        game_stream = itertools.chain([json.dumps(game.state).encode("utf-8")], lines)
        quit_after_all_games_finish = config.quit_after_all_games_finish
        stay_in_game = True
        while stay_in_game and (not terminated or quit_after_all_games_finish) and not force_quit:
            move_attempted = False
            try:
                upd = next_update(game_stream)
                u_type = upd["type"] if upd else "ping"
                if u_type == "chatLine":
                    conversation.react(ChatLine(upd))
                elif u_type == "gameState":
                    game.state = upd
                    board = setup_board(game)
                    takeback_field = game.state.get("btakeback") if game.is_white else game.state.get("wtakeback")

                    if not is_game_over(game) and is_engine_move(game, prior_game, board):
                        disconnect_time = correspondence_disconnect_time
                        say_hello(conversation, hello, hello_spectators, board)
                        setup_timer = Timer()
                        print_move_number(board)
                        move_attempted = True
                        engine.play_move(board,
                                         game,
                                         li,
                                         setup_timer,
                                         move_overhead,
                                         can_ponder,
                                         is_correspondence,
                                         correspondence_move_time,
                                         engine_cfg,
                                         fake_think_time(config, board, game))
                        time.sleep(to_seconds(delay))
                    elif is_game_over(game):
                        tell_user_game_result(game, board)
                        engine.send_game_result(game, board)
                        conversation.send_message("player", goodbye)
                        conversation.send_message("spectator", goodbye_spectators)
                    elif (takeback_field
                            and not bot_to_move(game, board)
                            and li.accept_takeback(game.id, takebacks_accepted < max_takebacks_accepted)):
                        takebacks_accepted += 1
                        record_takeback(game, takebacks_accepted)
                        engine.discard_last_move_commentary()

                    wbtime = upd[engine_wrapper.wbtime(board)]
                    wbinc = upd[engine_wrapper.wbinc(board)]
                    terminate_time = msec(wbtime) + msec(wbinc) + seconds(60)
                    game.ping(abort_time, terminate_time, disconnect_time)
                    prior_game = copy.deepcopy(game)
                elif u_type == "ping" and should_exit_game(board, game, prior_game, li, is_correspondence):
                    stay_in_game = False
            except (HTTPError, ReadTimeout, RemoteDisconnected, ChunkedEncodingError, RequestsConnectionError,
                    StopIteration) as e:
                stopped = isinstance(e, StopIteration)
                stay_in_game = not stopped and (move_attempted or game_is_active(li, game.id))

        pgn_record = try_get_pgn_game_record(li, config, game, board, engine)
    final_queue_entries(control_queue, correspondence_queue, game, is_correspondence, pgn_record, pgn_queue)
    delete_takeback_record(game)


def read_takeback_record(game: model.Game) -> int:
    """Read the number of move takeback requests accepeted in a game."""
    try:
        with open(takeback_record_file_name(game.id)) as takeback_file:
            return int(takeback_file.read())
    except Exception:
        return 0


def record_takeback(game: model.Game, accepted_count: int) -> None:
    """Record the number of move takeback requests accepeted in a game."""
    with open(takeback_record_file_name(game.id), "w") as takeback_file:
        takeback_file.write(str(accepted_count))


def delete_takeback_record(game: model.Game) -> None:
    """Delete the takeback record from a game if it has finished."""
    if is_game_over(game):
        with contextlib.suppress(Exception):
            os.remove(takeback_record_file_name(game.id))


def prune_takeback_records(all_games: list[GameType]) -> None:
    """Delete takeback records from games that have ended."""
    active_game_ids = {game["gameId"] for game in all_games}
    takeback_file_template = takeback_record_file_name("*")
    prefix, suffix = takeback_file_template.split("*")
    for takeback_file_name in glob.glob(takeback_file_template):
        game_id = takeback_file_name.removeprefix(prefix).removesuffix(suffix)
        if game_id not in active_game_ids:
            with contextlib.suppress(Exception):
                os.remove(takeback_file_name)


def takeback_record_file_name(game_id: str) -> str:
    """Get the file name for recording the number of move takebacks accepted."""
    return os.path.join(auto_log_directory, f"takeback-count-{game_id}.txt")


def get_greeting(greeting: str, greeting_cfg: Configuration, keyword_map: defaultdict[str, str]) -> str:
    """Get the greeting to send to the chat."""
    greeting_text: str = greeting_cfg.lookup(greeting)
    return greeting_text.format_map(keyword_map)


def say_hello(conversation: Conversation, hello: str, hello_spectators: str, board: chess.Board) -> None:
    """Send the greetings to the chat rooms."""
    if len(board.move_stack) < 2:
        conversation.send_message("player", hello)
        conversation.send_message("spectator", hello_spectators)


def fake_think_time(config: Configuration, board: chess.Board, game: model.Game) -> datetime.timedelta:
    """Calculate how much time we should wait for fake_think_time."""
    sleep = seconds(0.0)

    if config.fake_think_time and len(board.move_stack) > 9:
        remaining = max(seconds(0), game.my_remaining_time() - msec(config.move_overhead))
        delay = remaining * 0.025
        accel = 0.99 ** (len(board.move_stack) - 10)
        sleep = delay * accel

    return sleep


def print_move_number(board: chess.Board) -> None:
    """Log the move number."""
    logger.info("")
    logger.info(f"move: {len(board.move_stack) // 2 + 1}")


def next_update(lines: Iterator[bytes]) -> GameEventType:
    """Get the next game state."""
    binary_chunk = next(lines)
    upd = cast(GameEventType, json.loads(binary_chunk.decode("utf-8"))) if binary_chunk else {}
    if upd:
        logger.debug(f"Game state: {upd}")
    return upd


def setup_board(game: model.Game) -> chess.Board:
    """Set up the board."""
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


def is_engine_move(game: model.Game, prior_game: Optional[model.Game], board: chess.Board) -> bool:
    """Check whether it is the engine's turn."""
    return game_changed(game, prior_game) and bot_to_move(game, board)


def bot_to_move(game: model.Game, board: chess.Board) -> bool:
    """
    Determine whether it is the bot's move on the given board.

    This only determines if the board state shows the bot is on move. It does not check if the board state has changed.
    Messages from lichess can contain repeat board states if another game aspect has changed (draw offer, takeback offer,
    etc.). Use is_engine_move() to determine if the engine should play a move.
    """
    return game.is_white == (board.turn == chess.WHITE)


def is_game_over(game: model.Game) -> bool:
    """Check whether the game is over."""
    status = game.state["status"]
    return status != "started"


def should_exit_game(board: chess.Board, game: model.Game, prior_game: Optional[model.Game], li: lichess.Lichess,
                     is_correspondence: bool) -> bool:
    """Whether we should exit a game."""
    if (is_correspondence
            and not is_engine_move(game, prior_game, board)
            and game.should_disconnect_now()):
        return True
    if game.should_abort_now():
        logger.info(f"Aborting {game.url()} by lack of activity")
        li.abort(game.id)
        return True
    if game.should_terminate_now():
        logger.info(f"Terminating {game.url()} by lack of activity")
        if game.is_abortable():
            li.abort(game.id)
        return True
    return False


def final_queue_entries(control_queue: CONTROL_QUEUE_TYPE, correspondence_queue: CORRESPONDENCE_QUEUE_TYPE,
                        game: model.Game, is_correspondence: bool, pgn_record: str, pgn_queue: PGN_QUEUE_TYPE) -> None:
    """
    Log the game that ended or we disconnected from, and sends a `local_game_done` for the game.

     If this is an unfinished correspondence game, put it in a queue to resume later.
    """
    if is_correspondence and not is_game_over(game):
        logger.info(f"--- Disconnecting from {game.url()}")
        correspondence_queue.put_nowait(game.id)
    else:
        logger.info(f"--- {game.url()} Game over")

    control_queue.put_nowait({"type": "local_game_done", "game": {"id": game.id}})
    pgn_queue.put_nowait({"game": {"id": game.id,
                                   "pgn": pgn_record,
                                   "complete": is_game_over(game)}})


def game_changed(current_game: model.Game, prior_game: Optional[model.Game]) -> bool:
    """Check whether the current game state is different from the previous game state."""
    if prior_game is None:
        return True

    current_game_moves_str = current_game.state["moves"]
    prior_game_moves_str = prior_game.state["moves"]
    return current_game_moves_str != prior_game_moves_str


def tell_user_game_result(game: model.Game, board: chess.Board) -> None:
    """Log the game result."""
    winner = game.state.get("winner")
    termination = game.state.get("status")

    winning_name = game.white.name if winner == "white" else game.black.name
    losing_name = game.white.name if winner == "black" else game.black.name

    if winner is not None:
        logger.info(f"{winning_name} won!")
    elif termination in [model.Termination.DRAW, model.Termination.TIMEOUT]:
        logger.info("Game ended in a draw.")
    else:
        logger.info("Game adjourned.")

    simple_endings: dict[str, str] = {model.Termination.MATE: "Game won by checkmate.",
                                      model.Termination.RESIGN: f"{losing_name} resigned.",
                                      model.Termination.ABORT: "Game aborted."}

    if termination in simple_endings:
        logger.info(simple_endings[termination])
    elif termination == model.Termination.DRAW:
        draw_results = [(board.is_fifty_moves(), "Game drawn by 50-move rule."),
                        (board.is_repetition(), "Game drawn by threefold repetition."),
                        (board.is_insufficient_material(), "Game drawn from insufficient material."),
                        (board.is_stalemate(), "Game drawn by stalemate."),
                        (True, "Game drawn by agreement.")]
        messages = [draw_message for is_result, draw_message in draw_results if is_result]
        logger.info(messages[0])
    elif termination == model.Termination.TIMEOUT:
        if winner:
            logger.info(f"{losing_name} forfeited on time.")
        else:
            timeout_name = game.white.name if game.state.get("wtime") == 0 else game.black.name
            other_name = game.white.name if timeout_name == game.black.name else game.black.name
            logger.info(f"{timeout_name} ran out of time, but {other_name} did not have enough material to mate.")
    elif termination:
        logger.info(f"Game ended by {termination}")


def try_get_pgn_game_record(li: lichess.Lichess, config: Configuration, game: model.Game, board: chess.Board,
                            engine: engine_wrapper.EngineWrapper) -> str:
    """
    Call `print_pgn_game_record` to write the game to a PGN file and handle errors raised by it.

    :param li: Provides communication with lichess.org.
    :param config: The config that the bot will use.
    :param game: Contains information about the game (e.g. the players' names).
    :param board: The board. Contains the moves.
    :param engine: The engine. Contains information about the moves (e.g. eval, PV, depth).
    """
    try:
        return pgn_game_record(li, config, game, board, engine)
    except Exception:
        logger.exception("Error writing game record:")
        return ""


def pgn_game_record(li: lichess.Lichess, config: Configuration, game: model.Game, board: chess.Board,
                    engine: engine_wrapper.EngineWrapper) -> str:
    """
    Return the text of the game's PGN.

    :param li: Provides communication with lichess.org.
    :param config: The config that the bot will use.
    :param game: Contains information about the game (e.g. the players' names).
    :param board: The board. Contains the moves.
    :param engine: The engine. Contains information about the moves (e.g. eval, PV, depth).
    """
    if not config.pgn_directory:
        return ""

    lichess_game_record = chess.pgn.read_game(io.StringIO(li.get_game_pgn(game.id))) or chess.pgn.Game()
    try:
        # Recall previously written PGN file to retain engine evaluations.
        previous_game_path = get_game_file_path(config,
                                                game.id,
                                                game.white.name,
                                                game.black.name,
                                                game.me.name,
                                                is_game_over(game),
                                                force_single=True)
        with open(previous_game_path) as game_data:
            game_record = chess.pgn.read_game(game_data) or lichess_game_record
        game_record.headers.update(lichess_game_record.headers)
    except FileNotFoundError:
        game_record = lichess_game_record

    fill_missing_pgn_headers(game_record, game)

    current_node: Union[chess.pgn.Game, chess.pgn.ChildNode] = game_record.game()
    lichess_node: Union[chess.pgn.Game, chess.pgn.ChildNode] = lichess_game_record.game()
    for index, move in enumerate(board.move_stack):
        next_node = current_node.next()
        if next_node is None or next_node.move != move:
            current_node = current_node.add_main_variation(move)
        else:
            current_node = next_node

        next_lichess_node = lichess_node.next()
        if next_lichess_node:
            lichess_node = next_lichess_node
            current_node.set_clock(lichess_node.clock())
            if current_node.comment != lichess_node.comment:
                current_node.comment = f"{current_node.comment} {lichess_node.comment}".strip()

        commentary = engine.comment_for_board_index(index)
        pv_node = current_node.parent.add_line(commentary["pv"]) if "pv" in commentary else current_node
        pv_node.set_eval(commentary.get("score"), commentary.get("depth"))

    pgn_writer = chess.pgn.StringExporter()
    return game_record.accept(pgn_writer)


def get_game_file_path(config: Configuration,
                       game_id: str,
                       white_name: str,
                       black_name: str,
                       user_name: str,
                       game_is_over: bool,
                       *, force_single: bool = False) -> str:
    """Return the path of the file where the game record will be written."""
    def create_valid_path(s: str) -> str:
        illegal = '<>:"/\\|?*'
        return os.path.join(config.pgn_directory, "".join(c for c in s if c not in illegal))

    if config.pgn_file_grouping == "game" or not game_is_over or force_single:
        return create_valid_path(f"{white_name} vs {black_name} - {game_id}.pgn")
    elif config.pgn_file_grouping == "opponent":
        opponent_name = white_name if user_name == black_name else black_name
        return create_valid_path(f"{user_name} games vs. {opponent_name}.pgn")
    else:  # config.pgn_file_grouping == "all"
        return create_valid_path(f"{user_name} games.pgn")


def fill_missing_pgn_headers(game_record: chess.pgn.Game, game: model.Game) -> None:
    """
    Fill in any missing headers in the PGN record provided by lichess.org with information from `game`.

    :param game_record: A `chess.pgn.Game` object containing information about the game lichess.org's PGN file.
    :param game: Contains information about the game (e.g. the players' names), which is used to get the local headers.
    """
    local_headers = get_headers(game)
    for header, game_value in local_headers.items():
        record_value = game_record.headers.get(header)
        if not record_value or record_value.startswith("?") or (header == "Result" and record_value == "*"):
            game_record.headers[header] = str(game_value)


def get_headers(game: model.Game) -> dict[str, Union[str, int]]:
    """
    Create local headers to be written in the PGN file.

    :param game: Contains information about the game (e.g. the players' names).
    :return: The headers in a dict.
    """
    headers: dict[str, Union[str, int]] = {}
    headers["Event"] = game.pgn_event()
    headers["Site"] = game.short_url()
    headers["Date"] = game.game_start.strftime("%Y.%m.%d")
    headers["White"] = game.white.name or str(game.white)
    headers["Black"] = game.black.name or str(game.black)
    headers["Result"] = game.result()

    if game.black.rating:
        headers["BlackElo"] = game.black.rating
    if game.black.title:
        headers["BlackTitle"] = game.black.title

    if game.perf_name != "correspondence":
        headers["TimeControl"] = game.time_control()

    headers["UTCDate"] = headers["Date"]
    headers["UTCTime"] = game.game_start.strftime("%H:%M:%S")
    headers["Variant"] = game.variant_name

    if game.initial_fen and game.initial_fen != "startpos":
        headers["Setup"] = 1
        headers["FEN"] = game.initial_fen

    if game.white.rating:
        headers["WhiteElo"] = game.white.rating
    if game.white.title:
        headers["WhiteTitle"] = game.white.title

    return headers


def save_pgn_record(event: EventType, config: Configuration, user_name: str) -> None:
    """
    Write the game PGN record to a file.

    :param event: A local_game_done event from the control queue.
    :param config: The user's bot configuration.
    :param user_name: The bot's name.
    """
    pgn = event["game"]["pgn"]
    pgn_headers = chess.pgn.read_headers(io.StringIO(pgn))
    if not config.pgn_directory or pgn_headers is None:
        return

    game_id = event["game"]["id"]
    white_name = pgn_headers["White"]
    black_name = pgn_headers["Black"]
    game_is_over = event["game"]["complete"]

    os.makedirs(config.pgn_directory, exist_ok=True)
    game_path = get_game_file_path(config, game_id, white_name, black_name, user_name, game_is_over)
    single_game_path = get_game_file_path(config, game_id, white_name, black_name, user_name, game_is_over, force_single=True)
    write_mode = "w" if game_path == single_game_path else "a"
    logger.debug(f"Writing PGN game record to: {game_path}")
    with open(game_path, write_mode) as game_file:
        game_file.write(pgn + "\n\n")

    if os.path.exists(single_game_path) and game_path != single_game_path:
        os.remove(single_game_path)


def intro() -> str:
    """Return the intro string."""
    return fr"""
    .   _/|
    .  // o\
    .  || ._)  lichess-bot {__version__} on {platform.system()} {platform.release()}
    .  //__\
    .  )___(   Play on Lichess with a bot
    """


auto_log_directory = "lichess_bot_auto_logs"


def log_python_and_libraries() -> None:
    """Log the installed libraries and the python version."""
    logger.debug(f"Python version: {'.'.join(map(str, sys.version_info))}")
    text = "Installed libraries:\n"
    distributions = importlib.metadata.distributions()
    for distribution in distributions:
        text += f"{distribution.metadata['Name']}=={distribution.version}\n"
    text += "\n"
    logger.debug(text)


def start_lichess_bot() -> None:
    """Parse arguments passed to lichess-bot.py and starts lichess-bot."""
    parser = argparse.ArgumentParser(description="Play on Lichess with a bot")
    parser.add_argument("-u", action="store_true", help="Upgrade your account to a bot account.")
    parser.add_argument("-v", action="store_true", help="Make output more verbose. Include all communication with lichess.")
    parser.add_argument("--config", help="Specify a configuration file (defaults to ./config.yml).")
    parser.add_argument("-l", "--logfile", help="Record all console output to a log file.", default=None)
    parser.add_argument("--disable_auto_logging", action="store_true", help="Disable automatic logging.")
    args = parser.parse_args()

    logging_level = logging.DEBUG if args.v else logging.INFO
    logging_configurer(logging_level, args.logfile, args.disable_auto_logging)
    logger.info(intro(), extra={"highlighter": None})

    CONFIG = load_config(args.config or "./config.yml")
    if not args.disable_auto_logging:
        with open(os.path.join(auto_log_directory, "config.log"), "w") as config_log:
            log_config(CONFIG.config, config_log.write)
    logger.info("Checking engine configuration ...")
    with engine_wrapper.create_engine(CONFIG):
        pass
    logger.info("Engine configuration OK")

    max_retries = CONFIG.engine.online_moves.max_retries
    check_python_version()
    log_python_and_libraries()
    li = lichess.Lichess(CONFIG.token, CONFIG.url, __version__, logging_level, max_retries)

    user_profile = li.get_profile()
    username = user_profile["username"]
    is_bot = user_profile.get("title") == "BOT"
    logger.info(f"Welcome {username}!")

    if args.u and not is_bot:
        is_bot = upgrade_account(li)

    if is_bot:
        start(li, user_profile, CONFIG, logging_level, args.logfile, args.disable_auto_logging)
    else:
        logger.error(f"{username} is not a bot account. Please upgrade it to a bot account!")
    logging.shutdown()


def check_python_version() -> None:
    """Raise a warning or an exception if the version isn't supported or is deprecated."""
    def version_numeric(version_str: str) -> list[int]:
        return [int(n) for n in version_str.split(".")]

    python_deprecated_version = version_numeric(versioning_info["deprecated_python_version"])
    python_good_version = version_numeric(versioning_info["minimum_python_version"])
    version_change_date = versioning_info["deprecation_date"]
    this_python_version = list(sys.version_info[0:2])

    def version_str(version: list[int]) -> str:
        return f"Python {'.'.join(str(n) for n in version)}"

    upgrade_request = (f"You are currently running {version_str(this_python_version)}. "
                       f"Please upgrade to {version_str(python_good_version)} or newer")
    out_of_date_error = RuntimeError("A newer version of Python is required "
                                     f"to run this version of lichess-bot. {upgrade_request}.")
    out_of_date_warning = ("A newer version of Python will be required "
                           f"on {version_change_date} to run lichess-bot. {upgrade_request} before then.")

    this_lichess_bot_version = version_numeric(__version__)
    lichess_bot_breaking_version = list(version_change_date.timetuple()[0:3])

    if this_python_version < python_deprecated_version:
        raise out_of_date_error

    if this_python_version == python_deprecated_version:
        if this_lichess_bot_version < lichess_bot_breaking_version:
            logger.warning(out_of_date_warning)
        else:
            raise out_of_date_error


def start_program() -> None:
    """Start lichess-bot and restart when needed."""
    multiprocessing.set_start_method("spawn")
    try:
        while should_restart():
            disable_restart()
            start_lichess_bot()
            time.sleep(10 if should_restart() else 0)
    except Exception:
        logger.exception("Quitting lichess-bot due to an error:")
