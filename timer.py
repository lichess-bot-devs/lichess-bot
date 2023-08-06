"""A timer for use in lichess-bot."""
import time
import datetime
from typing import Optional, Union


class Timer:
    """A timer for use in lichess-bot."""

    def __init__(self, duration: Union[datetime.timedelta, float] = 0,
                 backdated_timestamp: Optional[float] = None) -> None:
        """
        Start the timer.

        :param duration: The duration of the timer. If duration is a float, then the unit is seconds.
        :param backdated_timestamp: When the timer started. Used to keep the timers between sessions.
        """
        self.duration = duration if isinstance(duration, datetime.timedelta) else datetime.timedelta(seconds=duration)
        self.reset()
        if backdated_timestamp is not None:
            time_already_used = time.time() - backdated_timestamp
            self.starting_time -= time_already_used

    def is_expired(self) -> bool:
        """Check if a timer is expired."""
        return self.time_since_reset() >= self.duration

    def reset(self) -> None:
        """Reset the timer."""
        self.starting_time = time.time()

    def time_since_reset(self) -> datetime.timedelta:
        """How much time has passed."""
        return datetime.timedelta(seconds=time.time() - self.starting_time)

    def time_until_expiration(self) -> datetime.timedelta:
        """How much time is left until it expires."""
        return max(datetime.timedelta(), self.duration - self.time_since_reset())

    def starting_timestamp(self) -> float:
        """When the timer started."""
        return time.time() - self.time_since_reset().total_seconds()
