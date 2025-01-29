"""Imitate `lichess.py`. Used in tests."""
import time
import chess.engine
import json
import logging
import traceback
import datetime
from queue import Queue
from requests.models import Response
from typing import Union, Optional, Generator
from lib.lichess import Lichess as OriginalLichess
from lib.timer import to_msec
from lib.lichess_types import (UserProfileType, ChallengeType, REQUESTS_PAYLOAD_TYPE, GameType, OnlineType, PublicDataType,
                       BackoffDetails)

# ruff: noqa: ARG002

logger = logging.getLogger(__name__)


def backoff_handler(details: BackoffDetails) -> None:
    """Log exceptions inside functions with the backoff decorator."""
    logger.debug("Backing off {wait:0.1f} seconds after {tries} tries "
                 "calling function {target} with args {args} and kwargs {kwargs}".format(**details))
    logger.debug(f"Exception: {traceback.format_exc()}")


def is_final(error: Exception) -> bool:
    """Mock error handler for tests when a function has a backup decorator."""
    logger.debug(error)
    return False


class GameStream(Response):
    """Imitate lichess.org's GameStream. Used in tests."""

    def __init__(self,
                 board_queue: Queue[chess.Board],
                 clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]]) -> None:
        """
        Capture the interprocess queues that will feed the gameStream with game information.

        :param board_queue: Updated board positions from the lichess_org_simulator() function.
        :param clock_queue: Updated game clock timings (white time, black time, and increment) from the
        lichess_org_simulator() function.
        """
        self.board_queue = board_queue
        self.clock_queue = clock_queue

    def iter_lines(self, chunk_size: Optional[int] = 512, decode_unicode: bool = False,
                   delimiter: Union[str, bytes, None] = None) -> Generator[bytes, None, None]:
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


class EventStream(Response):
    """Imitate lichess.org's EventStream. Used in tests."""

    def __init__(self, sent_game: bool = False) -> None:
        """
        Start the event stream for the lichess_bot_main() loop.

        :param sent_game: If we have already sent the `gameStart` event, so we don't send it again.
        """
        self.sent_game = sent_game

    def iter_lines(self, chunk_size: Optional[int] = 512, decode_unicode: bool = False,
                   delimiter: Union[str, bytes, None] = None) -> Generator[bytes, None, None]:
        """Send the events to lichess-bot."""
        if self.sent_game:
            yield b""
            time.sleep(1)
        else:
            yield json.dumps(
                {"type": "gameStart",
                 "game": {"id": "zzzzzzzz",
                          "source": "friend",
                          "compat": {"bot": True,
                                     "board": True}}}).encode("utf-8")


# Docs: https://lichess.org/api.
class Lichess(OriginalLichess):
    """Imitate communication with lichess.org."""

    def __init__(self,
                 move_queue: Queue[Optional[chess.Move]],
                 board_queue: Queue[chess.Board],
                 clock_queue: Queue[tuple[datetime.timedelta, datetime.timedelta, datetime.timedelta]]) -> None:
        """
        Capture the interprocess queues to distribute them to the eventStream and gameStream instances.

        :param move_queue: An interprocess queue to send moves chosen by the bot under test to the mock lichess function.
        :param board_queue: An interprocess queue to send board positions to the mock game stream.
        :param clock_queue: An interprocess queue to send game clock information to the mock game stream.
        """
        self.baseUrl = "testing"
        self.move_queue = move_queue
        self.board_queue = board_queue
        self.clock_queue = clock_queue
        self.sent_game = False
        self.started_game_stream = False

    def upgrade_to_bot_account(self) -> None:
        """Isn't used in tests."""

    def make_move(self, game_id: str, move: chess.engine.PlayResult) -> None:
        """Send a move to the opponent engine thread."""
        self.move_queue.put(move.move)

    def accept_takeback(self, game_id: str, accept: bool) -> bool:
        """Isn't used in tests."""
        return False

    def chat(self, game_id: str, room: str, text: str) -> None:
        """Isn't used in tests."""

    def abort(self, game_id: str) -> None:
        """Isn't used in tests."""

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

    def accept_challenge(self, challenge_id: str) -> None:
        """Isn't used in tests."""

    def decline_challenge(self, challenge_id: str, reason: str = "generic") -> None:
        """Isn't used in tests."""

    def get_profile(self) -> UserProfileType:
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

    def get_ongoing_games(self) -> list[GameType]:
        """Return that the bot isn't playing a game."""
        return []

    def resign(self, game_id: str) -> None:
        """Isn't used in tests."""

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

    def get_online_bots(self) -> list[UserProfileType]:
        """Return that the only bot online is us."""
        return [{"username": "b", "online": True}]

    def challenge(self, username: str, payload: REQUESTS_PAYLOAD_TYPE) -> ChallengeType:
        """Isn't used in tests."""
        return {}

    def cancel(self, challenge_id: str) -> None:
        """Isn't used in tests."""

    def online_book_get(self, path: str, params: Optional[dict[str, Union[str, int]]] = None,
                        stream: bool = False) -> OnlineType:
        """Isn't used in tests."""
        return {}

    def is_online(self, user_id: str) -> bool:
        """Return that a bot is online."""
        return True

    def get_public_data(self, user_name: str) -> PublicDataType:
        """Isn't used in tests."""
        return {}
