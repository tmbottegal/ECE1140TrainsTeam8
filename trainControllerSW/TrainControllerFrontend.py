"""
Train Controller Frontend
"""

from __future__ import annotations
from typing import Optional

try:
    from .TrainControllerBackend import TrainControllerBackend, mph_to_mps, mps_to_mph
except Exception:
    from TrainControllerBackend import TrainControllerBackend, mph_to_mps, mps_to_mph

# optional Train Model import (same-process integration)
try:
    from train_model_backend import TrainModelBackend  # type: ignore
except Exception:  # running without the TM in path
    TrainModelBackend = None  # type: ignore


class TrainControllerFrontend:
    """
    Glue between UI and Backend. If a TrainModelBackend is provided, this
    object pulls inputs from it and pushes outputs back to it (the sim steps).
    """

    def __init__(self, train_id: str = "T1", train_model: Optional["TrainModelBackend"] = None) -> None:
        self.ctrl = TrainControllerBackend(train_id=train_id)
        self.tm: Optional["TrainModelBackend"] = train_model  # may be None
        # fallback demo speed when TM is not attached
        self._demo_speed_mps = 0.0

    # ------- feature flags for UI -------
    def has_train_model(self) -> bool:
        return self.tm is not None

    # ------- UI -> controller setters -------
    def set_auto_mode(self, enabled: bool) -> None: self.ctrl.set_auto_mode(enabled)
    def set_driver_speed_mph(self, mph: float) -> None: self.ctrl.set_driver_speed(mph_to_mps(mph))
    def set_speed_limit_mph(self, mph: float) -> None: self.ctrl.set_speed_limit(mph_to_mps(mph))
    def set_kp(self, kp: float) -> None: self.ctrl.set_kp(kp)
    def set_ki(self, ki: float) -> None: self.ctrl.set_ki(ki)
    def set_service_brake(self, active: bool) -> None: self.ctrl.set_service_brake(active)
    def set_emergency_brake(self, active: bool) -> None: self.ctrl.set_emergency_brake(active)
    def set_doors_left(self, open_: bool) -> None: self.ctrl.set_doors_left(open_)
    def set_doors_right(self, open_: bool) -> None: self.ctrl.set_doors_right(open_)
    def set_headlights(self, on: bool) -> None: self.ctrl.set_headlights(on)
    def set_cabin_lights(self, on: bool) -> None: self.ctrl.set_cabin_lights(on)
    def set_temp_c(self, temp_c: float) -> None: self.ctrl.set_temp_setpoint_c(temp_c)

    # demo-only knobs fall back when no Train Model is attached
    def set_actual_speed_mph(self, mph: float) -> None:
        if self.tm is None:
            self._demo_speed_mps = mph_to_mps(mph)
            self.ctrl.set_actual_speed(self._demo_speed_mps)

    # “CTC push” in the UI writes into the Train Model (so inputs come *from* TM)
    def set_ctc_command(self, speed_mph: float, authority_m: float) -> None:
        if self.tm is not None:
            # write into TM so the controller later *reads* from TM
            self.tm.commanded_speed = mph_to_mps(speed_mph)
            self.tm.authority_m = float(authority_m)
        else:
            # no TM attached → still allow local testing
            self.ctrl.set_commanded_speed(mph_to_mps(speed_mph))
            self.ctrl.set_commanded_authority(authority_m)

    # ------- tick -------
    def tick(self, dt_s: float) -> dict:
        """
        Integration loop:
          TM → (cmd speed, authority, actual v, grade, beacon)
          TC → compute → (power, SB/EB)
          TC → TM.set_inputs(...)    # TM steps its sim here
        """
        if self.tm is not None:
            # 1) Pull inputs from Train Model
            s = self.tm.report_state()
            v_mps = float(s.get("velocity", 0.0))
            cmd_mps = float(s.get("commanded_speed", 0.0))
            auth_m = float(s.get("authority", 0.0))
            grade = float(s.get("grade", 0.0))
            beacon = str(s.get("beacon", "None"))

            self.ctrl.set_actual_speed(v_mps)
            self.ctrl.set_commanded_speed(cmd_mps)
            self.ctrl.set_commanded_authority(auth_m)

            # 2) Run controller
            self.ctrl.update(dt_s)
            disp = self.ctrl.get_display_values()

            # 3) Push outputs to Train Model (single step)
            self.tm.set_inputs(
                power_kw=float(disp["power_kw"]),
                service_brake=bool(disp["service_brake"]),
                emergency_brake=bool(disp["emergency_brake"]),
                grade_percent=grade,
                beacon_info=beacon,
            )

            return disp

        # ------- demo mode (no Train Model) -------
        self.ctrl.set_actual_speed(self._demo_speed_mps)
        self.ctrl.update(dt_s)

        # toy physics so the needle moves
        disp = self.ctrl.get_display_values()
        power_kw = float(disp.get("power_kw", 0.0))
        eb_on = bool(disp.get("emergency_brake", False))
        sb_on = bool(disp.get("service_brake", False))

        if eb_on: a = -3.0
        elif sb_on: a = -1.0
        else: a = 0.02 * power_kw

        self._demo_speed_mps = max(0.0, self._demo_speed_mps + a * dt_s)
        self.ctrl.set_actual_speed(self._demo_speed_mps)
        return self.ctrl.get_display_values()