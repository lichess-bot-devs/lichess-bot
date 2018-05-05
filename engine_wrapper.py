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
    lczero_options = cfg.get("lczero")
    commands = [engine_path]
    if lczero_options:
        if "weights" in lczero_options:
            commands.append("-w")
            commands.append(lczero_options["weights"])
        if "threads" in lczero_options:
            commands.append("-t")
            commands.append(str(lczero_options["threads"]))
        if "gpu" in lczero_options:
            commands.append("--gpu")
            commands.append(str(lczero_options["gpu"]))
        if "tempdecay" in lczero_options:
            commands.append("--tempdecay")
            commands.append(str(lczero_options["tempdecay"]))
        if lczero_options.get("noise"):
            commands.append("--noise")

    silence_stderr = cfg.get("silence_stderr", False)

    if engine_type == "xboard":
        return XBoardEngine(board, commands, cfg.get("xboard_options"), silence_stderr)

    return UCIEngine(board, commands, cfg.get("uci_options"), silence_stderr)


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

    def search(self, board, wtime, btime, winc, binc):
        self.engine.position(board)
        best_move, _ = self.engine.go(
            wtime=wtime,
            btime=btime,
            winc=winc,
            binc=binc
        )
        return best_move

    def search_with_ponder(self, board, wtime, btime, winc, binc):
        self.engine.position(board)
        best_move, ponder_move = self.engine.go(
            wtime=wtime,
            btime=btime,
            winc=winc,
            binc=binc
        )
        return ( best_move , ponder_move )

    def print_stats(self):
        self.print_handler_stats(self.engine.info_handlers[0].info, ["string", "depth", "nps", "nodes", "score"])

    def get_stats(self):
        return self.get_handler_stats(self.engine.info_handlers[0].info, ["depth", "nps", "nodes", "score"])

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

        self.engine.setboard(board)

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
                    except EngineStateException:
                        # If the user specifies more TBs than the engine supports, ignore the error.
                        pass
            else:
                try:
                    self.engine.features.set_option(option, value)
                except EngineStateException:
                    pass

    def set_time_control(self, game):
        minutes = game.clock_initial / 1000 / 60
        seconds = game.clock_initial / 1000 % 60
        inc = game.clock_increment / 1000
        self.engine.level(0, minutes, seconds, inc)

    def first_search(self, board, movetime):
        self.engine.setboard(board)
        self.engine.level(0, 0, movetime / 1000, 0)
        bestmove = self.engine.go()

        return bestmove

    def search(self, board, wtime, btime, winc, binc):
        self.engine.setboard(board)
        if board.turn == chess.WHITE:
            self.engine.time(wtime / 10)
            self.engine.otim(btime / 10)
        else:
            self.engine.time(btime / 10)
            self.engine.otim(wtime / 10)
        return self.engine.go()

    def print_stats(self):
        self.print_handler_stats(self.engine.post_handlers[0].post, ["depth", "nodes", "score"])

    def get_stats(self):
        return self.get_handler_stats(self.engine.post_handlers[0].post, ["depth", "nodes", "score"])


    def name(self):
        try:
            return self.engine.features.get("myname")
        except:
            return None
