"""A timer for use in lichess-bot."""
import time
import datetime
from typing import Optional


class Timer:
    """A timer for use in lichess-bot."""

    def __init__(self, duration: float = 0, backdated_start: Optional[datetime.datetime] = None) -> None:
        """
        Start the timer.

        :param duration: The duration of the timer.
        :param backdated_start: When the timer started. Used to keep the timers between sessions.
        """
        self.duration = duration
        self.reset()
        if backdated_start:
            time_already_used = datetime.datetime.now() - backdated_start
            self.starting_time -= time_already_used.total_seconds()

    def is_expired(self) -> bool:
        """Check if a timer is expired."""
        return self.time_since_reset() >= self.duration

    def reset(self) -> None:
        """Reset the timer."""
        self.starting_time = time.time()

    def time_since_reset(self) -> float:
        """How much time has passed."""
        return time.time() - self.starting_time

    def time_until_expiration(self) -> float:
        """How much time is left until it expires."""
        return max(0., self.duration - self.time_since_reset())

    def starting_timestamp(self) -> datetime.datetime:
        """When the timer started."""
        return datetime.datetime.now() - datetime.timedelta(seconds=self.time_since_reset())
