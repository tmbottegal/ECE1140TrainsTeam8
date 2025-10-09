""" 

 This is the Train Controller Front End.

"""

from __future__ import annotations
from typing import Optional

try:
    from .TrainControllerBackend import TrainControllerBackend, mph_to_mps
except Exception:
    from TrainControllerBackend import TrainControllerBackend, mph_to_mps


class TrainControllerFrontend:
    """
    Thin façade between UI and backend. Owns the controller object and exposes
    simple typed methods for the UI. Also provides a periodic tick() hook the UI
    calls via QTimer.
    """

    def __init__(self, train_id: str = "T1") -> None:
        self.ctrl = TrainControllerBackend(train_id=train_id)

    # ---- UI -> Backend setters ----
    def set_auto_mode(self, enabled: bool) -> None:
        self.ctrl.set_auto_mode(enabled)

    def set_driver_speed_mph(self, mph: float) -> None:
        self.ctrl.set_driver_speed(mph_to_mps(mph))

    def set_ctc_command(self, speed_mph: float, authority_m: float) -> None:
        self.ctrl.set_commanded_speed(mph_to_mps(speed_mph))
        self.ctrl.set_commanded_authority(authority_m)

    def set_speed_limit_mph(self, mph: float) -> None:
        self.ctrl.set_speed_limit(mph_to_mps(mph))

    def set_kp(self, kp: float) -> None:
        self.ctrl.set_kp(kp)

    def set_ki(self, ki: float) -> None:
        self.ctrl.set_ki(ki)

    def set_service_brake(self, active: bool) -> None:
        self.ctrl.set_service_brake(active)

    def set_emergency_brake(self, active: bool) -> None:
        self.ctrl.set_emergency_brake(active)

    def set_doors_left(self, open_: bool) -> None:
        self.ctrl.set_doors_left(open_)

    def set_doors_right(self, open_: bool) -> None:
        self.ctrl.set_doors_right(open_)

    def set_headlights(self, on: bool) -> None:
        self.ctrl.set_headlights(on)

    def set_cabin_lights(self, on: bool) -> None:
        self.ctrl.set_cabin_lights(on)

    def set_temp_c(self, temp_c: float) -> None:
        self.ctrl.set_temp_setpoint_c(temp_c)

    def set_actual_speed_mph(self, mph: float) -> None:
        # For Iteration #2 demo, allow the user to knob this to see the PI response
        self.ctrl.set_actual_speed(mph_to_mps(mph))

    # ---- Tick & telemetry ----
    def tick(self, dt_s: float) -> dict:
        self.ctrl.update(dt_s)
        return self.ctrl.get_display_values()
