class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return 1700000000 + self.now

    def advance(self, seconds):
        self.now += seconds
