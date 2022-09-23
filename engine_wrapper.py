import os
import chess.engine
import subprocess
import logging
from enum import Enum

logger = logging.getLogger(__name__)


def create_engine(config):
    cfg = config["engine"]
    engine_path = os.path.join(cfg["dir"], cfg["name"])
    engine_working_dir = cfg.get("working_dir") or os.getcwd()
    engine_type = cfg.get("protocol")
    engine_options = cfg.get("engine_options")
    draw_or_resign = cfg.get("draw_or_resign") or {}
    commands = [engine_path]
    if engine_options:
        for k, v in engine_options.items():
            commands.append(f"--{k}={v}")

    stderr = None if cfg.get("silence_stderr", False) else subprocess.DEVNULL

    if engine_type == "xboard":
        Engine = XBoardEngine
    elif engine_type == "uci":
        Engine = UCIEngine
    elif engine_type == "homemade":
        Engine = getHomemadeEngine(cfg["name"])
    else:
        raise ValueError(
            f"    Invalid engine type: {engine_type}. Expected xboard, uci, or homemade.")
    options = remove_managed_options(cfg.get(f"{engine_type}_options") or {})
    logger.debug(f"Starting engine: {' '.join(commands)}")
    return Engine(commands, options, stderr, draw_or_resign, cwd=engine_working_dir)


def remove_managed_options(config):
    def is_managed(key):
        return chess.engine.Option(key, None, None, None, None, None).is_managed()

    return {name: value for (name, value) in config.items() if not is_managed(name)}


class Termination(str, Enum):
    MATE = "mate"
    TIMEOUT = "outoftime"
    RESIGN = "resign"
    ABORT = "aborted"
    DRAW = "draw"


class GameEnding(str, Enum):
    WHITE_WINS = "1-0"
    BLACK_WINS = "0-1"
    DRAW = "1/2-1/2"
    INCOMPLETE = "*"


def translate_termination(termination, board, winner_color):
    if termination == Termination.MATE:
        return f"{winner_color.title()} mates"
    elif termination == Termination.TIMEOUT:
        return "Time forfeiture"
    elif termination == Termination.RESIGN:
        resigner = "black" if winner_color == "white" else "white"
        return f"{resigner.title()} resigns"
    elif termination == Termination.ABORT:
        return "Game aborted"
    elif termination == Termination.DRAW:
        if board.is_fifty_moves():
            return "50-move rule"
        elif board.is_repetition():
            return "Threefold repetition"
        else:
            return "Draw by agreement"
    elif termination:
        return termination
    else:
        return ""


PONDERPV_CHARACTERS = 6  # The length of ", PV: ".
MAX_CHAT_MESSAGE_LEN = 140  # The maximum characters in a chat message.


class EngineWrapper:
    def __init__(self, options, draw_or_resign):
        self.scores = []
        self.draw_or_resign = draw_or_resign
        self.go_commands = options.pop("go_commands", {}) or {}
        self.last_move_info = {}
        self.move_commentary = []
        self.comment_start_index = None

    def search_for(self, board, movetime, ponder, draw_offered):
        return self.search(board, chess.engine.Limit(time=movetime / 1000), ponder, draw_offered)

    def first_search(self, board, movetime, draw_offered):
        # No pondering after the first move since a different clock is used afterwards.
        return self.search_for(board, movetime, False, draw_offered)

    def search_with_ponder(self, board, wtime, btime, winc, binc, ponder, draw_offered):
        time_limit = chess.engine.Limit(white_clock=wtime / 1000,
                                        black_clock=btime / 1000,
                                        white_inc=winc / 1000,
                                        black_inc=binc / 1000)
        return self.search(board, time_limit, ponder, draw_offered)

    def add_go_commands(self, time_limit):
        movetime = self.go_commands.get("movetime")
        if movetime is not None:
            movetime_sec = float(movetime) / 1000
            if time_limit.time is None or time_limit.time > movetime_sec:
                time_limit.time = movetime_sec
        time_limit.depth = self.go_commands.get("depth")
        time_limit.nodes = self.go_commands.get("nodes")
        return time_limit

    def offer_draw_or_resign(self, result, board):
        def actual(score):
            return score.relative.score(mate_score=40000)

        can_offer_draw = self.draw_or_resign.get("offer_draw_enabled", False)
        draw_offer_moves = self.draw_or_resign.get("offer_draw_moves", 5)
        draw_score_range = self.draw_or_resign.get("offer_draw_score", 0)
        draw_max_piece_count = self.draw_or_resign.get("offer_draw_pieces", 10)
        pieces_on_board = chess.popcount(board.occupied)
        enough_pieces_captured = pieces_on_board <= draw_max_piece_count
        if can_offer_draw and len(self.scores) >= draw_offer_moves and enough_pieces_captured:
            scores = self.scores[-draw_offer_moves:]

            def score_near_draw(score):
                return abs(actual(score)) <= draw_score_range
            if len(scores) == len(list(filter(score_near_draw, scores))):
                result.draw_offered = True

        resign_enabled = self.draw_or_resign.get("resign_enabled", False)
        min_moves_for_resign = self.draw_or_resign.get("resign_moves", 3)
        resign_score = self.draw_or_resign.get("resign_score", -1000)
        if resign_enabled and len(self.scores) >= min_moves_for_resign:
            scores = self.scores[-min_moves_for_resign:]

            def score_near_loss(score):
                return actual(score) <= resign_score
            if len(scores) == len(list(filter(score_near_loss, scores))):
                result.resigned = True
        return result

    def search(self, board, time_limit, ponder, draw_offered):
        time_limit = self.add_go_commands(time_limit)
        result = self.engine.play(board,
                                  time_limit,
                                  info=chess.engine.INFO_ALL,
                                  ponder=ponder,
                                  draw_offered=draw_offered)
        self.last_move_info = result.info.copy()
        self.move_commentary.append(self.last_move_info.copy())
        if self.comment_start_index is None:
            self.comment_start_index = len(board.move_stack)
        # Use null_score to have no effect on draw/resign decisions
        null_score = chess.engine.PovScore(chess.engine.Mate(1), board.turn)
        self.scores.append(self.last_move_info.get("score", null_score))
        result = self.offer_draw_or_resign(result, board)
        if "pv" in self.last_move_info:
            self.last_move_info["ponderpv"] = board.variation_san(self.last_move_info["pv"])
        if "refutation" in self.last_move_info:
            self.last_move_info["refutation"] = board.variation_san(self.last_move_info["refutation"])
        if "currmove" in self.last_move_info:
            self.last_move_info["currmove"] = board.san(self.last_move_info["currmove"])
        self.print_stats()
        return result

    def comment_index(self, move_stack_index):
        if self.comment_start_index is None:
            return -1
        else:
            return move_stack_index - self.comment_start_index

    def comment_for_board_index(self, index):
        comment_index = self.comment_index(index)
        if comment_index < 0 or comment_index % 2 != 0:
            return None

        try:
            return self.move_commentary[comment_index // 2]
        except IndexError:
            return None

    def add_null_comment(self):
        if self.comment_start_index is not None:
            self.move_commentary.append(None)

    def print_stats(self):
        for line in self.get_stats():
            logger.info(line)

    def readable_score(self, score):
        score = score.relative
        if score.mate():
            str_score = f"#{score.mate()}"
        else:
            str_score = str(round(score.score() / 100, 2))
        return str_score

    def readable_wdl(self, wdl):
        wdl = round(wdl.relative.expectation() * 100, 1)
        return f"{wdl}%"

    def readable_number(self, number):
        if number >= 1e9:
            return f"{round(number / 1e9, 1)}B"
        elif number >= 1e6:
            return f"{round(number / 1e6, 1)}M"
        elif number >= 1e3:
            return f"{round(number / 1e3, 1)}K"
        return str(number)

    def get_stats(self, for_chat=False):
        info = self.last_move_info.copy()

        def to_readable_value(stat, info):
            readable = {"score": self.readable_score, "wdl": self.readable_wdl, "hashfull": lambda x: f"{round(x / 10, 1)}%",
                        "nodes": self.readable_number, "nps": lambda x: f"{self.readable_number(x)}nps",
                        "tbhits": self.readable_number, "cpuload": lambda x: f"{round(x / 10, 1)}%"}
            return str(readable.get(stat, lambda x: x)(info[stat]))

        def to_readable_key(stat):
            readable = {"wdl": "winrate", "ponderpv": "PV", "nps": "speed", "score": "evaluation"}
            stat = readable.get(stat, stat)
            return stat[0].upper() + stat[1:]

        stats = ["score", "wdl", "depth", "nodes", "nps", "ponderpv"]
        if for_chat and "ponderpv" in stats and "ponderpv" in info:
            bot_stats = [f"{to_readable_key(stat)}: {to_readable_value(stat, info)}"
                         for stat in stats if stat in info and stat != "ponderpv"]
            len_bot_stats = len(", ".join(bot_stats)) + PONDERPV_CHARACTERS
            ponder_pv = info["ponderpv"].split()
            try:
                while len(" ".join(ponder_pv)) + len_bot_stats > MAX_CHAT_MESSAGE_LEN:
                    ponder_pv.pop()
                if ponder_pv[-1].endswith("."):
                    ponder_pv.pop()
                info["ponderpv"] = " ".join(ponder_pv)
            except IndexError:
                pass
            if not info["ponderpv"]:
                info.pop("ponderpv")
        return [f"{to_readable_key(stat)}: {to_readable_value(stat, info)}" for stat in stats if stat in info]

    def get_opponent_info(self, game):
        pass

    def name(self):
        return self.engine.id["name"]

    def report_game_result(self, game, board):
        pass

    def stop(self):
        pass

    def quit(self):
        self.engine.quit()
        self.engine.close()


class UCIEngine(EngineWrapper):
    def __init__(self, commands, options, stderr, draw_or_resign, **popen_args):
        super().__init__(options, draw_or_resign)
        self.engine = chess.engine.SimpleEngine.popen_uci(commands, stderr=stderr, **popen_args)
        self.engine.configure(options)

    def stop(self):
        self.engine.protocol.send_line("stop")

    def get_opponent_info(self, game):
        name = game.opponent.name
        if name and "UCI_Opponent" in self.engine.protocol.config:
            rating = game.opponent.rating or "none"
            title = game.opponent.title or "none"
            player_type = "computer" if title == "BOT" else "human"
            self.engine.configure({"UCI_Opponent": f"{title} {rating} {player_type} {name}"})

    def report_game_result(self, game, board):
        self.engine.protocol._position(board)


class XBoardEngine(EngineWrapper):
    def __init__(self, commands, options, stderr, draw_or_resign, **popen_args):
        super().__init__(options, draw_or_resign)
        self.engine = chess.engine.SimpleEngine.popen_xboard(commands, stderr=stderr, **popen_args)
        egt_paths = options.pop("egtpath", {}) or {}
        features = self.engine.protocol.features
        egt_types_from_engine = features.get("egt", "").split(",")
        for egt_type in filter(None, egt_types_from_engine):
            if egt_type in egt_paths:
                options[f"egtpath {egt_type}"] = egt_paths[egt_type]
            else:
                logger.debug(f"No paths found for egt type: {egt_type}.")
        self.engine.configure(options)

    def report_game_result(self, game, board):
        # Send final moves, if any, to engine
        self.engine.protocol._new(board, None, {})

        winner = game.state.get("winner")
        termination = game.state.get("status")

        if winner == "white":
            game_result = GameEnding.WHITE_WINS
        elif winner == "black":
            game_result = GameEnding.BLACK_WINS
        elif termination == Termination.DRAW:
            game_result = GameEnding.DRAW
        else:
            game_result = GameEnding.INCOMPLETE

        endgame_message = translate_termination(termination, board, winner)
        if endgame_message:
            endgame_message = " {" + endgame_message + "}"

        self.engine.protocol.send_line(f"result {game_result}{endgame_message}")

    def stop(self):
        self.engine.protocol.send_line("?")

    def get_opponent_info(self, game):
        if game.opponent.name and self.engine.protocol.features.get("name", True):
            title = f"{game.opponent.title} " if game.opponent.title else ""
            self.engine.protocol.send_line(f"name {title}{game.opponent.name}")
        if game.me.rating and game.opponent.rating:
            self.engine.protocol.send_line(f"rating {game.me.rating} {game.opponent.rating}")
        if game.opponent.title == "BOT":
            self.engine.protocol.send_line("computer")


def getHomemadeEngine(name):
    import strategies
    return getattr(strategies, name)
