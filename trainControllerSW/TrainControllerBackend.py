""" 
 This is the Train Controller Back End.

"""

from __future__ import annotations
from dataclasses import dataclass

def mph_to_mps(v_mph: float) -> float: return v_mph * 0.44704
def mps_to_mph(v_mps: float) -> float: return v_mps / 0.44704

@dataclass
class TrainState:
    train_id: str = "T1"
    # PI gains
    kp: float = 0.8
    ki: float = 0.3
    # limits
    MAX_SPEED_MPS: float = mph_to_mps(70.0)
    speed_limit_mps: float = mph_to_mps(70.0)

    # inputs (ALL ultimately sourced from Train Model via Frontend)
    commanded_speed_mps: float = 0.0     # TM->TC
    commanded_authority_m: float = 0.0   # TM->TC
    actual_speed_mps: float = 0.0        # TM->TC
    auto_mode: bool = True               # Engineer
    driver_set_speed_mps: float = 0.0    # Driver (manual)
    service_brake_cmd: bool = False      # Engineer
    emergency_brake_cmd: bool = False    # Engineer

    # side features
    doors_left_open: bool = False
    doors_right_open: bool = False
    headlights_on: bool = False
    cabin_lights_on: bool = False
    temp_setpoint_c: float = 20.0

    # outputs to Train Model
    power_kw: float = 0.0
    service_brake_out: bool = False
    emergency_brake_out: bool = False

    # internal
    _i_err: float = 0.0

class TrainControllerBackend:
    """On-board controller: speed PI + safety guards. Outputs power/brakes only."""

    def __init__(self, train_id: str = "T1") -> None:
        self.state = TrainState(train_id=train_id)

    # -------- setters (all sources) --------
    def set_commanded_speed(self, speed_mps: float) -> None:
        self.state.commanded_speed_mps = max(0.0, float(speed_mps))

    def set_commanded_authority(self, authority_m: float) -> None:
        self.state.commanded_authority_m = max(0.0, float(authority_m))

    def set_actual_speed(self, speed_mps: float) -> None:
        self.state.actual_speed_mps = max(0.0, float(speed_mps))

    def set_auto_mode(self, enabled: bool) -> None: self.state.auto_mode = bool(enabled)
    def set_driver_speed(self, speed_mps: float) -> None: self.state.driver_set_speed_mps = max(0.0, float(speed_mps))
    def set_speed_limit(self, limit_mps: float) -> None: self.state.speed_limit_mps = max(0.0, float(limit_mps))
    def set_kp(self, kp: float) -> None: self.state.kp = max(0.0, float(kp))
    def set_ki(self, ki: float) -> None: self.state.ki = max(0.0, float(ki))
    def set_service_brake(self, active: bool) -> None: self.state.service_brake_cmd = bool(active)
    def set_emergency_brake(self, active: bool) -> None: self.state.emergency_brake_cmd = bool(active)
    def set_doors_left(self, open_: bool) -> None: self.state.doors_left_open = bool(open_)
    def set_doors_right(self, open_: bool) -> None: self.state.doors_right_open = bool(open_)
    def set_headlights(self, on: bool) -> None: self.state.headlights_on = bool(on)
    def set_cabin_lights(self, on: bool) -> None: self.state.cabin_lights_on = bool(on)
    def set_temp_setpoint_c(self, temp_c: float) -> None: self.state.temp_setpoint_c = float(temp_c)

    # -------- main update --------
    def update(self, dt_s: float) -> None:
        s = self.state

        # EB is king
        if s.emergency_brake_cmd:
            s.emergency_brake_out = True
            s.service_brake_out = False
            s.power_kw = 0.0
            self._reset_integrator()
            return
        else:
            s.emergency_brake_out = False

        # authority guard (0 or negative -> stop with SB)
        if s.commanded_authority_m <= 0.0:
            s.service_brake_out = True
            s.power_kw = 0.0
            self._reset_integrator()
            return

        # manual SB
        if s.service_brake_cmd:
            s.service_brake_out = True
            s.power_kw = 0.0
            self._reset_integrator()
            return
        else:
            s.service_brake_out = False

        # setpoint
        target = s.commanded_speed_mps if s.auto_mode else s.driver_set_speed_mps
        target = min(max(0.0, target), s.speed_limit_mps, s.MAX_SPEED_MPS)

        # PI
        err = target - s.actual_speed_mps
        s._i_err += max(0.0, err) * dt_s    # simple anti-windup on negative error
        u = s.kp * err + s.ki * s._i_err

        # map to kW and clamp (tune constant to taste)
        s.power_kw = max(0.0, min(120.0, u * 50.0))

    def _reset_integrator(self) -> None:
        self.state._i_err = 0.0

    # -------- telemetry for UI --------
    def get_display_values(self) -> dict:
        s = self.state
        return {
            "train_id": s.train_id,
            "cmd_speed_mph": mps_to_mph(s.commanded_speed_mps),
            "authority_m": s.commanded_authority_m,
            "driver_set_mph": mps_to_mph(s.driver_set_speed_mps),
            "actual_speed_mph": mps_to_mph(s.actual_speed_mps),
            "power_kw": s.power_kw,
            "auto_mode": s.auto_mode,
            "kp": s.kp, "ki": s.ki,
            "service_brake": s.service_brake_out,
            "emergency_brake": s.emergency_brake_out,
            "doors_left": s.doors_left_open, "doors_right": s.doors_right_open,
            "headlights": s.headlights_on, "cabin_lights": s.cabin_lights_on,
            "temp_c": s.temp_setpoint_c,
        }