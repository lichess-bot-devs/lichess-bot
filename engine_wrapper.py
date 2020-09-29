import os
import chess
import chess.xboard
import chess.uci
import backoff
import subprocess

@backoff.on_exception(backoff.expo, BaseException, max_time=120)
def create_engine(config, board):
    cfg = config["engine"]
    engine_path = os.path.join(cfg["dir"], cfg["name"])
    engine_type = cfg.get("protocol")
    engine_options = cfg.get("engine_options")
    commands = [engine_path]
    if engine_options:
        for k, v in engine_options.items():
            commands.append("--{}={}".format(k, v))

    silence_stderr = cfg.get("silence_stderr", False)

    if engine_type == "xboard":
        return XBoardEngine(board, commands, cfg.get("xboard_options", {}) or {}, silence_stderr)

    return UCIEngine(board, commands, cfg.get("uci_options", {}) or {}, silence_stderr)


class EngineWrapper:

    def __init__(self, board, commands, options=None, silence_stderr=False):
        pass

    def set_time_control(self, game):
        pass

    def first_search(self, board, movetime):
        pass

    def search(self, board, wtime, btime, winc, binc):
        pass

    def print_stats(self):
        pass

    def get_opponent_info(self, game):
        pass

    def name(self):
        return self.engine.name

    def quit(self):
        self.engine.quit()

    def print_handler_stats(self, info, stats):
        for stat in stats:
            if stat in info:
                print("    {}: {}".format(stat, info[stat]))

    def get_handler_stats(self, info, stats):
        stats_str = []
        for stat in stats:
            if stat in info:
                stats_str.append("{}: {}".format(stat, info[stat]))

        return stats_str


class UCIEngine(EngineWrapper):

    def __init__(self, board, commands, options, silence_stderr=False):
        commands = commands[0] if len(commands) == 1 else commands
        self.go_commands = options.get("go_commands", {})

        self.engine = chess.uci.popen_engine(commands, stderr = subprocess.DEVNULL if silence_stderr else None)
        self.engine.uci()

        if options:
            self.engine.setoption(options)

        self.engine.setoption({
            "UCI_Variant": type(board).uci_variant,
            "UCI_Chess960": board.chess960
        })
        self.engine.position(board)

        info_handler = chess.uci.InfoHandler()
        self.engine.info_handlers.append(info_handler)


    def first_search(self, board, movetime):
        self.engine.position(board)
        best_move, _ = self.engine.go(movetime=movetime)
        return best_move

    def search_with_ponder(self, board, wtime, btime, winc, binc, ponder=False):
        self.engine.position(board)
        best_move, ponder_move = self.engine.go(
            wtime=wtime,
            btime=btime,
            winc=winc,
            binc=binc,
            ponder=ponder
        )
        return ( best_move , ponder_move )

    def search(self, board, wtime, btime, winc, binc):
        self.engine.position(board)
        cmds = self.go_commands
        best_move, _ = self.engine.go(
            wtime=wtime,
            btime=btime,
            winc=winc,
            binc=binc,
            depth=cmds.get("depth"),
            nodes=cmds.get("nodes"),
            movetime=cmds.get("movetime")
        )
        return best_move


    def stop(self):
        self.engine.stop()


    def print_stats(self):
        self.print_handler_stats(self.engine.info_handlers[0].info, ["string", "depth", "nps", "nodes", "score"])


    def get_stats(self):
        return self.get_handler_stats(self.engine.info_handlers[0].info, ["depth", "nps", "nodes", "score"])

    def get_opponent_info(self, game):
        name = game.opponent.name
        if name:
            rating = game.opponent.rating if game.opponent.rating is not None else "none"
            title = game.opponent.title if game.opponent.title else "none"
            player_type = "computer" if title == "BOT" else "human"
            self.engine.setoption({"UCI_Opponent": "{} {} {} {}".format(title, rating, player_type, name)})

class XBoardEngine(EngineWrapper):

    def __init__(self, board, commands, options=None, silence_stderr=False):
        commands = commands[0] if len(commands) == 1 else commands
        self.engine = chess.xboard.popen_engine(commands, stderr = subprocess.DEVNULL if silence_stderr else None)

        self.engine.xboard()

        if board.chess960:
            self.engine.send_variant("fischerandom")
        elif type(board).uci_variant != "chess":
            self.engine.send_variant(type(board).uci_variant)

        if options:
            self._handle_options(options)

        if board.fen() != chess.STARTING_FEN:
            self.engine.force()
            if board.root().fen() != chess.STARTING_FEN:
                self.engine.setboard(board.root())
            for move in board.move_stack:
                self.engine.usermove(move)
        self.last_fen_seen = board.fen()

        post_handler = chess.xboard.PostHandler()
        self.engine.post_handlers.append(post_handler)

    def _handle_options(self, options):
        for option, value in options.items():
            if option == "memory":
                self.engine.memory(value)
            elif option == "cores":
                self.engine.cores(value)
            elif option == "egtpath":
                for egttype, egtpath in value.items():
                    try:
                        self.engine.egtpath(egttype, egtpath)
                    except chess.EngineStateException:
                        # If the user specifies more TBs than the engine supports, ignore the error.
                        pass
            else:
                try:
                    self.engine.features.set_option(option, value)
                except chess.EngineStateException:
                    pass

    def set_time_control(self, game):
        self.minutes = game.clock_initial / 1000 // 60
        self.seconds = game.clock_initial // 1000 % 60
        self.inc = game.clock_increment // 1000
        self.send_time()

    def send_time(self):
        self.engine.level(0, self.minutes, self.seconds, self.inc)

    def send_last_move(self, board):
        if board.fen() == self.last_fen_seen:
            return
        self.engine.force()
        try:
            self.engine.usermove(board.peek())
        except IndexError:
            self.engine.setboard(board)
        self.last_fen_seen = board.fen()

    def first_search(self, board, movetime):
        self.send_last_move(board)
        self.engine.st(movetime // 1000)
        bestmove = self.engine.go()
        self.send_time()

        return bestmove

    def search(self, board, wtime, btime, winc, binc):
        self.send_last_move(board)

        # XBoard engines expect time in units of 1/100 seconds.
        if board.turn == chess.WHITE:
            self.engine.time(wtime // 10)
            self.engine.otim(btime // 10)
        else:
            self.engine.time(btime // 10)
            self.engine.otim(wtime // 10)
        return self.engine.go()

    def search_with_ponder(self, board, wtime, btime, winc, binc, ponder=False):
        return self.search(board, wtime, btime, winc, binc), None

    def print_stats(self):
        self.print_handler_stats(self.engine.post_handlers[0].post, ["depth", "nodes", "score"])

    def get_stats(self):
        return self.get_handler_stats(self.engine.post_handlers[0].post, ["depth", "nodes", "score"])


    def name(self):
        try:
            return self.engine.features.get("myname")
        except:
            return None

    def get_opponent_info(self, game):
        title = game.opponent.title + " " if game.opponent.title else ""
        if game.opponent.name:
            self.engine.opponent_name(title + game.opponent.name)
        if game.me.rating is not None and game.opponent.rating is not None:
            self.engine.rating(game.me.rating, game.opponent.rating)
        if game.opponent.title == "BOT":
            self.engine.computer()
