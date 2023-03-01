import time


class Timer:
    def __init__(self, duration: int = 0) -> None:
        self.duration = duration
        self.reset()

    def is_expired(self) -> bool:
        return self.time_since_reset() >= self.duration

    def reset(self) -> None:
        self.starting_time = time.time()

    def time_since_reset(self) -> float:
        return time.time() - self.starting_time

    def time_until_expiration(self) -> float:
        return max(0., self.duration - self.time_since_reset())
