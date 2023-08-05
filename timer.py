"""A timer for use in lichess-bot."""
import datetime
from typing import Optional, Union


class Timer:
    """A timer for use in lichess-bot."""

    def __init__(self, duration: Union[datetime.timedelta, float] = 0,
                 backdated_start: Optional[datetime.datetime] = None) -> None:
        """
        Start the timer.

        :param duration: The duration of the timer. If duration is a float, then the unit is seconds.
        :param backdated_start: When the timer started. Used to keep the timers between sessions.
        """
        self.duration = duration if isinstance(duration, datetime.timedelta) else datetime.timedelta(seconds=duration)
        self.reset()
        if backdated_start:
            time_already_used = datetime.datetime.now() - backdated_start
            self.starting_time -= time_already_used

    def is_expired(self) -> bool:
        """Check if a timer is expired."""
        return self.time_since_reset() >= self.duration

    def reset(self) -> None:
        """Reset the timer."""
        self.starting_time = datetime.datetime.now()

    def time_since_reset(self) -> datetime.timedelta:
        """How much time has passed."""
        return datetime.datetime.now() - self.starting_time

    def time_until_expiration(self) -> datetime.timedelta:
        """How much time is left until it expires."""
        return max(datetime.timedelta(), self.duration - self.time_since_reset())

    def starting_timestamp(self) -> datetime.datetime:
        """When the timer started."""
        return datetime.datetime.now() - self.time_since_reset()
