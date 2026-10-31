"""Test that each game is played by one `play_game` process and that a dropped game stream is reopened."""
import json
from collections.abc import Callable, Generator
from typing import cast
from lib import lichess, lichess_bot
from lib.lichess_bot import POOL_TYPE, PlayGameArgsType

# ruff: noqa: ARG002


class FakePool:
    """Records the games that would be started."""

    def __init__(self) -> None:
        """Start with no games."""
        self.started: list[str] = []

    def apply_async(self, func: Callable[..., None], kwds: PlayGameArgsType,
                    error_callback: Callable[[BaseException], None]) -> None:
        """Record the game instead of playing it."""
        self.started.append(kwds["game_id"])


def start(game_id: str, active_games: dict[str, str], games_in_progress: set[str], pool: FakePool) -> None:
    """Start a game the way the main loop does."""
    lichess_bot.start_game_thread(active_games, game_id, "opponent", cast(PlayGameArgsType, {}),
                                  cast(POOL_TYPE, pool), games_in_progress)


def test_repeated_game_start_is_ignored() -> None:
    """A second `gameStart` for a game that is already being played must not start another process."""
    active_games: dict[str, str] = {}
    games_in_progress: set[str] = set()
    pool = FakePool()

    start("abcdefgh", active_games, games_in_progress, pool)
    start("abcdefgh", active_games, games_in_progress, pool)

    assert pool.started == ["abcdefgh"]
    assert active_games == {"abcdefgh": "opponent"}
    assert games_in_progress == {"abcdefgh"}


def test_accepted_challenge_is_started() -> None:
    """An accepted challenge is in `active_games` before its `gameStart`, and must still be started."""
    active_games = {"abcdefgh": "opponent"}
    games_in_progress: set[str] = set()
    pool = FakePool()

    start("abcdefgh", active_games, games_in_progress, pool)

    assert pool.started == ["abcdefgh"]


class FakeGameStream:
    """A game stream with fixed lines."""

    def __init__(self, lines: list[bytes]) -> None:
        """Store the lines."""
        self.lines = lines
        self.closed = False

    def iter_lines(self) -> Generator[bytes, None, None]:
        """Send the lines."""
        yield from self.lines

    def __enter__(self) -> "FakeGameStream":  # noqa: PYI034
        """Enter the stream context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close the stream."""
        self.closed = True


class FakeLichess:
    """Opens fake game streams."""

    def __init__(self, lines: list[bytes]) -> None:
        """Store the lines of the next game stream."""
        self.lines = lines
        self.streams: list[FakeGameStream] = []

    @property
    def streams_opened(self) -> int:
        """The number of game streams opened."""
        return len(self.streams)

    def get_game_stream(self, game_id: str) -> FakeGameStream:
        """Open a game stream."""
        self.streams.append(FakeGameStream(self.lines))
        return self.streams[-1]


def test_reconnect_game_stream_starts_with_current_state() -> None:
    """The reopened stream is opened lazily and starts with the game state from the new full game info."""
    state = {"type": "gameState", "moves": "e2e4 e7e5", "status": "started"}
    next_state = b'{"type": "gameState", "moves": "e2e4 e7e5 g1f3", "status": "started"}'
    li = FakeLichess([json.dumps({"type": "gameFull", "state": state}).encode("utf-8"), next_state])

    stream = lichess_bot.reconnect_game_stream(cast(lichess.Lichess, li), "abcdefgh")
    assert li.streams_opened == 0
    assert [json.loads(line) for line in stream] == [state, json.loads(next_state)]
    assert li.streams_opened == 1
    assert li.streams[0].closed


def test_reconnect_game_stream_that_ends_at_once() -> None:
    """A reopened stream that ends before sending the full game info ends without an error."""
    li = FakeLichess([])

    assert list(lichess_bot.reconnect_game_stream(cast(lichess.Lichess, li), "abcdefgh")) == []
    assert li.streams[0].closed


def test_closing_a_game_stream_closes_the_connection() -> None:
    """Closing a game stream before it ends, as `play_game` does before reopening it, closes the connection."""
    state = {"type": "gameState", "moves": "e2e4", "status": "started"}
    li = FakeLichess([json.dumps({"type": "gameFull", "state": state}).encode("utf-8"), b"", b""])

    for stream in (lichess_bot.game_stream_lines(cast(lichess.Lichess, li), "abcdefgh"),
                   lichess_bot.reconnect_game_stream(cast(lichess.Lichess, li), "abcdefgh")):
        next(stream)
        stream.close()
    assert li.streams_opened == 2
    assert all(opened.closed for opened in li.streams)
