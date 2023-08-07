"""A timer for use in lichess-bot."""
import time
import datetime
from typing import Optional


def msec(time_in_msec: float) -> datetime.timedelta:
    """Create a timedelta duration in milliseconds."""
    return datetime.timedelta(milliseconds=time_in_msec)


def msec_str(duration: datetime.timedelta) -> str:
    """Return a string with the duration value in whole number milliseconds."""
    return f"{round(duration/msec(1))}"


def seconds(time_in_sec: float) -> datetime.timedelta:
    """Create a timedelta duration in seconds."""
    return datetime.timedelta(seconds=time_in_sec)


def sec_str(duration: datetime.timedelta) -> str:
    """Return a string with the duration value in whole number seconds."""
    return f"{round(duration.total_seconds())}"


def minutes(time_in_minutes: float) -> datetime.timedelta:
    """Create a timedelta duration in minutes."""
    return datetime.timedelta(minutes=time_in_minutes)


def hours(time_in_hours: float) -> datetime.timedelta:
    """Create a timedelta duration in hours."""
    return datetime.timedelta(minutes=time_in_hours)


def days(time_in_days: float) -> datetime.timedelta:
    """Create a timedelta duration in minutes."""
    return datetime.timedelta(days=time_in_days)


class Timer:
    """A timer for use in lichess-bot."""

    def __init__(self, duration: datetime.timedelta = seconds(0),
                 backdated_timestamp: Optional[float] = None) -> None:
        """
        Start the timer.

        :param duration: The duration of the timer. If duration is a float, then the unit is seconds.
        :param backdated_timestamp: When the timer started. Used to keep the timers between sessions.
        """
        self.duration = duration
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
        return seconds(time.time() - self.starting_time)

    def time_until_expiration(self) -> datetime.timedelta:
        """How much time is left until it expires."""
        return max(seconds(0), self.duration - self.time_since_reset())

    def starting_timestamp(self) -> float:
        """When the timer started."""
        return time.time() - self.time_since_reset().total_seconds()
