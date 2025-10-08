""" 
 This is the Train Controller Back End.

 Core control logic
 - Accepts commanded speed and authority from CTC
 - Runs a PI controller to track target speed
 - Exposes a "tick(dt)" step used by the UI/Frontend timer
"""

from __future__ import annotations

from dataclasses import dataclass, field

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