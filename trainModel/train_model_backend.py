"""
train_model_backend.py
"""

from __future__ import annotations
import logging
from typing import Callable, List, Dict

#debug visibility
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


class TrainModelBackend:
    """
    backend simulation for a single train
    """

    def __init__(self) -> None:
        """initialize simulation variables"""
        # train parameters 
        # in SI units    
        self.length_m = 32.2     
        self.height_m = 3.4        
        self.width_m = 2.6        
        self.mass_kg = 40900.0    
        self.crew_count = 2                    # typical crew (driver + conductor)
        self.passenger_count = 200             # default passengers (change via Test UI)
        self.num_cars: int = 1                 # number of cars
        self.max_accel: float = 0.5           
        self.max_decel: float = -1.2         
        self.max_emergency_decel: float = -2.73  
        self.max_speed: float = 22.35          # 50 mph in m/s

        # dynamic state variables
        self.velocity: float = 0.0            
        self.acceleration: float = 0.0         
        self.position: float = 0.0             # m (distance traveled)
        self.power_kw: float = 0.0             
        self.grade_percent: float = 0.0        # track slope
        self.authority_m: float = 500.0       
        self.commanded_speed: float = 0.0      # target from Track Controller

        # boolean states
        self.service_brake: bool = False
        self.emergency_brake: bool = False
        self.engine_failure: bool = False
        self.brake_failure: bool = False
        self.signal_pickup_failure: bool = False
        self.block_occupied: bool = True

        # beacon data
        self.beacon_info: str = "None"

        # observers (UI)
        self._listeners: List[Callable[[], None]] = []


    # LISTENER SYSTEM
    """
    whenever the backend updates data, the UI should refresh automatically
    """
    def add_listener(self, callback: Callable[[], None]) -> None:
        """register a listener (UI refresh callback)."""
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug("Listener added: %r", callback)

    def _notify_listeners(self) -> None:
        """invoke all registered listeners."""
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.exception("Listener raised an exception")

  
    # CORE UPDATE METHODS
    def set_inputs(self, power_kw: float, service_brake: bool,
                   emergency_brake: bool, grade_percent: float,
                   beacon_info: str = "None") -> None:
        """
        update all control inputs (called by Test UI).
        Args:
            power_kw: Power command (kW)
            service_brake: Whether service brake is applied
            emergency_brake: Whether emergency brake is applied
            grade_percent: Track slope
            beacon_info: Info from Track Model beacon
        """
        self.power_kw = max(0.0, power_kw)  # power cannot be negative
        self.service_brake = service_brake
        self.emergency_brake = emergency_brake
        self.grade_percent = grade_percent
        self.beacon_info = beacon_info

        #perform one simulation step after updating inputs
        self._simulate_step()
        self._notify_listeners()

    # ------------------------------------------------------------------
    def _simulate_step(self) -> None:
        """
        compute new velocity and acceleration based on power, mass, grade,
        and brakes. enforces limits and failure modes.
        """
        # if engine failure → ignore power input
        if self.engine_failure:
            effective_power = 0.0
        else:
            effective_power = self.power_kw

        # convert to watts
        power_w = effective_power * 1000.0
        total_mass = self.mass_kg * self.num_cars

        # newtonian calculation: P = F * v  ⇒  a = (P / (m * v))
        # handle the case where velocity is 0 (avoid divide by zero)
        if self.velocity > 0.1:
            acceleration = power_w / (total_mass * self.velocity)
        else:
            # approximate startup acceleration at low speed
            acceleration = min(self.max_accel, power_w / (total_mass * 0.1))

        # add grade effect (positive grade = uphill, reduces accel)
        grade_accel = -9.81 * (self.grade_percent / 100.0)
        acceleration += grade_accel

        # handle braking conditions
        if self.service_brake and not self.brake_failure:
            acceleration = self.max_decel
        if self.emergency_brake:
            acceleration = self.max_emergency_decel

        # limit acceleration to bounds
        self.acceleration = max(self.max_emergency_decel,
                                min(acceleration, self.max_accel))

        # update velocity
        self.velocity += self.acceleration
        if self.velocity < 0:
            self.velocity = 0
        if self.velocity > self.max_speed:
            self.velocity = self.max_speed

        # update position and authority
        self.position += self.velocity
        self.authority_m = max(0.0, self.authority_m - self.velocity)

        # check for end of authority
        if self.authority_m <= 0:
            # force stop if exceeded
            self.velocity = 0.0
            self.acceleration = 0.0
            logger.warning("Authority limit reached. Train stopped.")

        # update occupancy based on velocity
        self.block_occupied = self.velocity > 0

        logger.info(
            f"v={self.velocity:.2f} m/s, a={self.acceleration:.2f} m/s², "
            f"auth={self.authority_m:.1f} m, brake={self.service_brake}, "
            f"EB={self.emergency_brake}, P={self.power_kw:.1f} kW"
        )

    # FAILURE HANDLING
    def set_failure_state(self, failure_type: str, state: bool) -> None:
        """
        toggle failure modes (used by Murphy/Test UI)
        failure_type: 'engine', 'brake', 'signal'
        """
        if failure_type == "engine":
            self.engine_failure = state
        elif failure_type == "brake":
            self.brake_failure = state
        elif failure_type == "signal":
            self.signal_pickup_failure = state
        else:
            logger.error("Invalid failure type: %s", failure_type)
            return

        logger.warning("Failure state changed: %s=%s", failure_type, state)
        self._notify_listeners()

    # REPORTING
    # REPORTING
    def report_state(self) -> Dict[str, object]:
        """
        Returns a dictionary of all train state variables for UI display.
        """
        return {
            # dynamics
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "power_kw": self.power_kw,
            "grade": self.grade_percent,
            "authority": self.authority_m,

            # static / physical
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "mass_kg": self.mass_kg,
            "crew_count": self.crew_count,
            "passenger_count": self.passenger_count,

            # “suggested speed”
            "commanded_speed": self.commanded_speed,

            # track segment placeholder (integrate with actual track info later )
            "track_segment": getattr(self, "track_segment", "c13"),

            # misc
            "beacon": self.beacon_info,
            "service_brake": self.service_brake,
            "emergency_brake": self.emergency_brake,
            "engine_failure": self.engine_failure,
            "brake_failure": self.brake_failure,
            "signal_pickup_failure": self.signal_pickup_failure,
            "block_occupied": self.block_occupied,
        }


