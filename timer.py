import time


class Timer:
    def __init__(self, duration=-1):
        self.duration = duration
        self.reset()

    def is_expired(self):
        return self.time_since_reset() >= self.duration

    def reset(self):
        self.starting_time = time.time()

    def time_since_reset(self):
        return time.time() - self.starting_time

    def time_until_expiration(self):
        return max(0, self.duration - self.time_since_reset())
