"""Provides communication with the engine."""
from __future__ import annotations
import os
import chess.engine
import chess.polyglot
import chess.syzygy
import chess.gaviota
import chess
import subprocess
import logging
import datetime
import time
import random
import math
import contextlib
from collections import Counter
from collections.abc import Callable
from lib import model, lichess
from lib.config import Configuration, change_value_to_list
from lib.timer import Timer, msec, seconds, msec_str, sec_str, to_seconds
from lib.lichess_types import (ReadableType, ChessDBMoveType, LichessEGTBMoveType, OPTIONS_GO_EGTB_TYPE, OPTIONS_TYPE,
                       COMMANDS_TYPE, MOVE, InfoStrDict, InfoDictKeys, InfoDictValue, GO_COMMANDS_TYPE, EGTPATH_TYPE,
                       ENGINE_INPUT_ARGS_TYPE, ENGINE_INPUT_KWARGS_TYPE)
from extra_game_handlers import game_specific_options
from operator import itemgetter
from typing import Any, Optional, Union, Literal, cast
from types import TracebackType


logger = logging.getLogger(__name__)

out_of_online_opening_book_moves: Counter[str] = Counter()


def create_engine(engine_config: Configuration, game: Optional[model.Game] = None) -> EngineWrapper:
    """
    Create the engine.

    Use in a with-block to automatically close the engine when exiting the game.

    :param engine_config: The options for the engine.
    :return: An engine. Either UCI, XBoard, or Homemade.
    """
    cfg = engine_config.engine
    engine_path = os.path.abspath(os.path.join(cfg.dir, cfg.name))
    engine_type = cfg.protocol
    commands = []
    if cfg.interpreter:
        commands.append(cfg.interpreter)
        commands.extend(cfg.interpreter_options)
    commands.append(engine_path)
    if cfg.engine_options:
        for k, v in cfg.engine_options.items():
            commands.append(f"--{k}={v}" if v is not None else f"--{k}")

    stderr = None if cfg.silence_stderr else subprocess.DEVNULL

    Engine: type[Union[UCIEngine, XBoardEngine, MinimalEngine]]
    if engine_type == "xboard":
        Engine = XBoardEngine
    elif engine_type == "uci":
        Engine = UCIEngine
    elif engine_type == "homemade":
        Engine = get_homemade_engine(cfg.name)
    else:
        raise ValueError(
            f"    Invalid engine type: {engine_type}. Expected xboard, uci, or homemade.")
    options = remove_managed_options(cfg.lookup(f"{engine_type}_options") or Configuration({}))
    logger.debug(f"Starting engine: {commands}")
    return Engine(commands, options, stderr, cfg.draw_or_resign, game, cwd=cfg.working_dir)


def remove_managed_options(config: Configuration) -> OPTIONS_GO_EGTB_TYPE:
    """Remove the options managed by python-chess."""
    def is_managed(key: str) -> bool:
        return chess.engine.Option(key, "", None, None, None, None).is_managed()

    return {name: value for (name, value) in config.items() if not is_managed(name)}


PONDERPV_CHARACTERS = 6  # The length of ", Pv: ".


class EngineWrapper:
    """A wrapper used by all engines (UCI, XBoard, Homemade)."""

    def __init__(self, options: OPTIONS_GO_EGTB_TYPE, draw_or_resign: Configuration) -> None:
        """
        Initialize the values of the wrapper used by all engines (UCI, XBoard, Homemade).

        :param options: The options to send to the engine.
        :param draw_or_resign: Options on whether the bot should resign or offer draws.
        """
        self.engine: Union[chess.engine.SimpleEngine, FillerEngine]
        self.scores: list[chess.engine.PovScore] = []
        self.draw_or_resign = draw_or_resign
        self.go_commands = Configuration(cast(GO_COMMANDS_TYPE, options.pop("go_commands", {})) or {})
        self.move_commentary: list[InfoStrDict] = []
        self.comment_start_index = -1

    def configure(self, options: OPTIONS_GO_EGTB_TYPE, game: Optional[model.Game]) -> None:
        """
        Send configurations to the engine.

        :param options: A dictionary of strings to option values.

        Raises chess.engine.EngineError if an option is sent that the engine does not support.
        """
        try:
            extra_options = {} if game is None else game_specific_options(game)
            self.engine.configure(cast(OPTIONS_TYPE, options | extra_options))
        except Exception:
            self.engine.close()
            raise

    def __enter__(self) -> EngineWrapper:  # noqa: PYI034 (return Self not available until 3.11)
        """Enter context so engine communication will be properly shutdown."""
        self.engine.__enter__()
        return self

    def __exit__(self, exc_type: Optional[type[BaseException]],
                 exc_value: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> None:
        """Exit context and allow engine to shutdown nicely if there was no exception."""
        if exc_type is None:
            self.ping()
            self.quit()
        self.engine.__exit__(exc_type, exc_value, traceback)

    def play_move(self,
                  board: chess.Board,
                  game: model.Game,
                  li: lichess.Lichess,
                  setup_timer: Timer,
                  move_overhead: datetime.timedelta,
                  can_ponder: bool,
                  is_correspondence: bool,
                  correspondence_move_time: datetime.timedelta,
                  engine_cfg: Configuration,
                  min_time: datetime.timedelta) -> None:
        """
        Play a move.

        :param board: The current position.
        :param game: The game that the bot is playing.
        :param li: Provides communication with lichess.org.
        :param start_time: The time that the bot received the move.
        :param move_overhead: The time it takes to communicate between the engine and lichess.org.
        :param can_ponder: Whether the engine is allowed to ponder.
        :param is_correspondence: Whether this is a correspondence or unlimited game.
        :param correspondence_move_time: The time the engine will think if `is_correspondence` is true.
        :param engine_cfg: Options for external moves (e.g. from an opening book), and for engine resignation and draw offers.
        :param min_time: Minimum time to spend, in seconds.
        :return: The move to play.
        """
        polyglot_cfg = engine_cfg.polyglot
        online_moves_cfg = engine_cfg.online_moves
        draw_or_resign_cfg = engine_cfg.draw_or_resign
        lichess_bot_tbs = engine_cfg.lichess_bot_tbs

        best_move: MOVE
        best_move = get_book_move(board, game, polyglot_cfg)

        if best_move.move is None:
            best_move = get_egtb_move(board,
                                      game,
                                      lichess_bot_tbs,
                                      draw_or_resign_cfg)

        if not isinstance(best_move, list) and best_move.move is None:
            best_move = get_online_move(li,
                                        board,
                                        game,
                                        online_moves_cfg,
                                        draw_or_resign_cfg)

        if isinstance(best_move, list) or best_move.move is None:
            draw_offered = check_for_draw_offer(game)

            time_limit, can_ponder = move_time(board, game, can_ponder,
                                               setup_timer, move_overhead,
                                               is_correspondence, correspondence_move_time)

            try:
                best_move = self.search(board, time_limit, can_ponder, draw_offered, best_move)
            except chess.engine.EngineError as error:
                BadMove = (chess.IllegalMoveError, chess.InvalidMoveError)
                if not any(isinstance(e, BadMove) for e in error.args):
                    raise
                logger.error("Ending game due to bot attempting an illegal move.")
                logger.error(error)
                game_ender = li.abort if game.is_abortable() else li.resign
                game_ender(game.id)
                return

        # Heed min_time
        elapsed = setup_timer.time_since_reset()
        if elapsed < min_time:
            time.sleep(to_seconds(min_time - elapsed))

        self.add_comment(best_move, board)
        self.print_stats()
        if best_move.resigned and len(board.move_stack) >= 2:
            li.resign(game.id)
        else:
            li.make_move(game.id, best_move)

    def add_go_commands(self, time_limit: chess.engine.Limit) -> chess.engine.Limit:
        """Add extra commands to send to the engine. For example, to search for 1000 nodes or up to depth 10."""
        movetime_cfg = self.go_commands.movetime
        if movetime_cfg is not None:
            movetime = msec(movetime_cfg)
            if time_limit.time is None or seconds(time_limit.time) > movetime:
                time_limit.time = to_seconds(movetime)
        time_limit.depth = self.go_commands.depth
        time_limit.nodes = self.go_commands.nodes
        return time_limit

    def offer_draw_or_resign(self, result: chess.engine.PlayResult, board: chess.Board) -> chess.engine.PlayResult:
        """Offer draw or resign depending on the score of the engine."""
        def actual(score: chess.engine.PovScore) -> int:
            return score.relative.score(mate_score=40000)

        can_offer_draw = self.draw_or_resign.offer_draw_enabled
        draw_offer_moves = self.draw_or_resign.offer_draw_moves
        draw_score_range: int = self.draw_or_resign.offer_draw_score
        draw_max_piece_count = self.draw_or_resign.offer_draw_pieces
        pieces_on_board = chess.popcount(board.occupied)
        enough_pieces_captured = pieces_on_board <= draw_max_piece_count
        if can_offer_draw and len(self.scores) >= draw_offer_moves and enough_pieces_captured:
            scores = self.scores[-draw_offer_moves:]

            def score_near_draw(score: chess.engine.PovScore) -> bool:
                return abs(actual(score)) <= draw_score_range
            if len(scores) == len(list(filter(score_near_draw, scores))):
                result.draw_offered = True

        resign_enabled = self.draw_or_resign.resign_enabled
        min_moves_for_resign = self.draw_or_resign.resign_moves
        resign_score: int = self.draw_or_resign.resign_score
        if resign_enabled and len(self.scores) >= min_moves_for_resign:
            scores = self.scores[-min_moves_for_resign:]

            def score_near_loss(score: chess.engine.PovScore) -> bool:
                return actual(score) <= resign_score
            if len(scores) == len(list(filter(score_near_loss, scores))):
                result.resigned = True
        return result

    def search(self, board: chess.Board, time_limit: chess.engine.Limit, ponder: bool, draw_offered: bool,
               root_moves: MOVE) -> chess.engine.PlayResult:
        """
        Tell the engine to search.

        :param board: The current position.
        :param time_limit: Conditions for how long the engine can search (e.g. we have 10 seconds and search up to depth 10).
        :param ponder: Whether the engine can ponder.
        :param draw_offered: Whether the bot was offered a draw.
        :param root_moves: If it is a list, the engine will only play a move that is in `root_moves`.
        :return: The move to play.
        """
        time_limit = self.add_go_commands(time_limit)
        result = self.engine.play(board,
                                  time_limit,
                                  info=chess.engine.INFO_ALL,
                                  ponder=ponder,
                                  draw_offered=draw_offered,
                                  root_moves=root_moves if isinstance(root_moves, list) else None)
        # Use null_score to have no effect on draw/resign decisions
        null_score = chess.engine.PovScore(chess.engine.Mate(1), board.turn)
        self.scores.append(result.info.get("score", null_score))
        return self.offer_draw_or_resign(result, board)

    def comment_index(self, move_stack_index: int) -> int:
        """
        Get the index of a move for use in `comment_for_board_index`.

        :param move_stack_index: The move number.
        :return: The index of the move in `self.move_commentary`.
        """
        if self.comment_start_index < 0:
            return -1
        return move_stack_index - self.comment_start_index

    def comment_for_board_index(self, index: int) -> InfoStrDict:
        """
        Get the engine comments for a specific move.

        :param index: The move number.
        :return: The move comments.
        """
        no_info: InfoStrDict = {}
        comment_index = self.comment_index(index)
        if comment_index < 0 or comment_index % 2 != 0:
            return no_info

        try:
            return self.move_commentary[comment_index // 2]
        except IndexError:
            return no_info

    def add_comment(self, move: chess.engine.PlayResult, board: chess.Board) -> None:
        """
        Store the move's comments.

        :param move: The move. Contains the comments in `move.info`.
        :param board: The current position.
        """
        if self.comment_start_index < 0:
            self.comment_start_index = len(board.move_stack)
        move_info = cast(InfoStrDict, dict(move.info.copy() if move.info else {}))
        if "pv" in move_info:
            move_info["ponderpv"] = board.variation_san(move.info["pv"])
        if "refutation" in move_info:
            move_info["refutation"] = board.variation_san(move.info["refutation"])
        if "currmove" in move_info:
            move_info["currmove"] = board.san(move.info["currmove"])
        self.move_commentary.append(move_info)

    def discard_last_move_commentary(self) -> None:
        """
        Remove the commentary for the last move, if any.

        Used after allowing an opponent to take back a move.
        """
        with contextlib.suppress(IndexError):
            self.move_commentary.pop()

    def print_stats(self) -> None:
        """Print the engine stats."""
        for line in self.get_stats():
            logger.info(line)

    def readable_score(self, relative_score: chess.engine.PovScore) -> str:
        """Convert the score to a more human-readable format."""
        score = relative_score.relative
        cp_score = score.score()
        if cp_score is None:
            str_score = f"#{score.mate()}"
        else:
            str_score = str(round(cp_score / 100, 2))
        return str_score

    def readable_wdl(self, wdl: chess.engine.PovWdl) -> str:
        """Convert the WDL score to a percentage, so it is more human-readable."""
        wdl_percentage = round(wdl.relative.expectation() * 100, 1)
        return f"{wdl_percentage}%"

    def readable_time(self, number: int) -> str:
        """Convert time given as a number into minutes and seconds, so it is more human-readable. e.g. 123 -> 2m 3s."""
        minutes, seconds = divmod(number, 60)
        if minutes >= 1:
            return f"{minutes:0.0f}m {seconds:0.1f}s"
        else:
            return f"{seconds:0.1f}s"

    def readable_number(self, number: int) -> str:
        """Convert number to a more human-readable format. e.g. 123456789 -> 123M."""
        if number >= 1e9:
            return f"{round(number / 1e9, 1)}B"
        if number >= 1e6:
            return f"{round(number / 1e6, 1)}M"
        if number >= 1e3:
            return f"{round(number / 1e3, 1)}K"
        return str(number)

    def to_readable_value(self, stat: InfoDictKeys, info: InfoStrDict) -> str:
        """Change a value to a more human-readable format."""
        readable: ReadableType = {"Evaluation": self.readable_score, "Winrate": self.readable_wdl,
                                  "Hashfull": lambda x: f"{round(x / 10, 1)}%", "Nodes": self.readable_number,
                                  "Speed": lambda x: f"{self.readable_number(x)}nps", "Tbhits": self.readable_number,
                                  "Cpuload": lambda x: f"{round(x / 10, 1)}%", "Movetime": self.readable_time}

        def identity(x: InfoDictValue) -> str:
            return str(x)

        func = cast(Callable[[InfoDictValue], str], readable.get(stat, identity))
        return str(func(info[stat]))

    def get_stats(self, for_chat: bool = False) -> list[str]:
        """
        Get the stats returned by the engine.

        :param for_chat: Whether the stats will be sent to the game chat, which has a 140 character limit.
        """
        can_index = self.move_commentary and self.move_commentary[-1]
        info: InfoStrDict = self.move_commentary[-1].copy() if can_index else {}

        def to_readable_item(stat: InfoDictKeys, value: InfoDictValue) -> tuple[InfoDictKeys, InfoDictValue]:
            readable = {"wdl": "winrate", "ponderpv": "PV", "nps": "speed", "score": "evaluation", "time": "movetime"}
            stat = cast(InfoDictKeys, readable.get(stat, stat))
            if stat == "string" and isinstance(value, str) and value.startswith("lichess-bot-source:"):
                stat = "Source"
                value = value.split(":", 1)[1]
            return cast(InfoDictKeys, stat.title()), value

        info = cast(InfoStrDict, dict(to_readable_item(cast(InfoDictKeys, key), cast(InfoDictValue, value))
                                      for (key, value) in info.items()))
        if "Source" not in info:
            info["Source"] = "Engine"

        stats = ["Source", "Evaluation", "Winrate", "Depth", "Nodes", "Speed", "Pv"]
        if for_chat and "Pv" in info:
            bot_stats = [f"{stat}: {self.to_readable_value(cast(InfoDictKeys, stat), info)}"
                         for stat in stats if stat in info and stat != "Pv"]
            len_bot_stats = len(", ".join(bot_stats)) + PONDERPV_CHARACTERS
            ponder_pv = info["Pv"].split()
            try:
                while len(" ".join(ponder_pv)) + len_bot_stats > lichess.MAX_CHAT_MESSAGE_LEN:
                    ponder_pv.pop()
                if ponder_pv[-1].endswith("."):
                    ponder_pv.pop()
                info["Pv"] = " ".join(ponder_pv)
            except IndexError:
                pass
            if not info["Pv"]:
                info.pop("Pv")
        return [f"{stat}: {self.to_readable_value(cast(InfoDictKeys, stat), info)}" for stat in stats if stat in info]

    def get_opponent_info(self, game: model.Game) -> None:
        """Get the opponent's information and sends it to the engine."""
        opponent = chess.engine.Opponent(name=game.opponent.name,
                                         title=game.opponent.title,
                                         rating=game.opponent.rating,
                                         is_engine=game.opponent.is_bot)
        self.engine.send_opponent_information(opponent=opponent, engine_rating=game.me.rating)

    def name(self) -> str:
        """Get the name of the engine."""
        return self.engine.id["name"]

    def get_pid(self) -> str:
        """Get the pid of the engine."""
        pid = "?"
        if self.engine.transport is not None:
            pid = str(self.engine.transport.get_pid())
        return pid

    def ping(self) -> None:
        """Ping the engine."""
        self.engine.ping()

    def send_game_result(self, game: model.Game, board: chess.Board) -> None:
        """
        Inform engine of the game ending.

        :param game: The final game state from lichess.
        :param board: The final board state.
        """
        termination = game.state.get("status")
        winner = game.state.get("winner")
        winning_color = chess.WHITE if winner == "white" else chess.BLACK

        if termination == model.Termination.MATE:
            self.engine.send_game_result(board)
        elif termination == model.Termination.RESIGN:
            resigner = "White" if winner == "black" else "Black"
            self.engine.send_game_result(board, winning_color, f"{resigner} resigned")
        elif termination == model.Termination.ABORT:
            self.engine.send_game_result(board, None, "Game aborted", False)
        elif termination == model.Termination.DRAW:
            draw_reason = None if board.is_game_over(claim_draw=True) else "Draw by agreement"
            self.engine.send_game_result(board, None, draw_reason)
        elif termination == model.Termination.TIMEOUT:
            if winner:
                self.engine.send_game_result(board, winning_color, "Time forfeiture")
            else:
                self.engine.send_game_result(board, None, "Time out with insufficient material")
        else:
            self.engine.send_game_result(board, None, termination)

    def quit(self) -> None:
        """Tell the engine to shut down."""
        self.engine.quit()


class UCIEngine(EngineWrapper):
    """The class used to communicate with UCI engines."""

    def __init__(self, commands: COMMANDS_TYPE, options: OPTIONS_GO_EGTB_TYPE, stderr: Optional[int],
                 draw_or_resign: Configuration, game: Optional[model.Game], **popen_args: str) -> None:
        """
        Communicate with UCI engines.

        :param commands: The engine path and commands to send to the engine. e.g. ["engines/engine.exe", "--option1=value1"]
        :param options: The options to send to the engine.
        :param stderr: Whether we should silence the stderr.
        :param draw_or_resign: Options on whether the bot should resign or offer draws.
        :param game: The first Game message from the game stream.
        :param popen_args: The cwd of the engine.
        """
        super().__init__(options, draw_or_resign)
        self.engine = chess.engine.SimpleEngine.popen_uci(commands, timeout=10., debug=False, setpgrp=True, stderr=stderr,
                                                          **popen_args)
        self.configure(options, game)


class XBoardEngine(EngineWrapper):
    """The class used to communicate with XBoard engines."""

    def __init__(self, commands: COMMANDS_TYPE, options: OPTIONS_GO_EGTB_TYPE, stderr: Optional[int],
                 draw_or_resign: Configuration, game: Optional[model.Game], **popen_args: str) -> None:
        """
        Communicate with XBoard engines.

        :param commands: The engine path and commands to send to the engine. e.g. ["engines/engine.exe", "--option1=value1"]
        :param options: The options to send to the engine.
        :param stderr: Whether we should silence the stderr.
        :param draw_or_resign: Options on whether the bot should resign or offer draws.
        :param game: The first Game message from the game stream.
        :param popen_args: The cwd of the engine.
        """
        super().__init__(options, draw_or_resign)
        self.engine = chess.engine.SimpleEngine.popen_xboard(commands, timeout=10., debug=False, setpgrp=True,
                                                             stderr=stderr, **popen_args)
        egt_paths = cast(EGTPATH_TYPE, options.pop("egtpath", {}) or {})
        protocol = cast(chess.engine.XBoardProtocol, self.engine.protocol)
        egt_features = protocol.features.get("egt", "")
        if isinstance(egt_features, str):
            egt_types_from_engine = egt_features.split(",")
            for egt_type in filter(None, egt_types_from_engine):
                if egt_type in egt_paths:
                    options[f"egtpath {egt_type}"] = egt_paths[egt_type]
                else:
                    logger.debug(f"No paths found for egt type: {egt_type}.")
        self.configure(options, game)


class MinimalEngine(EngineWrapper):
    """
    Subclass this to prevent a few random errors.

    Even though MinimalEngine extends EngineWrapper,
    you don't have to actually wrap an engine.

    At minimum, just implement `search`,
    however you can also change other methods like
    `notify`, etc.
    """

    def __init__(self, commands: COMMANDS_TYPE, options: OPTIONS_GO_EGTB_TYPE, stderr: Optional[int],  # noqa: ARG002
                 draw_or_resign: Configuration, game: Optional[model.Game] = None, name: Optional[str] = None,  # noqa: ARG002
                 **popen_args: str) -> None:  # noqa: ARG002 Unused argument popen_args
        """
        Initialize the values of the engine that all homemade engines inherit.

        :param options: The options to send to the engine.
        :param draw_or_resign: Options on whether the bot should resign or offer draws.
        """
        super().__init__(options, draw_or_resign)

        self.engine_name = self.__class__.__name__ if name is None else name

        self.engine = FillerEngine(self, name=self.engine_name)

    def get_pid(self) -> str:
        """Homemade engines don't have a pid, so we return a question mark."""
        return "?"

    def search(self, board: chess.Board, time_limit: chess.engine.Limit, ponder: bool, draw_offered: bool,
               root_moves: MOVE) -> chess.engine.PlayResult:
        """
        Choose a move.

        The method to be implemented in your homemade engine.
        NOTE: This method must return an instance of "chess.engine.PlayResult"
        """
        raise NotImplementedError("The search method is not implemented")

    def notify(self, method_name: str, *args: ENGINE_INPUT_ARGS_TYPE, **kwargs: ENGINE_INPUT_KWARGS_TYPE
               ) -> Any:
        """
        Enable the use of `self.engine.option1`.

        The EngineWrapper class sometimes calls methods on "self.engine".

        "self.engine" is a filler property that notifies <self>
        whenever an attribute is called.

        Nothing happens unless the main engine does something.

        Simply put, the following code is equivalent
        self.engine.<method_name>(<*args>, <**kwargs>)
        self.notify(<method_name>, <*args>, <**kwargs>)
        """


class FillerEngine:
    """
    Not meant to be an actual engine.

    This is only used to provide the property "self.engine"
    in "MinimalEngine" which extends "EngineWrapper"
    """

    def __init__(self, main_engine: MinimalEngine, name: str = "") -> None:
        """:param name: The name to send to the chat."""
        self.id = {"name": name}
        self.name = name
        self.main_engine = main_engine

    def __getattr__(self, method_name: str) -> Any:
        """Provide the property `self.engine`."""
        main_engine = self.main_engine

        # These types aren't tested by mypy.
        def method(*args: ENGINE_INPUT_ARGS_TYPE, **kwargs: ENGINE_INPUT_KWARGS_TYPE) -> Any:
            nonlocal main_engine
            nonlocal method_name
            return main_engine.notify(method_name, *args, **kwargs)

        return method


test_suffix = "-for-lichess-bot-testing-only"


def get_homemade_engine(name: str) -> type[MinimalEngine]:
    """
    Get the homemade engine with name `name`. e.g. If `name` is `RandomMove` then we will return `homemade.RandomMove`.

    :param name: The name of the homemade engine.
    :return: The engine with this name.
    """
    import homemade
    from test_bot import homemade as test_homemade
    engine: type[MinimalEngine]
    if name.endswith(test_suffix):  # Test only.
        engine = getattr(test_homemade, name.removesuffix(test_suffix))
    else:
        engine = getattr(homemade, name)
    return engine


def move_time(board: chess.Board,
              game: model.Game,
              can_ponder: bool,
              setup_timer: Timer,
              move_overhead: datetime.timedelta,
              is_correspondence: bool,
              correspondence_move_time: datetime.timedelta) -> tuple[chess.engine.Limit, bool]:
    """
    Determine the game clock settings for the current move.

    :param Board: The current position.
    :param game: Information about the current game.
    :param setup_timer: How much time has passed since receiving the opponent's move.
    :param move_overhead: How much time it takes to communicate with lichess.
    :param can_ponder: Whether the bot is allowed to ponder after choosing a move.
    :param is_correspondence: Whether the current game is a correspondence game.
    :param correspondence_move_time: How much time to use for this move it it is a correspondence game.
    :return: The time to choose a move and whether the bot can ponder after the move.
    """
    if len(board.move_stack) < 2:
        return first_move_time(game), False  # No pondering after the first move since a new clock starts afterwards.
    if is_correspondence:
        return single_move_time(board, game, correspondence_move_time, setup_timer, move_overhead), can_ponder
    return game_clock_time(board, game, setup_timer, move_overhead), can_ponder


def wbtime(board: chess.Board) -> Literal["wtime", "btime"]:
    """Return `wtime` if it is white's turn to move else `btime`."""
    return "wtime" if board.turn == chess.WHITE else "btime"


def wbinc(board: chess.Board) -> Literal["winc", "binc"]:
    """Return `winc` if it is white's turn to move else `binc`."""
    return "winc" if board.turn == chess.WHITE else "binc"


def single_move_time(board: chess.Board, game: model.Game, search_time: datetime.timedelta,
                     setup_timer: Timer, move_overhead: datetime.timedelta) -> chess.engine.Limit:
    """
    Calculate time to search in correspondence games.

    :param board: The current positions.
    :param game: The game that the bot is playing.
    :param search_time: How long the engine should search.
    :param setup_timer: How much time has passed since receiving the opponent's move.
    :param move_overhead: The time it takes to communicate between the engine and lichess-bot.
    :return: The time to choose a move.
    """
    pre_move_time = setup_timer.time_since_reset()
    overhead = pre_move_time + move_overhead
    clock_time = max(msec(1), msec(game.state[wbtime(board)]) - overhead)
    search_time = min(search_time, clock_time)
    logger.info(f"Searching for time {sec_str(search_time)} seconds for game {game.id}")
    return chess.engine.Limit(time=to_seconds(search_time), clock_id="correspondence")


def first_move_time(game: model.Game) -> chess.engine.Limit:
    """
    Determine time limit for the first move in the game.

    :param game: The game that the bot is playing.
    :return: The time to choose the first move.
    """
    # Need to hardcode first movetime since Lichess has 30 sec limit.
    search_time = seconds(10)
    logger.info(f"Searching for time {sec_str(search_time)} seconds for game {game.id}")
    return chess.engine.Limit(time=to_seconds(search_time), clock_id="first move")


def game_clock_time(board: chess.Board,
                    game: model.Game,
                    setup_timer: Timer,
                    move_overhead: datetime.timedelta) -> chess.engine.Limit:
    """
    Get the time to play by the engine in realtime games.

    :param board: The current positions.
    :param game: The game that the bot is playing.
    :param setup_timer: How much time has passed since receiving the opponent's move.
    :param move_overhead: The time it takes to communicate between the engine and lichess-bot.
    :return: The time to play a move.
    """
    pre_move_time = setup_timer.time_since_reset()
    overhead = pre_move_time + move_overhead
    times = {"wtime": msec(game.state["wtime"]), "btime": msec(game.state["btime"])}
    side = wbtime(board)
    times[side] = max(msec(1), times[side] - overhead)
    logger.info(f"Searching for wtime {msec_str(times['wtime'])} btime {msec_str(times['btime'])} for game {game.id}")
    return chess.engine.Limit(white_clock=to_seconds(times["wtime"]),
                              black_clock=to_seconds(times["btime"]),
                              white_inc=to_seconds(msec(game.state["winc"])),
                              black_inc=to_seconds(msec(game.state["binc"])),
                              clock_id="real time")


def check_for_draw_offer(game: model.Game) -> bool:
    """Check if the bot was offered a draw."""
    return bool(game.state.get(f"{game.opponent_color[0]}draw"))


def get_book_move(board: chess.Board, game: model.Game,
                  polyglot_cfg: Configuration) -> chess.engine.PlayResult:
    """Get a move from an opening book."""
    no_book_move = chess.engine.PlayResult(None, None)
    use_book = polyglot_cfg.enabled
    max_game_length = polyglot_cfg.max_depth * 2 - 1
    if not use_book or len(board.move_stack) > max_game_length:
        return no_book_move

    if board.chess960:
        variant = "chess960"
    else:
        variant = "standard" if board.uci_variant == "chess" else str(board.uci_variant)

    change_value_to_list(polyglot_cfg.config, "book", key=variant)
    books = polyglot_cfg.book.lookup(variant)

    for book in books:
        with chess.polyglot.open_reader(book) as reader:
            try:
                selection = polyglot_cfg.selection
                min_weight = polyglot_cfg.min_weight
                if selection == "weighted_random":
                    move = reader.weighted_choice(board).move
                elif selection == "uniform_random":
                    move = reader.choice(board, minimum_weight=min_weight).move
                elif selection == "best_move":
                    move = reader.find(board, minimum_weight=min_weight).move
            except IndexError:
                # python-chess raises "IndexError" if no entries found.
                move = None

        if move is not None:
            logger.info(f"Got move {move} from book {book} for game {game.id}")
            return chess.engine.PlayResult(move, None, {"string": "lichess-bot-source:Opening Book"})

    return no_book_move


def get_online_move(li: lichess.Lichess, board: chess.Board, game: model.Game, online_moves_cfg: Configuration,
                    draw_or_resign_cfg: Configuration) -> Union[chess.engine.PlayResult, list[chess.Move]]:
    """
    Get a move from an online source.

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    online_egtb_cfg = online_moves_cfg.online_egtb
    best_move, wdl, comment = get_online_egtb_move(li, board, game, online_egtb_cfg)
    if best_move is not None:
        can_offer_draw = draw_or_resign_cfg.offer_draw_enabled
        offer_draw_for_zero = draw_or_resign_cfg.offer_draw_for_egtb_zero
        offer_draw = can_offer_draw and offer_draw_for_zero and wdl == 0

        can_resign = draw_or_resign_cfg.resign_enabled
        resign_on_egtb_loss = draw_or_resign_cfg.resign_for_egtb_minus_two
        resign = can_resign and resign_on_egtb_loss and wdl == -2

        wdl_to_score = {2: 9900, 1: 500, 0: 0, -1: -500, -2: -9900}
        comment["score"] = chess.engine.PovScore(chess.engine.Cp(wdl_to_score[wdl]), board.turn)
        if isinstance(best_move, str):
            return chess.engine.PlayResult(chess.Move.from_uci(best_move),
                                           None,
                                           comment,
                                           draw_offered=offer_draw,
                                           resigned=resign)
        return [chess.Move.from_uci(move) for move in best_move]

    max_out_of_book_moves = online_moves_cfg.max_out_of_book_moves
    max_opening_moves = online_moves_cfg.max_depth * 2 - 1
    game_moves = len(board.move_stack)
    if game_moves > max_opening_moves or out_of_online_opening_book_moves[game.id] >= max_out_of_book_moves:
        return chess.engine.PlayResult(None, None)

    chessdb_cfg = online_moves_cfg.chessdb_book
    lichess_cloud_cfg = online_moves_cfg.lichess_cloud_analysis
    opening_explorer_cfg = online_moves_cfg.lichess_opening_explorer

    for online_source, cfg in ((get_chessdb_move, chessdb_cfg),
                               (get_lichess_cloud_move, lichess_cloud_cfg),
                               (get_opening_explorer_move, opening_explorer_cfg)):
        best_move, comment = online_source(li, board, game, cfg)
        if best_move:
            return chess.engine.PlayResult(chess.Move.from_uci(best_move), None, comment)

    out_of_online_opening_book_moves[game.id] += 1
    used_opening_books = chessdb_cfg.enabled or lichess_cloud_cfg.enabled or opening_explorer_cfg.enabled
    if out_of_online_opening_book_moves[game.id] == max_out_of_book_moves and used_opening_books:
        logger.info(f"Will stop using online opening books for game {game.id}.")
    return chess.engine.PlayResult(None, None)


def get_chessdb_move(li: lichess.Lichess, board: chess.Board, game: model.Game,
                     chessdb_cfg: Configuration) -> tuple[Optional[str], chess.engine.InfoDict]:
    """Get a move from chessdb.cn's opening book."""
    use_chessdb = chessdb_cfg.enabled
    time_left = msec(game.state[wbtime(board)])
    min_time = seconds(chessdb_cfg.min_time)
    if not use_chessdb or time_left < min_time or board.uci_variant != "chess":
        return None, {}

    move = None
    comment: chess.engine.InfoDict = {}
    site = "https://www.chessdb.cn/cdb.php"
    quality = chessdb_cfg.move_quality
    action = {"best": "querypv",
              "good": "querybest",
              "all": "query"}
    with contextlib.suppress(Exception):
        params: dict[str, Union[str, int]] = {"action": action[quality], "board": board.fen(), "json": 1}
        data = li.online_book_get(site, params=params)
        if data["status"] == "ok":
            if quality == "best":
                depth = data["depth"]
                if depth >= chessdb_cfg.min_depth:
                    score = data["score"]
                    move = data["pv"][0]
                    comment["score"] = chess.engine.PovScore(chess.engine.Cp(score), board.turn)
                    comment["depth"] = data["depth"]
                    comment["pv"] = list(map(chess.Move.from_uci, data["pv"]))
                    comment["string"] = "lichess-bot-source:ChessDB"
                    logger.info(f"Got move {move} from chessdb.cn (depth: {depth}, score: {score}) for game {game.id}")
            else:
                move = data["move"]
                logger.info(f"Got move {move} from chessdb.cn for game {game.id}")

    return move, comment


def get_lichess_cloud_move(li: lichess.Lichess, board: chess.Board, game: model.Game,
                           lichess_cloud_cfg: Configuration) -> tuple[Optional[str], chess.engine.InfoDict]:
    """Get a move from the lichess's cloud analysis."""
    side = wbtime(board)
    time_left = msec(game.state[side])
    min_time = seconds(lichess_cloud_cfg.min_time)
    use_lichess_cloud = lichess_cloud_cfg.enabled
    if not use_lichess_cloud or time_left < min_time:
        return None, {}

    move = None
    comment: chess.engine.InfoDict = {}

    quality = lichess_cloud_cfg.move_quality
    multipv = 1 if quality == "best" else 5
    variant = "standard" if board.uci_variant == "chess" else str(board.uci_variant)  # `str` is there only for mypy.

    with contextlib.suppress(Exception):
        data = li.online_book_get("https://lichess.org/api/cloud-eval",
                                  params={"fen": board.fen(),
                                          "multiPv": multipv,
                                          "variant": variant})
        if "error" not in data:
            depth = data["depth"]
            knodes = data["knodes"]
            min_depth = lichess_cloud_cfg.min_depth
            min_knodes = lichess_cloud_cfg.min_knodes
            if depth >= min_depth and knodes >= min_knodes:
                if quality == "best":
                    pv = data["pvs"][0]
                else:
                    best_eval = data["pvs"][0]["cp"]
                    pvs = data["pvs"]
                    max_difference = lichess_cloud_cfg.max_score_difference
                    if side == "wtime":
                        pvs = list(filter(lambda pv: pv["cp"] >= best_eval - max_difference, pvs))
                    else:
                        pvs = list(filter(lambda pv: pv["cp"] <= best_eval + max_difference, pvs))
                    pv = random.choice(pvs)
                move = pv["moves"].split()[0]
                score = pv["cp"] if side == "wtime" else -pv["cp"]
                comment["score"] = chess.engine.PovScore(chess.engine.Cp(score), board.turn)
                comment["depth"] = data["depth"]
                comment["nodes"] = data["knodes"] * 1000
                comment["pv"] = list(map(chess.Move.from_uci, pv["moves"].split()))
                comment["string"] = "lichess-bot-source:Lichess Cloud Analysis"
                logger.info(f"Got move {move} from lichess cloud analysis (depth: {depth}, score: {score}, knodes: {knodes})"
                            f" for game {game.id}")

    return move, comment


def get_opening_explorer_move(li: lichess.Lichess, board: chess.Board, game: model.Game,
                              opening_explorer_cfg: Configuration
                              ) -> tuple[Optional[str], chess.engine.InfoDict]:
    """Get a move from lichess's opening explorer."""
    side = wbtime(board)
    time_left = msec(game.state[side])
    min_time = seconds(opening_explorer_cfg.min_time)
    source = opening_explorer_cfg.source
    if not opening_explorer_cfg.enabled or time_left < min_time or source == "master" and board.uci_variant != "chess":
        return None, {}

    move = None
    comment: chess.engine.InfoDict = {}
    variant = "standard" if board.uci_variant == "chess" else str(board.uci_variant)  # `str` is there only for mypy
    with contextlib.suppress(Exception):
        params: dict[str, Union[str, int]]
        if source == "masters":
            params = {"fen": board.fen(), "moves": 100}
            response = li.online_book_get("https://explorer.lichess.ovh/masters", params)
            comment = {"string": "lichess-bot-source:Lichess Opening Explorer (Masters)"}
        elif source == "player":
            player = opening_explorer_cfg.player_name
            if not player:
                player = game.username
            params = {"player": player, "fen": board.fen(), "moves": 100, "variant": variant,
                      "recentGames": 0, "color": "white" if side == "wtime" else "black"}
            response = li.online_book_get("https://explorer.lichess.ovh/player", params, True)
            comment = {"string": "lichess-bot-source:Lichess Opening Explorer (Player)"}
        else:
            params = {"fen": board.fen(), "moves": 100, "variant": variant, "topGames": 0, "recentGames": 0}
            response = li.online_book_get("https://explorer.lichess.ovh/lichess", params)
            comment = {"string": "lichess-bot-source:Lichess Opening Explorer (Lichess)"}
        moves = []
        for possible_move in response["moves"]:
            games_played = possible_move["white"] + possible_move["black"] + possible_move["draws"]
            winrate = (possible_move["white"] + possible_move["draws"] * .5) / games_played
            if side == "btime":
                winrate = 1 - winrate
            if games_played >= opening_explorer_cfg.min_games:
                # We add both winrate and games_played to the tuple, so that if 2 moves are tied on the first metric,
                # the second one will be used.
                moves.append((winrate if opening_explorer_cfg.sort == "winrate" else games_played,
                              games_played if opening_explorer_cfg.sort == "winrate" else winrate, possible_move["uci"]))
        moves.sort(reverse=True)
        move = moves[0][2]
        logger.info(f"Got move {move} from lichess opening explorer ({opening_explorer_cfg.sort}: {moves[0][0]})"
                    f" for game {game.id}")

    return move, comment


def get_online_egtb_move(li: lichess.Lichess, board: chess.Board, game: model.Game, online_egtb_cfg: Configuration
                         ) -> tuple[Union[str, list[str], None], int, chess.engine.InfoDict]:
    """
    Get a move from an online egtb (either by lichess or chessdb).

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    use_online_egtb = online_egtb_cfg.enabled
    pieces = chess.popcount(board.occupied)
    source = online_egtb_cfg.source
    minimum_time = seconds(online_egtb_cfg.min_time)
    time_left = game.state[wbtime(board)]
    if (not use_online_egtb
            or msec(time_left) < minimum_time
            or board.uci_variant not in ["chess", "antichess", "atomic"]
            and source == "lichess"
            or board.uci_variant != "chess"
            and source == "chessdb"
            or pieces > online_egtb_cfg.max_pieces
            or board.castling_rights):

        return None, -3, {}

    quality = online_egtb_cfg.move_quality
    variant = "standard" if board.uci_variant == "chess" else str(board.uci_variant)

    with contextlib.suppress(Exception):
        if source == "lichess":
            return get_lichess_egtb_move(li, game, board, quality, variant)
        if source == "chessdb":
            return get_chessdb_egtb_move(li, game, board, quality)

    return None, -3, {}


def get_egtb_move(board: chess.Board, game: model.Game, lichess_bot_tbs: Configuration,
                  draw_or_resign_cfg: Configuration) -> Union[chess.engine.PlayResult, list[chess.Move]]:
    """
    Get a move from a local egtb.

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    best_move, wdl = get_syzygy(board, game, lichess_bot_tbs.syzygy)
    source = "lichess-bot-source:Syzygy EGTB"
    if best_move is None:
        best_move, wdl = get_gaviota(board, game, lichess_bot_tbs.gaviota)
        source = "lichess-bot-source:Gaviota EGTB"
    if best_move:
        can_offer_draw = draw_or_resign_cfg.offer_draw_enabled
        offer_draw_for_zero = draw_or_resign_cfg.offer_draw_for_egtb_zero
        offer_draw = bool(can_offer_draw and offer_draw_for_zero and wdl == 0)

        can_resign = draw_or_resign_cfg.resign_enabled
        resign_on_egtb_loss = draw_or_resign_cfg.resign_for_egtb_minus_two
        resign = bool(can_resign and resign_on_egtb_loss and wdl == -2)
        wdl_to_score = {2: 9900, 1: 500, 0: 0, -1: -500, -2: -9900}
        comment: chess.engine.InfoDict = {"score": chess.engine.PovScore(chess.engine.Cp(wdl_to_score[wdl]), board.turn),
                                          "string": source}
        if isinstance(best_move, chess.Move):
            return chess.engine.PlayResult(best_move, None, comment, draw_offered=offer_draw, resigned=resign)
        return best_move
    return chess.engine.PlayResult(None, None)


def get_lichess_egtb_move(li: lichess.Lichess, game: model.Game, board: chess.Board, quality: str,
                          variant: str) -> tuple[Union[str, list[str], None], int, chess.engine.InfoDict]:
    """
    Get a move from lichess's egtb.

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    name_to_wld = {"loss": -2,
                   "maybe-loss": -1,
                   "blessed-loss": -1,
                   "draw": 0,
                   "cursed-win": 1,
                   "maybe-win": 1,
                   "win": 2}
    pieces = chess.popcount(board.occupied)
    max_pieces = 7 if board.uci_variant == "chess" else 6
    if pieces <= max_pieces:
        data = li.online_book_get(f"https://tablebase.lichess.ovh/{variant}",
                                  params={"fen": board.fen()})
        if quality == "best":
            move = data["moves"][0]["uci"]
            wdl = name_to_wld[data["moves"][0]["category"]] * -1
            dtz = data["moves"][0]["dtz"] * -1
            dtm = data["moves"][0]["dtm"]
            if dtm:
                dtm *= -1
            logger.info(f"Got move {move} from tablebase.lichess.ovh (wdl: {wdl}, dtz: {dtz}, dtm: {dtm}) for game {game.id}")
        else:  # quality == "suggest":
            best_wdl = name_to_wld[data["moves"][0]["category"]] * -1

            def good_enough(possible_move: LichessEGTBMoveType) -> bool:
                return name_to_wld[possible_move["category"]] * -1 == best_wdl

            possible_moves = list(filter(good_enough, data["moves"]))
            if len(possible_moves) > 1:
                move_list = [move["uci"] for move in possible_moves]
                wdl = best_wdl
                logger.info(f"Suggesting moves from tablebase.lichess.ovh (wdl: {wdl}) for game {game.id}")
                return move_list, wdl, {"string": "lichess-bot-source:Lichess EGTB"}
            else:
                best_move = possible_moves[0]
                move = best_move["uci"]
                wdl = name_to_wld[best_move["category"]] * -1
                dtz = best_move["dtz"] * -1
                dtm = best_move["dtm"]
                if dtm:
                    dtm *= -1
                logger.info(f"Got move {move} from tablebase.lichess.ovh (wdl: {wdl}, dtz: {dtz}, dtm: {dtm})"
                            f" for game {game.id}")

        return move, wdl, {"string": "lichess-bot-source:Lichess EGTB"}
    return None, -3, {}


def get_chessdb_egtb_move(li: lichess.Lichess, game: model.Game, board: chess.Board,
                          quality: str) -> tuple[Union[str, list[str], None], int, chess.engine.InfoDict]:
    """
    Get a move from chessdb's egtb.

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    def score_to_wdl(score: int) -> int:
        return piecewise_function([(-20000, "e", -2),
                                   (0, "e", -1),
                                   (0, "i", 0),
                                   (20000, "i", 1)], 2, score)

    def score_to_dtz(score: int) -> int:
        return piecewise_function([(-20000, "e", -30000 - score),
                                   (0, "e", -20000 - score),
                                   (0, "i", 0),
                                   (20000, "i", 20000 - score)], 30000 - score, score)

    action = "querypv" if quality == "best" else "queryall"
    data = li.online_book_get("https://www.chessdb.cn/cdb.php",
                              params={"action": action, "board": board.fen(), "json": 1})
    if data["status"] == "ok":
        if quality == "best":
            score = data["score"]
            move = data["pv"][0]
            wdl = score_to_wdl(score)
            dtz = score_to_dtz(score)
            logger.info(f"Got move {move} from chessdb.cn (wdl: {wdl}, dtz: {dtz}) for game {game.id}")
        else:  # quality == "suggest"
            best_wdl = score_to_wdl(data["moves"][0]["score"])

            def good_enough(move: ChessDBMoveType) -> bool:
                return score_to_wdl(move["score"]) == best_wdl

            possible_moves = list(filter(good_enough, cast(list[ChessDBMoveType], data["moves"])))
            if len(possible_moves) > 1:
                wdl = score_to_wdl(possible_moves[0]["score"])
                move_list = [move["uci"] for move in possible_moves]
                logger.info(f"Suggesting moves from from chessdb.cn (wdl: {wdl}) for game {game.id}")
                return move_list, wdl, {"string": "lichess-bot-source:ChessDB EGTB"}
            else:
                best_move = possible_moves[0]
                score = best_move["score"]
                move = best_move["uci"]
                wdl = score_to_wdl(score)
                dtz = score_to_dtz(score)
                logger.info(f"Got move {move} from chessdb.cn (wdl: {wdl}, dtz: {dtz}) for game {game.id}")

        return move, wdl, {"string": "lichess-bot-source:ChessDB EGTB"}
    return None, -3, {}


def get_syzygy(board: chess.Board, game: model.Game,
               syzygy_cfg: Configuration) -> tuple[Union[chess.Move, list[chess.Move], None], int]:
    """
    Get a move from local syzygy egtbs.

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    if (not syzygy_cfg.enabled
            or chess.popcount(board.occupied) > syzygy_cfg.max_pieces
            or board.uci_variant not in ["chess", "antichess", "atomic"]):
        return None, -3

    move: Union[chess.Move, list[chess.Move]]
    move_quality = syzygy_cfg.move_quality

    with chess.syzygy.open_tablebase(syzygy_cfg.paths[0]) as tablebase:
        for path in syzygy_cfg.paths[1:]:
            tablebase.add_directory(path)

        try:
            moves = score_syzygy_moves(board, dtz_scorer, tablebase)

            best_wdl = max(map(dtz_to_wdl, moves.values()))
            good_moves = [(move, dtz) for move, dtz in moves.items() if dtz_to_wdl(dtz) == best_wdl]
            if move_quality == "suggest" and len(good_moves) > 1:
                move = [chess_move for chess_move, dtz in good_moves]
                logger.info(f"Suggesting moves from syzygy (wdl: {best_wdl}) for game {game.id}")
                return move, best_wdl
            # There can be multiple moves with the same dtz.
            best_dtz = min(good_moves, key=itemgetter(1))[1]
            best_moves = [chess_move for chess_move, dtz in good_moves if dtz == best_dtz]
            move = random.choice(best_moves)
            logger.info(f"Got move {move.uci()} from syzygy (wdl: {best_wdl}, dtz: {best_dtz}) for game {game.id}")
            return move, best_wdl
        except KeyError:
            # Attempt to only get the WDL score. It returns moves of quality="suggest", even if quality is set to "best".
            try:
                moves = score_syzygy_moves(board, lambda tablebase, b: -tablebase.probe_wdl(b), tablebase)
                best_wdl = int(max(moves.values()))  # int is there only for mypy.
                good_chess_moves = [chess_move for chess_move, wdl in moves.items() if wdl == best_wdl]
                logger.debug("Found moves using 'move_quality'='suggest'. We didn't find an '.rtbz' file for this endgame."
                             if move_quality == "best" else "")
                if len(good_chess_moves) > 1:
                    move = good_chess_moves
                    logger.info(f"Suggesting moves from syzygy (wdl: {best_wdl}) for game {game.id}")
                else:
                    move = good_chess_moves[0]
                    logger.info(f"Got move {move.uci()} from syzygy (wdl: {best_wdl}) for game {game.id}")
                return move, best_wdl
            except KeyError:
                return None, -3


def dtz_scorer(tablebase: chess.syzygy.Tablebase, board: chess.Board) -> Union[int, float]:
    """
    Score a position based on a syzygy DTZ egtb.

    For a zeroing move (capture or pawn move), a DTZ of +/-0.5 is returned.
    """
    dtz: Union[int, float] = -tablebase.probe_dtz(board)
    dtz = dtz if board.halfmove_clock else math.copysign(.5, dtz)
    return dtz + (math.copysign(board.halfmove_clock, dtz) if dtz else 0)


def dtz_to_wdl(dtz: float) -> int:
    """
    Convert DTZ scores to syzygy WDL scores.

    A DTZ of +/-100 returns a draw score of +/-1 instead of a win/loss score of +/-2 because
    a 50-move draw can be forced before checkmate can be forced.
    """
    return piecewise_function([(-100, "i", -1), (0, "e", -2), (0, "i", 0), (100, "e", 2)], 1, dtz)


def get_gaviota(board: chess.Board, game: model.Game,
                gaviota_cfg: Configuration) -> tuple[Union[chess.Move, list[chess.Move], None], int]:
    """
    Get a move from local gaviota egtbs.

    If `move_quality` is `suggest`, then it will return a list of moves for the engine to choose from.
    """
    if (not gaviota_cfg.enabled
            or chess.popcount(board.occupied) > gaviota_cfg.max_pieces
            or board.uci_variant != "chess"):
        return None, -3

    move: Union[chess.Move, list[chess.Move]]
    move_quality = gaviota_cfg.move_quality

    # Since gaviota TBs use dtm and not dtz, we have to put a limit where after it the position are considered to have
    # a syzygy wdl=1/-1, so the positions are draws under the 50 move rule. We use min_dtm_to_consider_as_wdl_1 as a
    # second limit, because if a position has 5 pieces and dtm=110 it may take 98 half-moves, to go down to 4 pieces and
    # another 12 to mate, so this position has a syzygy wdl=2/-2. To be safe, the first limit is 100 moves, which
    # guarantees that all moves have a syzygy wdl=2/-2. Setting min_dtm_to_consider_as_wdl_1 to 100 will disable it
    # because dtm >= dtz, so if abs(dtm) < 100 => abs(dtz) < 100, so wdl=2/-2.
    min_dtm_to_consider_as_wdl_1 = gaviota_cfg.min_dtm_to_consider_as_wdl_1

    with chess.gaviota.open_tablebase(gaviota_cfg.paths[0]) as tablebase:
        for path in gaviota_cfg.paths[1:]:
            tablebase.add_directory(path)

        try:
            moves = score_gaviota_moves(board, dtm_scorer, tablebase)

            best_wdl = max(map(dtm_to_gaviota_wdl, moves.values()))
            good_moves = [(move, dtm) for move, dtm in moves.items() if dtm_to_gaviota_wdl(dtm) == best_wdl]
            best_dtm = min(good_moves, key=itemgetter(1))[1]

            pseudo_wdl = dtm_to_wdl(best_dtm, min_dtm_to_consider_as_wdl_1)
            if move_quality == "suggest":
                best_moves = good_enough_gaviota_moves(good_moves, best_dtm, min_dtm_to_consider_as_wdl_1)
                if len(best_moves) > 1:
                    move = [chess_move for chess_move, dtm in best_moves]
                    logger.info(f"Suggesting moves from gaviota (pseudo wdl: {pseudo_wdl}) for game {game.id}")
                else:
                    move, dtm = best_moves[0]
                    logger.info(f"Got move {move.uci()} from gaviota (pseudo wdl: {pseudo_wdl}, dtm: {dtm})"
                                f" for game {game.id}")
            else:
                # There can be multiple moves with the same dtm.
                best_moves = [(move, dtm) for move, dtm in good_moves if dtm == best_dtm]
                move, dtm = random.choice(best_moves)
                logger.info(f"Got move {move.uci()} from gaviota (pseudo wdl: {pseudo_wdl}, dtm: {dtm}) for game {game.id}")
            return move, pseudo_wdl
        except KeyError:
            return None, -3


def dtm_scorer(tablebase: Union[chess.gaviota.NativeTablebase, chess.gaviota.PythonTablebase], board: chess.Board) -> int:
    """Score a position based on a gaviota DTM egtb."""
    dtm = -tablebase.probe_dtm(board)
    return dtm + int(math.copysign(board.halfmove_clock, dtm) if dtm else 0)


def dtm_to_gaviota_wdl(dtm: int) -> int:
    """Convert DTM scores to gaviota WDL scores."""
    return piecewise_function([(-1, "i", -1), (0, "i", 0)], 1, dtm)


def dtm_to_wdl(dtm: int, min_dtm_to_consider_as_wdl_1: int) -> int:
    """Convert DTM scores to syzygy WDL scores."""
    # We use 100 and not min_dtm_to_consider_as_wdl_1, because we want to play it safe and not resign in a
    # position where dtz=-102 (only if resign_for_egtb_minus_two is enabled).
    return piecewise_function([(-100, "i", -1), (-1, "i", -2), (0, "i", 0), (min_dtm_to_consider_as_wdl_1, "e", 2)], 1, dtm)


def good_enough_gaviota_moves(good_moves: list[tuple[chess.Move, int]], best_dtm: int,
                              min_dtm_to_consider_as_wdl_1: int) -> list[tuple[chess.Move, int]]:
    """
    Get the moves that are good enough to consider.

    :param good_moves: All the moves to choose from.
    :param best_dtm: The best DTM score of a move.
    :param min_dtm_to_consider_as_wdl_1: The minimum DTM score to consider as WDL=1.
    :return: A list of the moves that are good enough to consider.
    """
    if best_dtm < 100:
        # If a move had wdl=2 and dtz=98, but halfmove_clock is 4 then the real wdl=1 and dtz=102, so we
        # want to avoid these positions, if there is a move where even when we add the halfmove_clock the
        # dtz is still <100.
        return [(move, dtm) for move, dtm in good_moves if dtm < 100]
    if best_dtm < min_dtm_to_consider_as_wdl_1:
        # If a move had wdl=2 and dtz=98, but halfmove_clock is 4 then the real wdl=1 and dtz=102, so we
        # want to avoid these positions, if there is a move where even when we add the halfmove_clock the
        # dtz is still <100.
        return [(move, dtm) for move, dtm in good_moves if dtm < min_dtm_to_consider_as_wdl_1]
    if best_dtm <= -min_dtm_to_consider_as_wdl_1:
        # If a move had wdl=-2 and dtz=-98, but halfmove_clock is 4 then the real wdl=-1 and dtz=-102, so we
        # want to only choose between the moves where the real wdl=-1.
        return [(move, dtm) for move, dtm in good_moves if dtm <= -min_dtm_to_consider_as_wdl_1]
    if best_dtm <= -100:
        # If a move had wdl=-2 and dtz=-98, but halfmove_clock is 4 then the real wdl=-1 and dtz=-102, so we
        # want to only choose between the moves where the real wdl=-1.
        return [(move, dtm) for move, dtm in good_moves if dtm <= -100]
    return good_moves


def piecewise_function(range_definitions: list[tuple[float, Literal["e", "i"], int]], last_value: int,
                       position: float) -> int:
    """
    Return a value according to a position argument.

    This function is meant to replace if-elif-else blocks that turn ranges into discrete values.
    Each tuple in the list has three parts: an upper limit, and inclusive/exclusive indicator, and
    a value. For example,
    `piecewise_function([(-20000, "e", 2), (0, "e" -1), (0, "i", 0), (20000, "i", 1)], 2, score)` is equivalent to:

    if score < -20000:
        return -2
    elif score < 0:
        return -1
    elif score <= 0:
        return 0
    elif score <= 20000:
        return 1
    else:
        return 2

    Arguments:
    range_definitions:
        A list of tuples with the first element being the inclusive right border of region and the second
        element being the associated value. An element of this list (a, "i", b) corresponds to an
        inclusive limit and is equivalent to
            if x <= a:
                return b
        where x is the value of the position argument. An element of the form (a, "e", b) corresponds to
        an exclusive limit and is equivalent to
            if x < a:
                return b
        For correct operation, this argument should be sorted by the first element. If two ranges have the
        same border, one with "e" and the other with "i", the "e" element should be first.
    last_value:
        If the position argument does not fall in any of the ranges in the range_definition argument,
        return this value.
    position:
        The value that will be compared to the first element of the range_definitions tuples.

    """
    for border, inc_exc, value in range_definitions:
        if position < border or (inc_exc == "i" and position == border):
            return value
    return last_value


def score_syzygy_moves(board: chess.Board,
                       scorer: Union[Callable[[chess.syzygy.Tablebase, chess.Board], int],
                                     Callable[[chess.syzygy.Tablebase, chess.Board], Union[int, float]]],
                       tablebase: chess.syzygy.Tablebase) -> dict[chess.Move, Union[int, float]]:
    """Score all the moves using syzygy egtbs."""
    moves = {}
    for move in board.legal_moves:
        board.push(move)
        moves[move] = scorer(tablebase, board)
        board.pop()
    return moves


def score_gaviota_moves(board: chess.Board,
                        scorer: Callable[[Union[chess.gaviota.NativeTablebase, chess.gaviota.PythonTablebase],
                                          chess.Board], int],
                        tablebase: Union[chess.gaviota.NativeTablebase, chess.gaviota.PythonTablebase]
                        ) -> dict[chess.Move, int]:
    """Score all the moves using gaviota egtbs."""
    moves = {}
    for move in board.legal_moves:
        board.push(move)
        moves[move] = scorer(tablebase, board)
        board.pop()
    return moves
