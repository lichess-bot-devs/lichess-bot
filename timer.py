import time


class Timer:
    def __init__(self, duration):
        self.duration = duration
        self.reset()

    def is_expired(self):
        return self.time_since_reset() >= self.duration

    def reset(self):
        self.starting_time = time.time()

    def time_since_reset(self):
        return time.time() - self.starting_time
