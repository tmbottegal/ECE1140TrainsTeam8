import datetime
import time

class GlobalClock:
    """Global simulation clock shared by all modules.

    Tracks and advances simulated time. The simulation runs faster
    than real time based on `time_multiplier`. Pausing stops time
    progression, and resuming continues from the last point.
    """

    def __init__(self, start_hour=6, start_minute=59):
        # Start at current system time (can be changed to fixed start if desired)
        self.current_time = datetime.datetime.now()

        #We could also start from a fixed reference point if wanted 
        #EX: Todays date but a fixed time 
        #now = datetime.datetime.now()
        #self.current_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)

        # How many simulated seconds pass per real second
        # (20 = 20x faster than real time)
        self.time_multiplier = 20

        # Whether the simulation clock is actively running
        self.running = False

    def tick(self):
        """Advance simulated time by `time_multiplier` seconds."""
        delta = datetime.timedelta(seconds=self.time_multiplier)
        self.current_time += delta

    def run(self):
        """Continuously advance time once per real second until stopped."""
        self.running = True
        while self.running:
            self.tick()
            time.sleep(1)  # wait one real second before next tick

    def stop(self):
        """Pause the simulation clock."""
        self.running = False

    def set_time(self, hour, minute):
        """Manually set the current simulation time (hour, minute)."""
        self.current_time = self.current_time.replace(hour=hour, minute=minute)
    def get_time(self):
        """Return the current simulation datetime object."""
        return self.current_time


    def __repr__(self):
        """Return a readable time string like '07:42 AM'."""
        return self.current_time.strftime("%I:%M %p")

# Shared global instance imported by all modules
clock = GlobalClock()
