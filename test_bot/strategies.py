from lib.strategies import ExampleEngine
import chess
import chess.engine
from lib.config import Configuration
from typing import Any, Optional, Union
OPTIONS_TYPE = dict[str, Any]
COMMANDS_TYPE = list[str]
MOVE = Union[chess.engine.PlayResult, list[chess.Move]]


class Stockfish(ExampleEngine):
    def __init__(self, commands: COMMANDS_TYPE, options: OPTIONS_TYPE, stderr: Optional[int],
                 draw_or_resign: Configuration, **popen_args: str):
        super().__init__(commands, options, stderr, draw_or_resign, **popen_args)
        self.engine = chess.engine.SimpleEngine.popen_uci('./TEMP/sf.exe')

    def search(self, board: chess.Board, time_limit: chess.engine.Limit, ponder: bool, draw_offered: bool,
               root_moves: MOVE) -> chess.engine.PlayResult:
        return self.engine.play(board, time_limit)
