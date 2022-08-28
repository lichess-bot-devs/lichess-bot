import time

class Timer:
    def __init__(self, update_interval):
        self.interval = update_interval
        self.reset()

    def is_expired(self):
        return time.time() > self.last_update + self.interval

    def reset(self):
        self.last_update = time.time()

    def time_since_reset(self):
        return time.time() - self.last_update
