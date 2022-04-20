import os
import chess.engine
import backoff
import subprocess
import logging
from enum import Enum

logger = logging.getLogger(__name__)


@backoff.on_exception(backoff.expo, BaseException, max_time=120)
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


PONDERPV_CHARACTERS = 12  # the length of ", ponderpv: "
MAX_CHAT_MESSAGE_LEN = 140  # maximum characters in a chat message


class EngineWrapper:
    def __init__(self, options, draw_or_resign):
        self.scores = []
        self.draw_or_resign = draw_or_resign
        self.go_commands = options.pop("go_commands", {}) or {}
        self.last_move_info = {}
        self.move_commentary = []
        self.comment_start_index = None

    def search_for(self, board, movetime, ponder, draw_offered):
        return self.search(board, chess.engine.Limit(time=movetime // 1000), ponder, draw_offered)

    def first_search(self, board, movetime, draw_offered):
        # No pondering after the first move since a different clock is used afterwards.
        return self.search(board, chess.engine.Limit(time=movetime // 1000), False, draw_offered)

    def search_with_ponder(self, board, wtime, btime, winc, binc, ponder, draw_offered):
        cmds = self.go_commands
        movetime = cmds.get("movetime")
        if movetime is not None:
            movetime = float(movetime) / 1000
        time_limit = chess.engine.Limit(white_clock=wtime / 1000,
                                        black_clock=btime / 1000,
                                        white_inc=winc / 1000,
                                        black_inc=binc / 1000,
                                        depth=cmds.get("depth"),
                                        nodes=cmds.get("nodes"),
                                        time=movetime)
        return self.search(board, time_limit, ponder, draw_offered)

    def offer_draw_or_resign(self, result, board):
        if self.draw_or_resign.get("offer_draw_enabled", False) and len(self.scores) >= self.draw_or_resign.get("offer_draw_moves", 5):
            scores = self.scores[-self.draw_or_resign.get("offer_draw_moves", 5):]
            pieces_on_board = chess.popcount(board.occupied)
            scores_near_draw = lambda score: abs(score.relative.score(mate_score=40000)) <= self.draw_or_resign.get("offer_draw_score", 0)
            if len(scores) == len(list(filter(scores_near_draw, scores))) and pieces_on_board <= self.draw_or_resign.get("offer_draw_pieces", 10):
                result.draw_offered = True

        if self.draw_or_resign.get("resign_enabled", False) and len(self.scores) >= self.draw_or_resign.get("resign_moves", 3):
            scores = self.scores[-self.draw_or_resign.get("resign_moves", 3):]
            scores_near_loss = lambda score: score.relative.score(mate_score=40000) <= self.draw_or_resign.get("resign_score", -1000)
            if len(scores) == len(list(filter(scores_near_loss, scores))):
                result.resigned = True
        return result

    def search(self, board, time_limit, ponder, draw_offered):
        result = self.engine.play(board, time_limit, info=chess.engine.INFO_ALL, ponder=ponder, draw_offered=draw_offered)
        self.last_move_info = result.info.copy()
        self.move_commentary.append(self.last_move_info.copy())
        if self.comment_start_index is None:
            self.comment_start_index = len(board.move_stack)
        self.scores.append(self.last_move_info.get("score", chess.engine.PovScore(chess.engine.Mate(1), board.turn)))
        result = self.offer_draw_or_resign(result, board)
        self.last_move_info["ponderpv"] = board.variation_san(self.last_move_info.get("pv", []))
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
            logger.info(f"{line}")

    def get_stats(self, for_chat=False):
        info = self.last_move_info.copy()
        stats = ["depth", "nps", "nodes", "score", "ponderpv"]
        if for_chat:
            bot_stats = [f"{stat}: {info[stat]}" for stat in stats if stat in info and stat != "ponderpv"]
            len_bot_stats = len(", ".join(bot_stats)) + PONDERPV_CHARACTERS
            ponder_pv = info["ponderpv"]
            ponder_pv = ponder_pv.split()
            try:
                while len(" ".join(ponder_pv)) + len_bot_stats > MAX_CHAT_MESSAGE_LEN:
                    ponder_pv.pop()
                if ponder_pv[-1].endswith("."):
                    ponder_pv.pop()
                info["ponderpv"] = " ".join(ponder_pv)
            except IndexError:
                pass
        return [f"{stat}: {info[stat]}" for stat in stats if stat in info]

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
            rating = game.opponent.rating if game.opponent.rating is not None else "none"
            title = game.opponent.title if game.opponent.title else "none"
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
        egt_types_from_engine = features["egt"].split(",") if "egt" in features else []
        for egt_type in egt_types_from_engine:
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
        if game.me.rating is not None and game.opponent.rating is not None:
            self.engine.protocol.send_line(f"rating {game.me.rating} {game.opponent.rating}")
        if game.opponent.title == "BOT":
            self.engine.protocol.send_line("computer")


def getHomemadeEngine(name):
    import strategies
    return eval(f"strategies.{name}")
