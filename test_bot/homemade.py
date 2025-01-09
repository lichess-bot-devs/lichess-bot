"""Homemade engine using Stockfish (used in testing)."""
from homemade import ExampleEngine
import chess
import chess.engine
import sys
from lib.config import Configuration
from lib import model
from typing import Optional
from lib.lichess_types import OPTIONS_GO_EGTB_TYPE, COMMANDS_TYPE, MOVE

# ruff: noqa: ARG002

platform = sys.platform
file_extension = ".exe" if platform == "win32" else ""


class Stockfish(ExampleEngine):
    """A homemade engine that uses Stockfish."""

    def __init__(self, commands: COMMANDS_TYPE, options: OPTIONS_GO_EGTB_TYPE, stderr: Optional[int],
                 draw_or_resign: Configuration, game: Optional[model.Game], **popen_args: str) -> None:
        """Start Stockfish."""
        super().__init__(commands, options, stderr, draw_or_resign, game, **popen_args)
        self.engine = chess.engine.SimpleEngine.popen_uci(f"./TEMP/sf{file_extension}")

    def search(self, board: chess.Board, time_limit: chess.engine.Limit, ponder: bool, draw_offered: bool,
               root_moves: MOVE) -> chess.engine.PlayResult:
        """Get a move using Stockfish."""
        return self.engine.play(board, time_limit)
