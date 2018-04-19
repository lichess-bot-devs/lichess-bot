import chess
import chess.xboard
import chess.uci

class EngineWrapper:

    def __init__(self, board, commands):
        pass

    def pre_game(self, game):
        pass

    def first_search(self, movetime):
        pass

    def search(self, board, wtime, btime, winc, binc):
        pass

    def print_stats(self):
        pass

    def name(self):
        return self.engine.name

    def quit(self):
        self.engine.quit()

    def print_stats(self):
        stats = ["depth", "nodes", "score"]
        for stat in stats:
            post_handler = self.engine.post_handlers[0]
            if stat in post_handler.post:
                print("    {}: {}".format(stat, post_handler.post[stat]))

class XBoardEngine(EngineWrapper):

    def __init__(self, board, commands):
        commands = commands[0] if len(commands) == 1 else commands
        self.engine = chess.xboard.popen_engine(commands)

        self.engine.xboard()
        self.engine.setboard(board)

        post_handler = chess.xboard.PostHandler()
        self.engine.post_handlers.append(post_handler)

    def pre_game(self, game):
        minutes = game.clock_initial / 1000 / 60
        seconds = game.clock_initial / 1000 % 60
        inc = game.clock_increment / 1000
        self.engine.level(0, minutes, seconds, inc)

    def first_search(self, board, movetime):
        self.engine.setboard(board)
        self.engine.st(movetime / 1000)
        return self.engine.go()

    def search(self, board, wtime, btime, winc, binc):
        self.engine.setboard(board)
        if board.turn == chess.WHITE:
            self.engine.time(wtime / 10)
            self.engine.otim(btime / 10)
        else:
            self.engine.time(btime / 10)
            self.engine.otim(wtime / 10)
        return self.engine.go()

class UCIEngine(EngineWrapper):

    def __init__(self, board, commands):
        commands = commands[0] if len(commands) == 1 else commands
        self.engine = chess.uci.popen_engine(commands)

        self.engine.uci()
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
