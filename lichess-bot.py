import argparse
import chess
import chess.pgn
import chess.syzygy
import chess.gaviota
from chess.variant import find_variant
import chess.polyglot
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
import random
import os
import io
import copy
from config import load_config
from conversation import Conversation, ChatLine
from timer import Timer
from requests.exceptions import ChunkedEncodingError, ConnectionError, HTTPError, ReadTimeout
from rich.logging import RichHandler
from collections import defaultdict, Counter
from http.client import RemoteDisconnected

logger = logging.getLogger(__name__)

__version__ = "1.2.0"

terminated = False

out_of_online_opening_book_moves = Counter()


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
    busy_processes = 0
    queued_processes = 0

    def log_proc_count(change, queued, used):
        symbol = "+++" if change == "Freed" else "---"
        logger.info(f"{symbol} Process {change}. Total Queued: {queued}. Total Used: {used}")

    challenge_config = config["challenge"]
    max_games = challenge_config.get("concurrency", 1)

    wait_for_correspondence_ping = False
    startup_correspondence_games = [game["gameId"]
                                    for game in li.get_ongoing_games()
                                    if game["perf"] == "correspondence"]

    last_check_online_time = Timer(60 * 60)  # one hour interval
    matchmaker = matchmaking.Matchmaking(li, config, user_profile)

    play_game_args = [li,
                      None,  # will hold the game id
                      control_queue,
                      user_profile,
                      config,
                      challenge_queue,
                      correspondence_queue,
                      logging_queue,
                      game_logging_configurer,
                      logging_level]

    with multiprocessing.pool.Pool(max_games + 1) as pool:
        while not terminated:
            try:
                event = control_queue.get()
                if event.get("type") != "ping":
                    logger.debug(f"Event: {event}")
            except InterruptedError:
                continue

            if event.get("type") is None:
                logger.warning("Unable to handle response from lichess.org:")
                logger.warning(event)
                if event.get("error") == "Missing scope":
                    logger.warning('Please check that the API access token for your bot has the scope "Play games '
                                   'with the bot API".')
                continue

            if event["type"] == "terminated":
                break
            elif event["type"] == "local_game_done":
                busy_processes -= 1
                matchmaker.last_game_ended_delay.reset()
                log_proc_count("Freed", queued_processes, busy_processes)
                if one_game:
                    break
            elif event["type"] == "challenge":
                chlng = model.Challenge(event["challenge"], user_profile)
                is_supported, decline_reason = chlng.is_supported(challenge_config)
                if is_supported:
                    challenge_queue.append(chlng)
                    if challenge_config.get("sort_by", "best") == "best":
                        list_c = list(challenge_queue)
                        list_c.sort(key=lambda c: -c.score())
                        challenge_queue = list_c
                elif chlng.id != matchmaker.challenge_id:
                    li.decline_challenge(chlng.id, reason=decline_reason)
            elif event["type"] == "challengeDeclined":
                matchmaker.declined_challenge(event)
            elif event["type"] == "gameStart":
                game_id = event["game"]["id"]
                if matchmaker.challenge_id == game_id:
                    matchmaker.challenge_id = None
                if game_id in startup_correspondence_games:
                    logger.info(f'--- Enqueue {config["url"] + game_id}')
                    correspondence_queue.put(game_id)
                    startup_correspondence_games.remove(game_id)
                else:
                    if queued_processes > 0:
                        queued_processes -= 1
                    busy_processes += 1
                    log_proc_count("Used", queued_processes, busy_processes)
                    play_game_args[1] = game_id
                    pool.apply_async(play_game,
                                     play_game_args,
                                     error_callback=game_error_handler)

            is_correspondence_ping = event["type"] == "correspondence_ping"
            is_local_game_done = event["type"] == "local_game_done"
            if (is_correspondence_ping or (is_local_game_done and not wait_for_correspondence_ping)) and not challenge_queue:
                if is_correspondence_ping and wait_for_correspondence_ping:
                    correspondence_queue.put("")

                wait_for_correspondence_ping = False
                while (busy_processes + queued_processes) < max_games:
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
                        busy_processes += 1
                        log_proc_count("Used", queued_processes, busy_processes)
                        play_game_args[1] = game_id
                        pool.apply_async(play_game,
                                         play_game_args,
                                         error_callback=game_error_handler)

            # Keep processing the queue until empty or max_games is reached.
            while (queued_processes + busy_processes) < max_games and challenge_queue:
                chlng = challenge_queue.pop(0)
                if chlng.from_self:
                    continue
                try:
                    logger.info(f"Accept {chlng}")
                    queued_processes += 1
                    li.accept_challenge(chlng.id)
                    log_proc_count("Queued", queued_processes, busy_processes)
                except (HTTPError, ReadTimeout) as exception:
                    if isinstance(exception, HTTPError) and exception.response.status_code == 404:
                        logger.info(f"Skip missing {chlng}")
                    queued_processes -= 1

            if (queued_processes + busy_processes < 1
                    and not challenge_queue
                    and matchmaker.should_create_challenge()):
                logger.info("Challenging a random bot")
                matchmaker.challenge()

            if last_check_online_time.is_expired():
                if not li.is_online(user_profile["id"]):
                    logger.info("Will reset connection with lichess")
                    li.reset_connection()
                last_check_online_time.reset()

            control_queue.task_done()

    logger.info("Terminated")


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

    is_correspondence = game.perf_name == "Correspondence"
    correspondence_cfg = config.get("correspondence") or {}
    correspondence_move_time = correspondence_cfg.get("move_time", 60) * 1000
    correspondence_disconnect_time = correspondence_cfg.get("disconnect_time", 300)

    engine_cfg = config["engine"]
    ponder_cfg = correspondence_cfg if is_correspondence else engine_cfg
    can_ponder = ponder_cfg.get("uci_ponder", False) or ponder_cfg.get("ponder", False)
    move_overhead = config.get("move_overhead", 1000)
    delay_seconds = config.get("rate_limiting_delay", 0)/1000
    polyglot_cfg = engine_cfg.get("polyglot", {})
    online_moves_cfg = engine_cfg.get("online_moves", {})
    draw_or_resign_cfg = engine_cfg.get("draw_or_resign") or {}
    lichess_bot_tbs = engine_cfg.get("lichess_bot_tbs") or {}

    greeting_cfg = config.get("greeting") or {}
    keyword_map = defaultdict(str, me=game.me.name, opponent=game.opponent.name)

    def get_greeting(greeting):
        return str(greeting_cfg.get(greeting) or "").format_map(keyword_map)
    hello = get_greeting("hello")
    goodbye = get_greeting("goodbye")
    hello_spectators = get_greeting("hello_spectators")
    goodbye_spectators = get_greeting("goodbye_spectators")

    first_move = True
    disconnect_time = 0
    prior_game = None
    while not terminated:
        move_attempted = False
        try:
            if first_move:
                upd = game.state
                first_move = False
            else:
                binary_chunk = next(lines)
                upd = json.loads(binary_chunk.decode("utf-8")) if binary_chunk else None

            u_type = upd["type"] if upd else "ping"
            if u_type != "ping":
                logger.debug(f"Game state: {upd}")
            if u_type == "chatLine":
                conversation.react(ChatLine(upd), game)
            elif u_type == "gameState":
                game.state = upd
                board = setup_board(game)
                if len(board.move_stack) == 0:
                    disconnect_time = correspondence_disconnect_time
                if not is_game_over(game) and is_engine_move(game, prior_game, board):
                    disconnect_time = correspondence_disconnect_time
                    if len(board.move_stack) < 2:
                        conversation.send_message("player", hello)
                        conversation.send_message("spectator", hello_spectators)
                    start_time = time.perf_counter_ns()
                    fake_thinking(config, board, game)
                    print_move_number(board)

                    best_move = get_book_move(board, polyglot_cfg)

                    if best_move.move is None:
                        best_move = get_egtb_move(board,
                                                  lichess_bot_tbs,
                                                  draw_or_resign_cfg)

                    if best_move.move is None:
                        best_move = get_online_move(li,
                                                    board,
                                                    game,
                                                    online_moves_cfg,
                                                    draw_or_resign_cfg)

                    if best_move.move is None:
                        draw_offered = check_for_draw_offer(game)

                        if len(board.move_stack) < 2:
                            best_move = choose_first_move(engine,
                                                          board,
                                                          draw_offered)
                        elif is_correspondence:
                            best_move = choose_move_time(engine,
                                                         board,
                                                         correspondence_move_time,
                                                         can_ponder,
                                                         draw_offered)
                        else:
                            best_move = choose_move(engine,
                                                    board,
                                                    game,
                                                    can_ponder,
                                                    draw_offered,
                                                    start_time,
                                                    move_overhead)
                    else:
                        engine.add_null_comment()
                    move_attempted = True
                    if best_move.resigned and len(board.move_stack) >= 2:
                        li.resign(game.id)
                    else:
                        li.make_move(game.id, best_move)
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
            elif u_type == "ping":
                if (is_correspondence
                        and not is_engine_move(game, prior_game, board)
                        and game.should_disconnect_now()):
                    break
                elif game.should_abort_now():
                    logger.info(f"Aborting {game.url()} by lack of activity")
                    li.abort(game.id)
                    break
                elif game.should_terminate_now():
                    logger.info(f"Terminating {game.url()} by lack of activity")
                    if game.is_abortable():
                        li.abort(game.id)
                    break
        except (HTTPError, ReadTimeout, RemoteDisconnected, ChunkedEncodingError, ConnectionError):
            if move_attempted:
                continue
            if game.id not in (ongoing_game["gameId"] for ongoing_game in li.get_ongoing_games()):
                break
        except StopIteration:
            break

    engine.stop()
    engine.quit()

    try:
        print_pgn_game_record(li, config, game, board, engine)
    except Exception:
        logger.exception("Error writing game record:")

    if is_correspondence and not is_game_over(game):
        logger.info(f"--- Disconnecting from {game.url()}")
        correspondence_queue.put(game_id)
    else:
        logger.info(f"--- {game.url()} Game over")

    control_queue.put_nowait({"type": "local_game_done"})


def choose_move_time(engine, board, search_time, ponder, draw_offered):
    logger.info(f"Searching for time {search_time}")
    return engine.search_for(board, search_time, ponder, draw_offered)


def choose_first_move(engine, board, draw_offered):
    # need to hardcode first movetime (10000 ms) since Lichess has 30 sec limit.
    search_time = 10000
    logger.info(f"Searching for time {search_time}")
    return engine.first_search(board, search_time, draw_offered)


def get_book_move(board, polyglot_cfg):
    no_book_move = chess.engine.PlayResult(None, None)
    use_book = polyglot_cfg.get("enabled")
    max_game_length = polyglot_cfg.get("max_depth", 8) * 2 - 1
    if not use_book or len(board.move_stack) > max_game_length:
        return no_book_move

    book_config = polyglot_cfg.get("book", {})

    variant = "standard" if board.uci_variant == "chess" else board.uci_variant
    books = book_config.get(variant) or []
    if isinstance(books, str):
        books = [books]

    for book in books:
        with chess.polyglot.open_reader(book) as reader:
            try:
                selection = polyglot_cfg.get("selection", "weighted_random")
                min_weight = polyglot_cfg.get("min_weight", 1)
                if selection == "weighted_random":
                    move = reader.weighted_choice(board).move
                elif selection == "uniform_random":
                    move = reader.choice(board, minimum_weight=min_weight).move
                elif selection == "best_move":
                    move = reader.find(board, minimum_weight=min_weight).move
            except IndexError:
                # python-chess raises "IndexError" if no entries found
                move = None

        if move is not None:
            logger.info(f"Got move {move} from book {book}")
            return chess.engine.PlayResult(move, None)

    return no_book_move


def get_chessdb_move(li, board, game, chessdb_cfg):
    wb = "w" if board.turn == chess.WHITE else "b"
    use_chessdb = chessdb_cfg.get("enabled", False)
    time_left = game.state[f"{wb}time"]
    min_time = chessdb_cfg.get("min_time", 20) * 1000
    if not use_chessdb or time_left < min_time or board.uci_variant != "chess":
        return None

    move = None
    site = "https://www.chessdb.cn/cdb.php"
    quality = chessdb_cfg.get("move_quality", "good")
    action = {"best": "querypv",
              "good": "querybest",
              "all": "query"}
    try:
        params = {"action": action[quality],
                  "board": board.fen(),
                  "json": 1}
        data = li.online_book_get(site, params=params)
        if data["status"] == "ok":
            if quality == "best":
                depth = data["depth"]
                if depth >= chessdb_cfg.get("min_depth", 20):
                    score = data["score"]
                    move = data["pv"][0]
                    logger.info(f"Got move {move} from chessdb.cn (depth: {depth}, score: {score})")
            else:
                move = data["move"]
                logger.info(f"Got move {move} from chessdb.cn")

        if chessdb_cfg.get("contribute", True):
            params["action"] = "queue"
            li.online_book_get(site, params=params)
    except Exception:
        pass

    return move


def get_lichess_cloud_move(li, board, game, lichess_cloud_cfg):
    wb = "w" if board.turn == chess.WHITE else "b"
    time_left = game.state[f"{wb}time"]
    min_time = lichess_cloud_cfg.get("min_time", 20) * 1000
    use_lichess_cloud = lichess_cloud_cfg.get("enabled", False)
    if not use_lichess_cloud or time_left < min_time:
        return None

    move = None

    quality = lichess_cloud_cfg.get("move_quality", "best")
    multipv = 1 if quality == "best" else 5
    variant = "standard" if board.uci_variant == "chess" else board.uci_variant

    try:
        data = li.online_book_get("https://lichess.org/api/cloud-eval",
                                  params={"fen": board.fen(),
                                          "multiPv": multipv,
                                          "variant": variant})
        if "error" not in data:
            depth = data["depth"]
            knodes = data["knodes"]
            min_depth = lichess_cloud_cfg.get("min_depth", 20)
            min_knodes = lichess_cloud_cfg.get("min_knodes", 0)
            if depth >= min_depth and knodes >= min_knodes:
                if quality == "best":
                    pv = data["pvs"][0]
                else:
                    best_eval = data["pvs"][0]["cp"]
                    pvs = data["pvs"]
                    max_difference = lichess_cloud_cfg.get("max_score_difference", 50)
                    if wb == "w":
                        pvs = list(filter(lambda pv: pv["cp"] >= best_eval - max_difference, pvs))
                    else:
                        pvs = list(filter(lambda pv: pv["cp"] <= best_eval + max_difference, pvs))
                    pv = random.choice(pvs)
                move = pv["moves"].split()[0]
                score = pv["cp"] if wb == "w" else -pv["cp"]
                logger.info(f"Got move {move} from lichess cloud analysis (depth: {depth}, score: {score}, knodes: {knodes})")
    except Exception:
        pass

    return move


def get_online_egtb_move(li, board, game, online_egtb_cfg):
    use_online_egtb = online_egtb_cfg.get("enabled", False)
    wb = "w" if board.turn == chess.WHITE else "b"
    pieces = chess.popcount(board.occupied)
    source = online_egtb_cfg.get("source", "lichess")
    minimum_time = online_egtb_cfg.get("min_time", 20) * 1000
    if (not use_online_egtb
            or game.state[f"{wb}time"] < minimum_time
            or board.uci_variant not in ["chess", "antichess", "atomic"]
            and source == "lichess"
            or board.uci_variant != "chess"
            and source == "chessdb"
            or pieces > online_egtb_cfg.get("max_pieces", 7)
            or board.castling_rights):

        return None, None

    quality = online_egtb_cfg.get("move_quality", "best")
    variant = "standard" if board.uci_variant == "chess" else board.uci_variant

    try:
        if source == "lichess":
            name_to_wld = {"loss": -2,
                           "maybe-loss": -1,
                           "blessed-loss": -1,
                           "draw": 0,
                           "cursed-win": 1,
                           "maybe-win": 1,
                           "win": 2}
            max_pieces = 7 if board.uci_variant == "chess" else 6
            if pieces <= max_pieces:
                data = li.online_book_get(f"http://tablebase.lichess.ovh/{variant}",
                                          params={"fen": board.fen()})
                if quality == "best":
                    move = data["moves"][0]["uci"]
                    wdl = name_to_wld[data["moves"][0]["category"]] * -1
                    dtz = data["moves"][0]["dtz"] * -1
                    dtm = data["moves"][0]["dtm"]
                    if dtm:
                        dtm *= -1
                else:
                    best_wdl = name_to_wld[data["moves"][0]["category"]]

                    def good_enough(possible_move):
                        return name_to_wld[possible_move["category"]] == best_wdl
                    possible_moves = list(filter(good_enough, data["moves"]))
                    random_move = random.choice(possible_moves)
                    move = random_move["uci"]
                    wdl = name_to_wld[random_move["category"]] * -1
                    dtz = random_move["dtz"] * -1
                    dtm = random_move["dtm"]
                    if dtm:
                        dtm *= -1

                logger.info(f"Got move {move} from tablebase.lichess.ovh (wdl: {wdl}, dtz: {dtz}, dtm: {dtm})")
                return move, wdl
        elif source == "chessdb":

            def score_to_wdl(score):
                if score < -20000:
                    return -2
                elif score < 0:
                    return -1
                elif score == 0:
                    return 0
                elif score <= 20000:
                    return 1
                else:
                    return 2

            def score_to_dtz(score):
                if score < -20000:
                    return -30000 - score
                elif score < 0:
                    return -20000 - score
                elif score == 0:
                    return 0
                elif score <= 20000:
                    return 20000 - score
                else:
                    return 30000 - score

            action = "querypv" if quality == "best" else "queryall"
            data = li.online_book_get("https://www.chessdb.cn/cdb.php",
                                      params={"action": action, "board": board.fen(), "json": 1})
            if data["status"] == "ok":
                if quality == "best":
                    score = data["score"]
                    move = data["pv"][0]
                else:
                    best_wdl = score_to_wdl(data["moves"][0]["score"])

                    def good_enough(move):
                        return score_to_wdl(move["score"]) == best_wdl
                    possible_moves = filter(good_enough, data["moves"])
                    random_move = random.choice(list(possible_moves))
                    score = random_move["score"]
                    move = random_move["uci"]

                wdl = score_to_wdl(score)
                dtz = score_to_dtz(score)
                logger.info(f"Got move {move} from chessdb.cn (wdl: {wdl}, dtz: {dtz})")
                return move, score_to_wdl(score)
    except Exception:
        pass

    return None, None


def get_online_move(li, board, game, online_moves_cfg, draw_or_resign_cfg):
    online_egtb_cfg = online_moves_cfg.get("online_egtb", {})
    chessdb_cfg = online_moves_cfg.get("chessdb_book", {})
    lichess_cloud_cfg = online_moves_cfg.get("lichess_cloud_analysis", {})
    max_out_of_book_moves = online_moves_cfg.get("max_out_of_book_moves", 10)
    offer_draw = False
    resign = False
    best_move, wdl = get_online_egtb_move(li, board, game, online_egtb_cfg)
    if best_move is not None:
        can_offer_draw = draw_or_resign_cfg.get("offer_draw_enabled", False)
        offer_draw_for_zero = draw_or_resign_cfg.get("offer_draw_for_egtb_zero", True)
        if can_offer_draw and offer_draw_for_zero and wdl == 0:
            offer_draw = True

        can_resign = draw_or_resign_cfg.get("resign_enabled", False)
        resign_on_egtb_loss = draw_or_resign_cfg.get("resign_for_egtb_minus_two", True)
        if can_resign and resign_on_egtb_loss and wdl == -2:
            resign = True
    elif out_of_online_opening_book_moves[game.id] < max_out_of_book_moves:
        best_move = get_chessdb_move(li, board, game, chessdb_cfg)

    if best_move is None and out_of_online_opening_book_moves[game.id] < max_out_of_book_moves:
        best_move = get_lichess_cloud_move(li, board, game, lichess_cloud_cfg)

    if best_move:
        return chess.engine.PlayResult(chess.Move.from_uci(best_move),
                                       None,
                                       draw_offered=offer_draw,
                                       resigned=resign)
    out_of_online_opening_book_moves[game.id] += 1
    used_opening_books = chessdb_cfg.get("enabled") or lichess_cloud_cfg.get("enabled")
    if out_of_online_opening_book_moves[game.id] == max_out_of_book_moves and used_opening_books:
        logger.info("Will stop using online opening books.")
    return chess.engine.PlayResult(None, None)


def get_syzygy(board, syzygy_cfg):
    if (not syzygy_cfg.get("enabled", False)
            or chess.popcount(board.occupied) > syzygy_cfg.get("max_pieces", 7)
            or board.uci_variant not in ["chess", "antichess", "atomic"]):
        return None, None
    move_quality = syzygy_cfg.get("move_quality", "best")
    with chess.syzygy.open_tablebase(syzygy_cfg["paths"][0]) as tablebase:
        for path in syzygy_cfg["paths"][1:]:
            tablebase.add_directory(path)

        try:
            moves = {}
            for move in board.legal_moves:
                board_copy = board.copy()
                board_copy.push(move)
                dtz = -tablebase.probe_dtz(board_copy)
                moves[move] = dtz + (1 if dtz > 0 else -1) * board_copy.halfmove_clock * (0 if dtz == 0 else 1)

            def dtz_to_wdl(dtz):
                if dtz <= -100:
                    return -1
                elif dtz < 0:
                    return -2
                elif dtz == 0:
                    return 0
                elif dtz < 100:
                    return 2
                else:
                    return 1

            best_wdl = max(map(dtz_to_wdl, moves.values()))
            good_moves = [(move, dtz) for move, dtz in moves.items() if dtz_to_wdl(dtz) == best_wdl]
            if move_quality == "good":
                move, dtz = random.choice(good_moves)
                logger.info(f"Got move {move.uci()} from syzygy (wdl: {best_wdl}, dtz: {dtz})")
                return move, best_wdl
            else:
                best_dtz = min([dtz for move, dtz in good_moves])
                best_moves = [move for move, dtz in good_moves if dtz == best_dtz]
                move = random.choice(best_moves)
                logger.info(f"Got move {move.uci()} from syzygy (wdl: {best_wdl}, dtz: {best_dtz})")
                return move, best_wdl
        except KeyError:
            # Attempt to only get the WDL score. It returns a move of quality="good", even if quality is set to "best".
            try:
                moves = {}
                for move in board.legal_moves:
                    board_copy = board.copy()
                    board_copy.push(move)
                    moves[move] = -tablebase.probe_wdl(board_copy)
                best_wdl = max(moves.values())
                good_moves = [move for move, wdl in moves.items() if wdl == best_wdl]
                move = random.choice(good_moves)
                if move_quality == "best":
                    logger.debug("Found a move using 'move_quality'='good'. We didn't find an '.rtbz' file for this endgame.")
                logger.info(f"Got move {move.uci()} from syzygy (wdl: {best_wdl})")
                return move, best_wdl
            except KeyError:
                return None, None


def get_gaviota(board, gaviota_cfg):
    if (not gaviota_cfg.get("enabled", False)
            or chess.popcount(board.occupied) > gaviota_cfg.get("max_pieces", 5)
            or board.uci_variant != "chess"):
        return None, None
    move_quality = gaviota_cfg.get("move_quality", "best")
    # Since gaviota TBs use dtm and not dtz, we have to put a limit where after it the position are considered to have
    # a syzygy wdl=1/-1, so the positions are draws under the 50 move rule. We use min_dtm_to_consider_as_wdl_1 as a
    # second limit, because if a position has 5 pieces and dtm=110 it may take 98 half-moves, to go down to 4 pieces and
    # another 12 to mate, so this position has a syzygy wdl=2/-2. To be safe, the first limit is 100 moves, which
    # guarantees that all moves have a syzygy wdl=2/-2. Setting min_dtm_to_consider_as_wdl_1 to 100 will disable it
    # because dtm >= dtz, so if abs(dtm) < 100 => abs(dtz) < 100, so wdl=2/-2.
    min_dtm_to_consider_as_wdl_1 = gaviota_cfg.get("min_dtm_to_consider_as_wdl_1", 120)
    with chess.gaviota.open_tablebase(gaviota_cfg["paths"][0]) as tablebase:
        for path in gaviota_cfg["paths"][1:]:
            tablebase.add_directory(path)

        try:
            moves = {}
            for move in board.legal_moves:
                board_copy = board.copy()
                board_copy.push(move)
                dtm = -tablebase.probe_dtm(board_copy)
                moves[move] = dtm + (1 if dtm > 0 else -1) * board_copy.halfmove_clock * (0 if dtm == 0 else 1)

            def dtm_to_gaviota_wdl(dtm):
                if dtm < 0:
                    return -1
                elif dtm == 0:
                    return 0
                else:
                    return 1

            best_wdl = max(map(dtm_to_gaviota_wdl, moves.values()))
            good_moves = [(move, dtm) for move, dtm in moves.items() if dtm_to_gaviota_wdl(dtm) == best_wdl]
            best_dtm = min([dtm for move, dtm in good_moves])

            def dtm_to_wdl(dtm):
                if dtm <= -100:
                    # We use 100 and not min_dtm_to_consider_as_wdl_1, because we want to play it safe and not resign in a
                    # position where dtz=-102 (only if resign_for_egtb_minus_two is enabled).
                    return -1
                elif dtm < 0:
                    return -2
                elif dtm == 0:
                    return 0
                elif dtm < min_dtm_to_consider_as_wdl_1:
                    return 2
                else:
                    return 1

            pseudo_wdl = dtm_to_wdl(best_dtm)
            if move_quality == "good":
                if best_dtm < 100:
                    # If a move had wdl=2 and dtz=98, but halfmove_clock is 4 then the real wdl=1 and dtz=102, so we
                    # want to avoid these positions, if there is a move where even when we add the halfmove_clock the
                    # dtz is still <100.
                    best_moves = [(move, dtm) for move, dtm in good_moves if dtm < 100]
                elif best_dtm < min_dtm_to_consider_as_wdl_1:
                    # If a move had wdl=2 and dtz=98, but halfmove_clock is 4 then the real wdl=1 and dtz=102, so we
                    # want to avoid these positions, if there is a move where even when we add the halfmove_clock the
                    # dtz is still <100.
                    best_moves = [(move, dtm) for move, dtm in good_moves if dtm < min_dtm_to_consider_as_wdl_1]
                elif best_dtm <= -min_dtm_to_consider_as_wdl_1:
                    # If a move had wdl=-2 and dtz=-98, but halfmove_clock is 4 then the real wdl=-1 and dtz=-102, so we
                    # want to only choose between the moves where the real wdl=-1.
                    best_moves = [(move, dtm) for move, dtm in good_moves if dtm <= -min_dtm_to_consider_as_wdl_1]
                elif best_dtm <= -100:
                    # If a move had wdl=-2 and dtz=-98, but halfmove_clock is 4 then the real wdl=-1 and dtz=-102, so we
                    # want to only choose between the moves where the real wdl=-1.
                    best_moves = [(move, dtm) for move, dtm in good_moves if dtm <= -100]
                else:
                    best_moves = good_moves
            else:
                # There can be multiple moves with the same dtm.
                best_moves = [(move, dtm) for move, dtm in good_moves if dtm == best_dtm]
            move, dtm = random.choice(best_moves)
            logger.info(f"Got move {move.uci()} from gaviota (pseudo wdl: {pseudo_wdl}, dtm: {dtm})")
            return move, pseudo_wdl
        except KeyError:
            return None, None


def get_egtb_move(board, lichess_bot_tbs, draw_or_resign_cfg):
    best_move, wdl = get_syzygy(board, lichess_bot_tbs.get("syzygy") or {})
    if best_move is None:
        best_move, wdl = get_gaviota(board, lichess_bot_tbs.get("gaviota") or {})
    if best_move:
        can_offer_draw = draw_or_resign_cfg.get("offer_draw_enabled", False)
        offer_draw_for_zero = draw_or_resign_cfg.get("offer_draw_for_egtb_zero", True)
        offer_draw = bool(can_offer_draw and offer_draw_for_zero and wdl == 0)

        can_resign = draw_or_resign_cfg.get("resign_enabled", False)
        resign_on_egtb_loss = draw_or_resign_cfg.get("resign_for_egtb_minus_two", True)
        resign = bool(can_resign and resign_on_egtb_loss and wdl == -2)
        return chess.engine.PlayResult(best_move, None, draw_offered=offer_draw, resigned=resign)
    return chess.engine.PlayResult(None, None)


def choose_move(engine, board, game, ponder, draw_offered, start_time, move_overhead):
    pre_move_time = int((time.perf_counter_ns() - start_time) / 1e6)
    overhead = pre_move_time + move_overhead
    wb = "w" if board.turn == chess.WHITE else "b"
    game.state[f"{wb}time"] = max(0, game.state[f"{wb}time"] - overhead)
    logger.info("Searching for wtime {wtime} btime {btime}".format_map(game.state))
    return engine.search_with_ponder(board,
                                     game.state["wtime"],
                                     game.state["btime"],
                                     game.state["winc"],
                                     game.state["binc"],
                                     ponder,
                                     draw_offered)


def check_for_draw_offer(game):
    return game.state.get(f"{game.opponent_color[0]}draw", False)


def fake_thinking(config, board, game):
    if config.get("fake_think_time") and len(board.move_stack) > 9:
        delay = min(game.clock_initial, game.my_remaining_seconds()) * 0.015
        accel = 1 - max(0, min(100, len(board.move_stack) - 20)) / 150
        sleep = min(5, delay * accel)
        time.sleep(sleep)


def print_move_number(board):
    logger.info("")
    logger.info(f"move: {len(board.move_stack) // 2 + 1}")


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

        commentary = engine.comment_for_board_index(index) or {}
        pv_node = current_node.parent.add_line(commentary.get("pv", []))
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
    li = lichess.Lichess(CONFIG["token"], CONFIG["url"], __version__, logging_level)

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
        start_lichess_bot()
    except Exception:
        logger.exception("Quitting lichess-bot due to an error:")
