import os
import chess.engine
import backoff
import subprocess
import logging

logger = logging.getLogger(__name__)


@backoff.on_exception(backoff.expo, BaseException, max_time=120)
def create_engine(config):
    cfg = config["engine"]
    engine_path = os.path.join(cfg["dir"], cfg["name"])
    engine_type = cfg.get("protocol")
    engine_options = cfg.get("engine_options")
    commands = [engine_path]
    if engine_options:
        for k, v in engine_options.items():
            commands.append("--{}={}".format(k, v))

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
    options = remove_managed_options(cfg.get(engine_type + "_options", {}) or {})
    return Engine(commands, options, stderr)


def remove_managed_options(config):
    def is_managed(key):
        return chess.engine.Option(key, None, None, None, None, None).is_managed()

    return {name: value for (name, value) in config.items() if not is_managed(name)}


class Termination:
    MATE = 'mate'
    TIMEOUT = 'outoftime'
    RESIGN = 'resign'
    ABORT = 'aborted'
    DRAW = 'draw'


class GameEnding:
    WHITE_WINS = '1-0'
    BLACK_WINS = '0-1'
    DRAW = '1/2-1/2'
    INCOMPLETE = '*'


class EngineWrapper:
    def __init__(self, commands, options, stderr):
        pass

    def search_for(self, board, movetime, ponder):
        return self.search(board, chess.engine.Limit(time=movetime // 1000), ponder)

    def first_search(self, board, movetime):
        # No pondering after the first move since a different clock is used afterwards.
        return self.search(board, chess.engine.Limit(time=movetime // 1000), False)

    def search_with_ponder(self, board, wtime, btime, winc, binc, ponder):
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
        return self.search(board, time_limit, ponder)

    def search(self, board, time_limit, ponder):
        result = self.engine.play(board, time_limit, info=chess.engine.INFO_ALL, ponder=ponder)
        self.last_move_info = result.info
        self.print_stats()
        return result.move

    def print_stats(self):
        for line in self.get_stats():
            logger.info(f"{line}")

    def get_stats(self):
        info = self.last_move_info
        stats = ["depth", "nps", "nodes", "score"]
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
    def __init__(self, commands, options, stderr):
        self.go_commands = options.pop("go_commands", {}) or {}
        self.engine = chess.engine.SimpleEngine.popen_uci(commands, stderr=stderr)
        self.engine.configure(options)
        self.last_move_info = {}

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
    def __init__(self, commands, options, stderr):
        self.go_commands = options.pop("go_commands", {}) or {}
        self.engine = chess.engine.SimpleEngine.popen_xboard(commands, stderr=stderr)
        egt_paths = options.pop("egtpath", {}) or {}
        features = self.engine.protocol.features
        egt_types_from_engine = features["egt"].split(",") if "egt" in features else []
        for egt_type in egt_types_from_engine:
            options[f"egtpath {egt_type}"] = egt_paths[egt_type]
        self.engine.configure(options)
        self.last_move_info = {}
        
    def report_game_result(self, game, board):
        # Send final moves, if any, to engine
        self.engine.protocol._new(board, None, {})

        winner = game.state.get('winner')
        termination = game.state.get('status')

        if winner == 'white':
            game_result = GameEnding.WHITE_WINS
        elif winner == 'black':
            game_result = GameEnding.BLACK_WINS
        elif termination == Termination.DRAW:
            game_result = GameEnding.DRAW
        else:
            game_result = GameEnding.INCOMPLETE

        if termination == Termination.MATE:
            endgame_message = winner.title() + ' mates'
        elif termination == Termination.TIMEOUT:
            endgame_message = 'Time forfeiture'
        elif termination == Termination.RESIGN:
            resigner = 'black' if winner == 'white' else 'white'
            endgame_message = resigner.title() + ' resigns'
        elif termination == Termination.ABORT:
            endgame_message = 'Game aborted'
        elif termination == Termination.DRAW:
            if board.is_fifty_moves():
                endgame_message = '50-move rule'
            elif board.is_repetition():
                endgame_message = 'Threefold repetition'
            else:
                endgame_message = 'Draw by agreement'
        elif termination:
            endgame_message = termination
        else:
            endgame_message = ''

        if endgame_message:
            endgame_message = ' {' + endgame_message + '}'

        self.engine.protocol.send_line('result ' + game_result + endgame_message)

    def stop(self):
        self.engine.protocol.send_line("?")

    def get_opponent_info(self, game):
        if game.opponent.name and self.engine.protocol.features.get("name", True):
            title = game.opponent.title + " " if game.opponent.title else ""
            self.engine.protocol.send_line(f"name {title}{game.opponent.name}")
        if game.me.rating is not None and game.opponent.rating is not None:
            self.engine.protocol.send_line(f"rating {game.me.rating} {game.opponent.rating}")
        if game.opponent.title == "BOT":
            self.engine.protocol.send_line("computer")


def getHomemadeEngine(name):
    import strategies
    return eval(f"strategies.{name}")
