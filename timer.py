import time
import datetime
from typing import Optional


class Timer:
    def __init__(self, duration: float = 0, backdated_start: Optional[datetime.datetime] = None) -> None:
        self.duration = duration
        self.reset()
        if backdated_start:
            time_already_used = datetime.datetime.now() - backdated_start
            self.starting_time -= time_already_used.total_seconds()

    def is_expired(self) -> bool:
        return self.time_since_reset() >= self.duration

    def reset(self) -> None:
        self.starting_time = time.time()

    def time_since_reset(self) -> float:
        return time.time() - self.starting_time

    def time_until_expiration(self) -> float:
        return max(0., self.duration - self.time_since_reset())

    def starting_timestamp(self) -> datetime.datetime:
        return datetime.datetime.now() - datetime.timedelta(seconds=self.time_since_reset())
