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
        self.time_multiplier = 1.0     # 20× faster than real time
        self.tick_interval = 1.0  
        self.running = False
        self._listeners: List[Callable[[datetime.datetime], None]] = []

    # ---- core time control ----
    def tick(self):
        """Advance simulated time by (1 s × multiplier) and notify listeners."""
        delta = datetime.timedelta(seconds=self.tick_interval * self.time_multiplier)

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
            # Real-time sleep (UI stays smooth)
            time.sleep(1 / max(self.time_multiplier, 1e-6))


    def stop(self):
        """Pause the continuous run loop."""
        self.running = False

        # --------------------------------------------------
    # New Control Methods
    # --------------------------------------------------
    def pause(self):
        self.running = False

    def resume(self):
        self.running = True

    def set_speed(self, multiplier: float):
        """
        Set how fast simulation time advances.
        multiplier = 1.0 → real time
        multiplier = 10.0 → 10× faster
        multiplier = 0.0 → frozen (same as pause)
        """
        if multiplier < 0:
            multiplier = 0.0
        self.time_multiplier = multiplier
        print(f"[GlobalClock] Speed set to {multiplier}×")

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

    def get_seconds_since_midnight(self) -> int:
        """
        Returns total seconds since 00:00 of the simulated day.
        Useful for scheduled dispatch logic.
        """
        t = self.current_time
        return t.hour * 3600 + t.minute * 60 + t.second

    def register_listener(self, callback: Callable[[datetime.datetime], None]):
        """Module (like Track Model) calls once to receive time updates."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def __repr__(self):
        return self.get_time_string()

# Shared singleton
clock = GlobalClock()
