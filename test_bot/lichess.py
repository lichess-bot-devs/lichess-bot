"""Imitate `lichess.py`. Used in tests."""
import time
import chess
import chess.engine
import json
import logging
import traceback
import datetime
from queue import Queue
from typing import Union, Any, Optional, Generator
from lib.timer import to_msec
JSON_REPLY_TYPE = dict[str, Any]
REQUESTS_PAYLOAD_TYPE = dict[str, Any]

logger = logging.getLogger(__name__)


def backoff_handler(details: Any) -> None:
    """Log exceptions inside functions with the backoff decorator."""
    logger.debug("Backing off {wait:0.1f} seconds after {tries} tries "
                 "calling function {target} with args {args} and kwargs {kwargs}".format(**details))
    logger.debug(f"Exception: {traceback.format_exc()}")


def is_final(error: Any) -> bool:
    """Mock error handler for tests when a function has a backup decorator."""
    logger.debug(error)
    return False


class GameStream:
    """Imitate lichess.org's GameStream. Used in tests."""

    def __init__(self,
                 board_queue: Queue[chess.Board],
                 clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]]) -> None:
        """Initialize `self.moves_sent` to an empty string. It stores the moves that we have already sent."""
        self.board_queue = board_queue
        self.clock_queue = clock_queue

    def iter_lines(self) -> Generator[bytes, None, None]:
        """Send the game events to lichess-bot."""
        yield json.dumps(
            {"id": "zzzzzzzz",
             "variant": {"key": "standard",
                         "name": "Standard",
                         "short": "Std"},
             "clock": {"initial": 60000,
                       "increment": 2000},
             "speed": "bullet",
             "perf": {"name": "Bullet"},
             "rated": True,
             "createdAt": 1600000000000,
             "white": {"id": "bo",
                       "name": "bo",
                       "title": "BOT",
                       "rating": 3000},
             "black": {"id": "b",
                       "name": "b",
                       "title": "BOT",
                       "rating": 3000,
                       "provisional": True},
             "initialFen": "startpos",
             "type": "gameFull",
             "state": {"type": "gameState",
                       "moves": "",
                       "wtime": 10000,
                       "btime": 10000,
                       "winc": 100,
                       "binc": 100,
                       "status": "started"}}).encode("utf-8")
        while True:
            board = self.board_queue.get()
            self.board_queue.task_done()

            wtime, btime, increment = self.clock_queue.get()
            self.clock_queue.task_done()

            new_game_state = {"type": "gameState",
                              "moves": " ".join(move.uci() for move in board.move_stack),
                              "wtime": int(to_msec(wtime)),
                              "btime": int(to_msec(btime)),
                              "winc": int(to_msec(increment)),
                              "binc": int(to_msec(increment))}

            if board.is_game_over():
                new_game_state["status"] = "outoftime"
                new_game_state["winner"] = "black"
                yield json.dumps(new_game_state).encode("utf-8")
                break
            if board.move_stack:
                new_game_state["status"] = "started"
                yield json.dumps(new_game_state).encode("utf-8")


class EventStream:
    """Imitate lichess.org's EventStream. Used in tests."""

    def __init__(self, sent_game: bool = False) -> None:
        """:param sent_game: If we have already sent the `gameStart` event, so we don't send it again."""
        self.sent_game = sent_game

    def iter_lines(self) -> Generator[bytes, None, None]:
        """Send the events to lichess-bot."""
        if self.sent_game:
            yield b''
            time.sleep(1)
        else:
            yield json.dumps(
                {"type": "gameStart",
                 "game": {"id": "zzzzzzzz",
                          "source": "friend",
                          "compat": {"bot": True,
                                     "board": True}}}).encode("utf-8")


# Docs: https://lichess.org/api.
class Lichess:
    """Imitate communication with lichess.org."""

    def __init__(self,
                 move_queue: Queue[Optional[chess.Move]],
                 board_queue: Queue[chess.Board],
                 clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]]) -> None:
        """Has the same parameters as `lichess.Lichess` to be able to be used in its placed without any modification."""
        self.baseUrl = "testing"
        self.move_queue = move_queue
        self.board_queue = board_queue
        self.clock_queue = clock_queue
        self.sent_game = False
        self.started_game_stream = False

    def upgrade_to_bot_account(self) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def make_move(self, game_id: str, move: chess.engine.PlayResult) -> JSON_REPLY_TYPE:
        """Send a move to the opponent engine thread."""
        self.move_queue.put(move.move)
        return {}

    def chat(self, game_id: str, room: str, text: str) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def abort(self, game_id: str) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def get_event_stream(self) -> EventStream:
        """Send the `EventStream`."""
        events = EventStream(self.sent_game)
        self.sent_game = True
        return events

    def get_game_stream(self, game_id: str) -> GameStream:
        """Send the `GameStream`."""
        if self.started_game_stream:
            self.move_queue.put(None)
        self.started_game_stream = True
        return GameStream(self.board_queue, self.clock_queue)

    def accept_challenge(self, challenge_id: str) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def decline_challenge(self, challenge_id: str, reason: str = "generic") -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def get_profile(self) -> dict[str, Union[str, bool, dict[str, str]]]:
        """Return a simple profile for the bot that lichess-bot uses when testing."""
        return {"id": "b",
                "username": "b",
                "online": True,
                "title": "BOT",
                "url": "https://lichess.org/@/b",
                "followable": True,
                "following": False,
                "blocking": False,
                "followsYou": False,
                "perfs": {}}

    def get_ongoing_games(self) -> list[dict[str, Any]]:
        """Return that the bot isn't playing a game."""
        return []

    def resign(self, game_id: str) -> None:
        """Isn't used in tests."""
        return

    def get_game_pgn(self, game_id: str) -> str:
        """Return a simple PGN."""
        return """
[Event "Test game"]
[Site "pytest"]
[Date "2022.03.11"]
[Round "1"]
[White "bo"]
[Black "b"]
[Result "0-1"]

*
"""

    def get_online_bots(self) -> list[dict[str, Union[str, bool]]]:
        """Return that the only bot online is us."""
        return [{"username": "b", "online": True}]

    def challenge(self, username: str, payload: REQUESTS_PAYLOAD_TYPE) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def cancel(self, challenge_id: str) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def online_book_get(self, path: str, params: Optional[dict[str, Any]] = None, stream: bool = False) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}

    def is_online(self, user_id: str) -> bool:
        """Return that a bot is online."""
        return True

    def get_public_data(self, user_name: str) -> JSON_REPLY_TYPE:
        """Isn't used in tests."""
        return {}
