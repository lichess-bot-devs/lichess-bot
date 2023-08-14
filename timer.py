"""A timer for use in lichess-bot."""
import time
import datetime
from typing import Optional


def msec(time_in_msec: float) -> datetime.timedelta:
    """Create a timedelta duration in milliseconds."""
    return datetime.timedelta(milliseconds=time_in_msec)


def to_msec(duration: datetime.timedelta) -> float:
    """Return a bare number representing the length of the duration in milliseconds."""
    return duration / msec(1)


def msec_str(duration: datetime.timedelta) -> str:
    """Return a string with the duration value in whole number milliseconds."""
    return f"{round(to_msec(duration))}"


def seconds(time_in_sec: float) -> datetime.timedelta:
    """Create a timedelta duration in seconds."""
    return datetime.timedelta(seconds=time_in_sec)


def to_seconds(duration: datetime.timedelta) -> float:
    """Return a bare number representing the length of the duration in seconds."""
    return duration.total_seconds()


def sec_str(duration: datetime.timedelta) -> str:
    """Return a string with the duration value in whole number seconds."""
    return f"{round(to_seconds(duration))}"


def minutes(time_in_minutes: float) -> datetime.timedelta:
    """Create a timedelta duration in minutes."""
    return datetime.timedelta(minutes=time_in_minutes)


def hours(time_in_hours: float) -> datetime.timedelta:
    """Create a timedelta duration in hours."""
    return datetime.timedelta(minutes=time_in_hours)


def days(time_in_days: float) -> datetime.timedelta:
    """Create a timedelta duration in minutes."""
    return datetime.timedelta(days=time_in_days)


def years(time_in_years: float) -> datetime.timedelta:
    """Create a timedelta duration in median years--i.e., 365 days."""
    return days(365 * time_in_years)


class Timer:
    """
    A timer for use in lichess-bot. An instance of timer can be used both as a countdown timer and a stopwatch.

    If the duration argument in the __init__() method is greater than zero, then
    the method is_expired() indicates when the intial duration has passed. The
    method time_until_expiration() gives the amount of time left until the timer
    expires.

    Regardless of the initial duration (even if it's zero), a timer can be used
    as a stopwatch by calling time_since_reset() to get the amount of time since
    the timer was created or since it was last reset.
    """

    def __init__(self, duration: datetime.timedelta = seconds(0),
                 backdated_timestamp: Optional[datetime.datetime] = None) -> None:
        """
        Start the timer.

        :param duration: The duration of time before Timer.is_expired() returns True.
        :param backdated_timestamp: When the timer should have started. Used to keep the timers between sessions.
        """
        self.duration = duration
        self.reset()
        if backdated_timestamp is not None:
            time_already_used = datetime.datetime.now() - backdated_timestamp
            self.starting_time -= to_seconds(time_already_used)

    def is_expired(self) -> bool:
        """Check if a timer is expired."""
        return self.time_since_reset() >= self.duration

    def reset(self) -> None:
        """Reset the timer."""
        self.starting_time = time.perf_counter()

    def time_since_reset(self) -> datetime.timedelta:
        """How much time has passed."""
        return seconds(time.perf_counter() - self.starting_time)

    def time_until_expiration(self) -> datetime.timedelta:
        """How much time is left until it expires."""
        return max(seconds(0), self.duration - self.time_since_reset())

    def starting_timestamp(self, format: str) -> str:
        """When the timer started."""
        return (datetime.datetime.now() - self.time_since_reset()).strftime(format)
