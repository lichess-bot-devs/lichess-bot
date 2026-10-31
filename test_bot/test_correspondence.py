"""Tests for correspondence game handling."""

from multiprocessing import Manager
from typing import cast
from unittest.mock import MagicMock

from lib import lichess_bot
from lib.config import Configuration
from lib.lichess import Lichess
from lib.lichess_bot import MULTIPROCESSING_LIST_TYPE, PlayGameArgsType
from lib.lichess_types import (
    CONTROL_QUEUE_TYPE,
    CORRESPONDENCE_QUEUE_TYPE,
    LOGGING_QUEUE_TYPE,
    PGN_QUEUE_TYPE,
)


def _make_play_game_args(correspondence_queue: CORRESPONDENCE_QUEUE_TYPE,
                         challenge_queue: MULTIPROCESSING_LIST_TYPE) -> PlayGameArgsType:
    """Build a minimal ``play_game_args`` dict for testing."""
    manager = Manager()
    return PlayGameArgsType(
        li=cast(Lichess, MagicMock()),
        control_queue=cast(CONTROL_QUEUE_TYPE, manager.Queue()),
        pgn_queue=cast(PGN_QUEUE_TYPE, manager.Queue()),
        user_profile={"username": "testbot"},
        config=cast(Configuration, MagicMock()),
        challenge_queue=challenge_queue,
        correspondence_queue=correspondence_queue,
        logging_queue=cast(LOGGING_QUEUE_TYPE, manager.Queue()),
    )


def _reset_counter() -> None:
    """Reset the module-level correspondence counter between tests."""
    lichess_bot.correspondence_games_to_start = 0


def test_correspondence_ping_with_queued_game_does_not_crash() -> None:
    """
    ``correspondence_ping`` (no ``game`` key) must not crash when games are queued.

    Regression: prior to the fix, ``event["game"]`` raised ``KeyError: 'game'``
    because the synthetic ping event has no ``game`` field at all.
    """
    _reset_counter()
    manager = Manager()
    correspondence_queue = cast(CORRESPONDENCE_QUEUE_TYPE, manager.Queue())
    challenge_queue = cast(MULTIPROCESSING_LIST_TYPE, manager.list())
    active_games: dict[str, str] = {}
    correspondence_queue.put_nowait(("d5qiLiZH", "SomeOpponent"))

    lichess_bot.check_in_on_correspondence_games(
        pool=MagicMock(),
        event={"type": "correspondence_ping"},
        correspondence_queue=correspondence_queue,
        challenge_queue=challenge_queue,
        play_game_args=_make_play_game_args(correspondence_queue, challenge_queue),
        active_games=active_games,
        max_games=5,
    )

    assert active_games == {"d5qiLiZH": "SomeOpponent"}
    assert correspondence_queue.qsize() == 0


def test_local_game_done_does_not_crash() -> None:
    """``local_game_done`` (only ``game.id``) must not crash and must start queued games."""
    _reset_counter()
    manager = Manager()
    correspondence_queue = cast(CORRESPONDENCE_QUEUE_TYPE, manager.Queue())
    challenge_queue = cast(MULTIPROCESSING_LIST_TYPE, manager.list())
    active_games: dict[str, str] = {}
    correspondence_queue.put_nowait(("abcdefgh", "BotOpponent"))
    # ``local_game_done`` does not refresh the counter; simulate that a prior
    # ping already set it to the queue size.
    lichess_bot.correspondence_games_to_start = correspondence_queue.qsize()

    lichess_bot.check_in_on_correspondence_games(
        pool=MagicMock(),
        event={"type": "local_game_done", "game": {"id": "oldgame"}},
        correspondence_queue=correspondence_queue,
        challenge_queue=challenge_queue,
        play_game_args=_make_play_game_args(correspondence_queue, challenge_queue),
        active_games=active_games,
        max_games=5,
    )

    assert active_games == {"abcdefgh": "BotOpponent"}
    assert correspondence_queue.qsize() == 0


def test_correspondence_queue_does_not_crash_with_no_queue() -> None:
    """``correspondence_ping`` with no queued games must be a no-op."""
    _reset_counter()
    manager = Manager()
    correspondence_queue = cast(CORRESPONDENCE_QUEUE_TYPE, manager.Queue())
    challenge_queue = cast(MULTIPROCESSING_LIST_TYPE, manager.list())
    active_games: dict[str, str] = {}

    lichess_bot.check_in_on_correspondence_games(
        pool=MagicMock(),
        event={"type": "correspondence_ping"},
        correspondence_queue=correspondence_queue,
        challenge_queue=challenge_queue,
        play_game_args=_make_play_game_args(correspondence_queue, challenge_queue),
        active_games=active_games,
        max_games=5,
    )

    assert active_games == {}


def test_challenges_block_correspondence_start() -> None:
    """If challenges are pending, queued correspondence games should not be started."""
    _reset_counter()
    manager = Manager()
    correspondence_queue = cast(CORRESPONDENCE_QUEUE_TYPE, manager.Queue())
    challenge_queue = cast(MULTIPROCESSING_LIST_TYPE, manager.list(["pending"]))
    active_games: dict[str, str] = {}
    correspondence_queue.put_nowait(("d5qiLiZH", "SomeOpponent"))

    lichess_bot.check_in_on_correspondence_games(
        pool=MagicMock(),
        event={"type": "correspondence_ping"},
        correspondence_queue=correspondence_queue,
        challenge_queue=challenge_queue,
        play_game_args=_make_play_game_args(correspondence_queue, challenge_queue),
        active_games=active_games,
        max_games=5,
    )

    assert active_games == {}
    # The entry should still be in the queue so it gets started once challenges drain.
    assert correspondence_queue.qsize() == 1


def test_opponent_name_preserved_across_queue_roundtrip() -> None:
    """The opponent name enqueued with the game ID must surface in ``active_games``."""
    _reset_counter()
    manager = Manager()
    correspondence_queue = cast(CORRESPONDENCE_QUEUE_TYPE, manager.Queue())
    challenge_queue = cast(MULTIPROCESSING_LIST_TYPE, manager.list())
    active_games: dict[str, str] = {}
    correspondence_queue.put_nowait(("gameA", "Alice"))
    correspondence_queue.put_nowait(("gameB", "Bob"))
    lichess_bot.correspondence_games_to_start = correspondence_queue.qsize()

    lichess_bot.check_in_on_correspondence_games(
        pool=MagicMock(),
        event={"type": "correspondence_ping"},
        correspondence_queue=correspondence_queue,
        challenge_queue=challenge_queue,
        play_game_args=_make_play_game_args(correspondence_queue, challenge_queue),
        active_games=active_games,
        max_games=5,
    )

    assert active_games == {"gameA": "Alice", "gameB": "Bob"}
