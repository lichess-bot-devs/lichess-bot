"""Tests for noticing that the lichess event stream has gone silent."""

from lib import lichess_bot
from lib.lichess import stop
from lib.lichess_types import CONTROL_QUEUE_TYPE, EventType
from lib.timer import msec
from queue import Queue
import pytest


def empty_control_queue() -> CONTROL_QUEUE_TYPE:
    """Create a control queue that no event-stream process is writing to."""
    queue: Queue[EventType] = Queue()
    return queue


def test_silent_event_stream_asks_for_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stream that sends neither events nor pings is dead, and waiting on it forever is not an option."""
    monkeypatch.setattr(lichess_bot, "EVENT_STREAM_SILENCE_LIMIT", msec(10))
    monkeypatch.setattr(stop, "restart", False)

    assert lichess_bot.next_event(empty_control_queue()) == {}
    assert stop.restart is True


def test_event_before_the_silence_limit_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stream that is still delivering pings must not be declared dead."""
    monkeypatch.setattr(lichess_bot, "EVENT_STREAM_SILENCE_LIMIT", msec(10))
    monkeypatch.setattr(stop, "restart", False)
    control_queue = empty_control_queue()
    control_queue.put_nowait({"type": "ping"})

    assert lichess_bot.next_event(control_queue) == {"type": "ping"}
    assert stop.restart is False
