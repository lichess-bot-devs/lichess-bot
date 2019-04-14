import chess.polyglot
import logging

logger = logging.getLogger(__name__)


class Book:
    WEIGHTED_RANDOM = "weighted_random"
    UNIFORM_RANDOM = "uniform_random"
    BEST_MOVE = "best_move"

    def __init__(self, polyglot_cfg, variant):
        self.book_cfg = polyglot_cfg.get("book", {})
        self.book = self.book_cfg.get(self.variant, None)
        self.variant = "standard" if variant == "chess" else variant
        self.selection = self.book_cfg.get("selection", None)

        self.enabled = polyglot_cfg.get("enabled", False) and self.book

        self.max_depth = polyglot_cfg.get("max_depth", 8) * 2 - 1
        self.min_weight = self.book_cfg.get("min_weight", 1)

    def get_move(self, board):
        move = None
        with chess.polyglot.open_reader(self.book) as reader:
            try:
                if self.selection == Book.WEIGHTED_RANDOM:
                    move = reader.weighted_choice(board).move()

                elif self.selection == Book.UNIFORM_RANDOM:
                    move = reader.choice(board, self.min_weight).move()

                elif self.selection == Book.BEST_MOVE:
                    move = reader.find(board, self.min_weight).move()

                logger.info("Got move {} from book {}".format(move, self.book))
            except IndexError:
                logger.warning("Book {} did not find move", self.book)

        return move

    def is_enabled(self):
        return self.enabled
