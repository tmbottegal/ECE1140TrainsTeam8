# universal/global_clock.py
import datetime, time
from typing import Callable, List

class GlobalClock:
    """CTC-owned global simulation clock.

    Keeps a simulated datetime, advances by a time multiplier,
    and notifies registered listeners (e.g. Track Model) whenever it ticks.
    """

    def __init__(self, start_hour: int = 6, start_minute: int = 0):
        # --- CHOOSE START MODE -------------------------------------------------
        USE_REAL_SYSTEM_TIME = False   # <--- toggle this True to use real time

        now = datetime.datetime.now()
        if USE_REAL_SYSTEM_TIME:
            # Start exactly from the computer's real clock time
            self.current_time = now
        else:
            # Start from today's date but a fixed hour/minute (e.g., 06:00)
            self.current_time = now.replace(
                hour=start_hour, minute=start_minute, second=0, microsecond=0
            )
        # ----------------------------------------------------------------------
        self.time_multiplier = 20.0     # 20× faster than real time
        self.running = False
        self._listeners: List[Callable[[datetime.datetime], None]] = []

    # ---- core time control ----
    def tick(self):
        """Advance simulated time by (1 s × multiplier) and notify listeners."""
        delta = datetime.timedelta(seconds=self.time_multiplier)
        self.current_time += delta
        for cb in self._listeners:
            try:
                cb(self.current_time)
            except Exception as e:
                print(f"[GlobalClock] listener error: {e}")

    def run(self):
        """Continuously tick every real second."""
        self.running = True
        while self.running:
            self.tick()
            time.sleep(1)

    def stop(self):
        """Pause the continuous run loop."""
        self.running = False

    # ---- manual + info ----
    def set_time(self, hour: int, minute: int, second: int = 0):
        """Manually set simulation time."""
        self.current_time = self.current_time.replace(
            hour=hour, minute=minute, second=second
        )
        for cb in self._listeners:
            cb(self.current_time)

    def get_time(self) -> datetime.datetime:
        return self.current_time

    def get_time_string(self) -> str:
        return self.current_time.strftime("%I:%M:%S %p")

    def register_listener(self, callback: Callable[[datetime.datetime], None]):
        """Module (like Track Model) calls once to receive time updates."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def __repr__(self):
        return self.get_time_string()

# Shared singleton
clock = GlobalClock()
