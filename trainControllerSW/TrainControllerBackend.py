""" 
 This is the Train Controller Back End.

 Core control logic
 - Accepts commanded speed and authority from CTC
 - Runs a PI controller to track target speed
 - Exposes a "tick(dt)" step used by the UI/Frontend timer
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict

class TrainState:

    commanded_speed_mps: float = 0.0

    commanded_authority: bool = False

    service_break: bool = False

    emergency_brake: bool = False

    left_doors_open: bool = False
    right_doors_open: bool = False

    lights_on: bool = False

    cabin_temp_c: float = 21.0

    actual_speed_mps: float = 0.0

    acceleration_mps2: float = 0.0

    _i_err: float = 0.0

    power_watts: float = 0.0

    MAX_POWER_W: float = 120_000.0
    MAX_SERVICE_DECEL: float = 1.2
    MAX_EMERGENCY_DECEL: float = 2.73

    KP: float = 8_000.0
    KI: float = 2_000.0

    MAX_SPEED_MPS: float = 19.44

    I_CLAMP: float = 25_000.0

class SafetyException(Exception):
    pass

class TrainControllerBackend:
        
    def __init__(self, train_id: str = "T1") -> None:
        self.train_id = train_id
        self.state = TrainState()
        
    def set_commanded_speed(self, speed_mps: float) -> None:
        self.state.commanded_speed_mps = max(0.0, min(speed_mps, self.state.MAX_SPEED_MPS))

    def set_service_brake(self, active: bool) -> None:
        self.state.service_brake = bool(active)

    def set_emergency_brake(self, active: bool) -> None:
        self.state.emergency_brake = bool(active)

    def set_doors(self, left_open: Optional[bool] = None, right_open: Optional[bool] = None) -> None:
        if left_open is not None:
            self.state.left_doors_open = bool(left_open)
        if right_open is not None:
            self.state.right_doors_open = bool(right_open)
        
    def set_lights(self, on: bool) -> None:
        self.state.lights_on = bool(on)

    def update_actual_speed(self, speed_mps: float) -> None:
        self.state.actual_speed_mps = max(0.0, speed_mps)

        
    def tick(self, dt: float) -> Dict[str, float]:
        s = self.state
            
        must_stop = (
            not s.commanded_authority
            or s.left_doors_open
            or s.right_doors_open
            or s.emergency_brake
        )

        target = 0.0 if must_stop else min(s.commanded_speed_mps, s.MAX_SPEED_MPS)
            
        speed_err = target - s.actual_speed_mps
        s._i_err += speed_err * dt

        if s._i_err > s.I_CLAMP / s.KI:
            s._i_err = s.I_CLAMP / s.KI
        elif s._i_err < -s.I_CLAMP / s.KI:
            s._i_err = -s.I_CLAMP / s.KI

        traction_power = s.KP * speed_err + s.KI * s._i_err

        commanded_service_decel = s.MAX_SERVICE_DECEL if s.service_brake else 0.0
        commanded_emergency_decel = s.MAX_EMERGENCY_DECEL if s.emergency_brake else 0.0
        total_brake_decel = max(commanded_service_decel, commanded_emergency_decel)

        if total_brake_decel > 0.0 or must_stop:
            traction_power = 0.0

            traction_power = max(0.0, min(traction_power, s.MAX_POWER_W))
            s.power_watts = traction_power

            k_power_to_accel = 1.0 / 25_000.0

            accel_from_power = k_power_to_accel * traction_power

            s.acceleration_mps2 = max(0.0, accel_from_power) - total_brake_decel

        return {
            "power_watts": s.power_watts,
            "service_brake": float(commanded_service_decel > 0 ),
            "emergency_brake": float(commanded_emergency_decel > 0),
            "target_speed_mps": target,
            "accel_cmd_mps2": s.acceleration_mps2,
        }
        

    def snapshot(self) -> Dict[str, float | bool]:
        s = self.state

        return {
            "train_id": self.train_id,
            "cmd_speed_mps": s.commanded_speed_mps,
            "cmd_authority": s.commanded_authority,
            "service_brake": s.service_break,
            "emergency_brake": s.emergency_brake,
            "doors_left": s.left_doors_open,
            "doors_right": s.right_doors_open,
            "lights_on": s.lights_on,
            "actual_speed_mps": s.actual_speed_mps,
            "accel_mps2": s.acceleration_mps2,
            "power_watts": s.power_watts,
        }