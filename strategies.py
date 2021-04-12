"""
Some example strategies for people who want to create a custom, homemade bot.
And some handy classes to extend
"""

import chess
import random
from engine_wrapper import EngineWrapper


class MinimalEngine(EngineWrapper):
    """
    Subclass this to prevent some pitfalls
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.last_move_info = []
        self.engine = self

    def search_with_ponder(self, board, wtime, btime, winc, binc, ponder):
        timeleft = 0
        if board.turn:
            timeleft = wtime
        else:
            timeleft = btime
        return self.search(board, timeleft, ponder)

    # Prevents infinite recursion - self.engine.quit is called in EngineWrapper
    def quit(self):
        pass


class ExampleEngine(MinimalEngine):
    pass


# Names from tom7's excellent eloWorld video

class RandomMove(ExampleEngine):
    def search(self, board, *args):
        return random.choice(list(board.legal_moves))


class Alphabetical(ExampleEngine):
    def search(self, board, *args):
        moves = list(board.legal_moves)
        moves.sort(key=board.san)
        return moves[0]


# Uci representation is first_move, right?
class FirstMove(ExampleEngine):
    def search(self, board, *args):
        moves = list(board.legal_moves)
        moves.sort(key=str)
        return moves[0]
