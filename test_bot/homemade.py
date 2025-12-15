"""Homemade engine playing scholar's mate."""
from homemade import ExampleEngine
import chess
import chess.engine
from lib.config import Configuration
from lib import model
from lib.lichess_types import OPTIONS_GO_EGTB_TYPE, COMMANDS_TYPE, MOVE
from test_bot.test_games import scholars_mate

# ruff: noqa: ARG002

class ScholarsMate(ExampleEngine):
    """A homemade engine that plays the scholar's mate."""

    def __init__(self, commands: COMMANDS_TYPE, options: OPTIONS_GO_EGTB_TYPE, stderr: int | None,
                 draw_or_resign: Configuration, game: model.Game | None, **popen_args: str) -> None:
        """Set up engine."""
        super().__init__(commands, options, stderr, draw_or_resign, game, **popen_args)

    def search(self, board: chess.Board, time_limit: chess.engine.Limit, ponder: bool, draw_offered: bool,
               root_moves: MOVE) -> chess.engine.PlayResult:
        """Get the next scholar's mate move."""
        move_number = len(board.move_stack)
        move = board.parse_uci(scholars_mate[move_number])
        return chess.engine.PlayResult(move, None)
