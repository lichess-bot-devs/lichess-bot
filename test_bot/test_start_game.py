"""Tests for starting games without exceeding challenge.concurrency."""

from lib import lichess_bot
from lib.lichess_bot import PlayGameArgsType
from collections.abc import Iterator
from requests.exceptions import HTTPError
from typing import cast
import pytest


class MockLichess:
    """A stand-in for `lichess.Lichess` that records abort attempts."""

    def __init__(self, abort_error: Exception | None = None) -> None:
        """Create a mock lichess connection whose abort() raises `abort_error`, if given."""
        self.aborted: list[str] = []
        self.abort_error = abort_error

    def abort(self, game_id: str) -> None:
        """Record the abort attempt, and fail it if the test asked for a failure."""
        self.aborted.append(game_id)
        if self.abort_error is not None:
            raise self.abort_error


class MockPool:
    """A stand-in for the process pool that records the games handed to it."""

    def __init__(self) -> None:
        """Create a mock pool that has been given no games."""
        self.games: list[str] = []

    def apply_async(self, func: object, kwds: PlayGameArgsType, error_callback: object) -> None:  # noqa: ARG002
        """Record the game that would have been played in a pool process."""
        self.games.append(kwds["game_id"])


@pytest.fixture(autouse=True)
def _empty_games_in_progress() -> Iterator[None]:
    """Start and leave every test with no game holding a pool process."""
    lichess_bot.games_in_progress.clear()
    yield
    lichess_bot.games_in_progress.clear()


def start_game(li: MockLichess, pool: MockPool, active_games: dict[str, str], game_id: str, max_games: int) -> None:
    """Call `start_game_thread()` with mock lichess and pool objects."""
    play_game_args = cast(PlayGameArgsType, {"li": li})
    lichess_bot.start_game_thread(active_games, game_id, "opponent", play_game_args,
                                  cast(lichess_bot.POOL_TYPE, pool), max_games)


def test_game_within_the_concurrency_limit_is_played() -> None:
    """A game that can get a pool process is played, not aborted."""
    li, pool = MockLichess(), MockPool()
    active_games = {"first_game": "opponent"}
    lichess_bot.games_in_progress.add("first_game")

    start_game(li, pool, active_games, "second_game", 2)

    assert pool.games == ["second_game"]
    assert li.aborted == []
    assert active_games["second_game"] == "opponent"


def test_game_beyond_the_concurrency_limit_is_aborted() -> None:
    """A game with no free pool process is aborted instead of waiting for one."""
    li, pool = MockLichess(), MockPool()
    active_games = {"first_game": "opponent"}
    lichess_bot.games_in_progress.add("first_game")

    start_game(li, pool, active_games, "second_game", 1)

    assert li.aborted == ["second_game"]
    assert pool.games == []
    assert "second_game" not in active_games
    assert "second_game" not in lichess_bot.games_in_progress


def test_overflow_game_that_cannot_be_aborted_is_left_alone() -> None:
    """Lichess refuses to abort a game with moves, but such a game must not be played or resigned either."""
    li, pool = MockLichess(HTTPError("400 Client Error")), MockPool()
    active_games = {"first_game": "opponent"}
    lichess_bot.games_in_progress.add("first_game")

    start_game(li, pool, active_games, "second_game", 1)

    assert li.aborted == ["second_game"]
    assert pool.games == []
    assert "second_game" not in active_games
    assert "second_game" not in lichess_bot.games_in_progress
