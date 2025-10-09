""" 
 This is the Train Controller Back End.

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def mph_to_mps(v_mph: float) -> float:
    return v_mph * 0.44704


def mps_to_mph(v_mps: float) -> float:
    return v_mps / 0.44704


@dataclass
class TrainState:
    # Identifiers / configuration
    train_id: str = "T1"

    # Control gains
    kp: float = 0.8
    ki: float = 0.3

    # Limits
    MAX_SPEED_MPS: float = mph_to_mps(70.0)  # spec sheet max ~70 km/h shown; UI shows mph <=160, but we’ll cap controller

    # Inputs (from Track/CTC/Train Model/UI)
    commanded_speed_mps: float = 0.0          # from CTC/Track circuit
    commanded_authority_m: float = 0.0        # from CTC/Track circuit (remaining distance)
    service_brake_cmd: bool = False           # from Driver (UI)
    emergency_brake_cmd: bool = False         # from Driver/Passenger/Train Model
    driver_set_speed_mps: float = 0.0         # from Driver (UI) in Manual
    auto_mode: bool = True                    # True: use CTC commanded speed; False: driver_set_speed
    speed_limit_mps: float = mph_to_mps(70.0) # optional “block limit” field (UI knob here)

    doors_left_open: bool = False
    doors_right_open: bool = False
    headlights_on: bool = False
    cabin_lights_on: bool = False
    temp_setpoint_c: float = 20.0

    # Train model feedback (these would be set by the Train Model in integration)
    actual_speed_mps: float = 0.0

    # Outputs to Train Model
    power_kw: float = 0.0
    service_brake_out: bool = False
    emergency_brake_out: bool = False

    # Internals for PI
    _i_err: float = 0.0


class TrainControllerBackend:
    """
    Safety-first velocity regulator with simple PI for Iteration #2 demo.
    Produces power (kW) & brake commands, manages doors/lights/temp, and enforces
    basic safety constraints (authority, EB, speed cap).
    """

    def __init__(self, train_id: str = "T1") -> None:
        self.state = TrainState(train_id=train_id)

    # -------- External setters (CTC/Track/TrainModel/UI) --------
    def set_commanded_speed(self, speed_mps: float) -> None:
        self.state.commanded_speed_mps = max(0.0, float(speed_mps))

    def set_commanded_authority(self, authority_m: float) -> None:
        # Non-negative; if None is supplied, treat as 0 for safety.
        self.state.commanded_authority_m = max(0.0, float(authority_m))

    def set_driver_speed(self, speed_mps: float) -> None:
        self.state.driver_set_speed_mps = max(0.0, float(speed_mps))

    def set_auto_mode(self, enabled: bool) -> None:
        self.state.auto_mode = bool(enabled)

    def set_speed_limit(self, limit_mps: float) -> None:
        self.state.speed_limit_mps = max(0.0, float(limit_mps))

    def set_kp(self, kp: float) -> None:
        self.state.kp = max(0.0, float(kp))

    def set_ki(self, ki: float) -> None:
        self.state.ki = max(0.0, float(ki))

    def set_service_brake(self, active: bool) -> None:
        self.state.service_brake_cmd = bool(active)

    def set_emergency_brake(self, active: bool) -> None:
        self.state.emergency_brake_cmd = bool(active)

    def set_doors_left(self, open_: bool) -> None:
        # For iteration 2, allow manual; later you can gate by speed==0
        self.state.doors_left_open = bool(open_)

    def set_doors_right(self, open_: bool) -> None:
        self.state.doors_right_open = bool(open_)

    def set_headlights(self, on: bool) -> None:
        self.state.headlights_on = bool(on)

    def set_cabin_lights(self, on: bool) -> None:
        self.state.cabin_lights_on = bool(on)

    def set_temp_setpoint_c(self, temp_c: float) -> None:
        self.state.temp_setpoint_c = float(temp_c)

    def set_actual_speed(self, speed_mps: float) -> None:
        self.state.actual_speed_mps = max(0.0, float(speed_mps))

    # -------- Main update --------
    def update(self, dt_s: float) -> None:
        """
        Compute power/brake outputs for the next tick.
        dt_s: simulation tick in seconds (e.g., 0.1 s).
        """
        s = self.state

        # Safety: Emergency Brake hard stop
        if s.emergency_brake_cmd:
            s.power_kw = 0.0
            s.emergency_brake_out = True
            s.service_brake_out = False
            self._reset_integrator()
            return
        else:
            s.emergency_brake_out = False

        # Determine target speed (PI setpoint)
        target = s.commanded_speed_mps if s.auto_mode else s.driver_set_speed_mps
        # Always enforce speed limit and controller max
        target = min(target, s.speed_limit_mps, s.MAX_SPEED_MPS)

        # Authority guard: if authority is zero (or extremely low), cut power and apply service brake.
        if s.commanded_authority_m <= 0.0:
            s.power_kw = 0.0
            s.service_brake_out = True
            self._reset_integrator()
            return

        # Manual service brake request overrides controller
        if s.service_brake_cmd:
            s.power_kw = 0.0
            s.service_brake_out = True
            self._reset_integrator()
            return
        else:
            s.service_brake_out = False

        # Basic PI control on speed error
        err = max(0.0, target) - max(0.0, s.actual_speed_mps)
        s._i_err += err * dt_s
        u = s.kp * err + s.ki * s._i_err

        # Convert a simple "u" to kW. For demo we clamp and scale.
        # You can tune this constant to make the needle movement nice in your Train Model.
        kw = max(0.0, min(120.0, u * 50.0))

        s.power_kw = kw

    def _reset_integrator(self) -> None:
        self.state._i_err = 0.0

    # -------- Telemetry getters used by UI --------
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
            "kp": s.kp,
            "ki": s.ki,
            "service_brake": s.service_brake_out,
            "emergency_brake": s.emergency_brake_out,
            "doors_left": s.doors_left_open,
            "doors_right": s.doors_right_open,
            "headlights": s.headlights_on,
            "cabin_lights": s.cabin_lights_on,
            "temp_c": s.temp_setpoint_c,
        }
