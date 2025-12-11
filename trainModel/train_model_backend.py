"""Train Model Backend
"""
import logging
import math
import os
import sys
from datetime import datetime
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.global_clock import clock
from universal.universal import TrainCommand

logger = logging.getLogger(__name__)


class TrainModelBackend:
    """Backend for train physics simulation and state management.
    
    Attributes:
        train_id: String identifier for this train.
        line_name: Name of the line this train operates on.
        velocity: Current velocity in m/s.
        acceleration: Current acceleration in m/s^2.
        position: Current position in meters.
        mass_kg: Total train mass in kilograms.
    """
    
    # Constants (SI units)
    GRAVITY = 9.81  # m/s^2
    AIR_DENSITY = 1.225  # kg/m^3 (sea level)
    DRAG_COEFF = 1.1  # Dimensionless drag coefficient
    FRONTAL_AREA = 3.4 * 2.6  # m^2 (height * width)
    ROLLING_C = 0.0015  # Rolling resistance coefficient
    V_EPS = 0.2  # m/s to avoid P/v blow-up at low speed
    DT_MAX = 0.25  # Clamp large time steps
    MPS_TO_MPH = 2.23694  # Meters per second to miles per hour
    
    # Performance limits
    MAX_ACCEL = 0.8  # m/s^2 traction-limited accel
    MAX_DECEL = -1.2  # m/s^2 service-brake
    MAX_EBRAKE = -2.73  # m/s^2 emergency-brake
    MAX_SPEED = 22.35  # m/s (≈50 mph)
    
    # Passenger boarding
    PASSENGER_MASS_KG = 70.0  # Average weight
    CAPACITY = 272  # Maximum passenger capacity
    
    def __init__(self, line_name: Optional[str] = None) -> None:
        """Initialize train model backend.
        
        Args:
            line_name: Name of the line this train operates on. Defaults to "-".
        """
        self.line_name = line_name or "-"
        self.train_id: str = "T1"
        
        # Physical properties
        self.length_m = 32.2
        self.height_m = 3.4
        self.width_m = 2.6
        self.mass_kg = 40900.0
        self.num_cars: int = 1
        self.crew_count = 2
        self.passenger_count = 200
        
        # Dynamics state
        self.velocity: float = 0.0  # m/s
        self.acceleration: float = 0.0  # m/s^2
        self.position: float = 0.0  # m
        
        # Inputs from testbench
        self.power_kw: float = 0.0  # kW
        self.grade_percent: float = 0.0  # %
        self.authority_m: float = 0.0  # m
        self.commanded_speed: float = 0.0  # m/s
        
        # Device / failures
        self.service_brake: bool = False
        self.emergency_brake: bool = False
        
        # Environment
        self.cabin_lights: bool = False
        self.headlights: bool = False
        self.left_doors: bool = False
        self.right_doors: bool = False
        self.heating: bool = False
        self.air_conditioning: bool = False
        
        # Failures
        self.engine_failure: bool = False
        self.brake_failure: bool = False
        self.signal_pickup_failure: bool = False
        
        self.block_occupied: bool = True
        
        # Cabin environment (Celsius, UI converts to Fahrenheit)
        self.temperature_setpoint: float = 22.0
        self.actual_temperature: float = 22.0
        
        # Misc / I/O
        self.current_announcement: str = ""
        self.beacon_info: str = ""
        self.track_segment: Optional[str] = None
        
        # Observers
        self._listeners: List[Callable[[], None]] = []
        
        # Integrator time bases
        self._last_clock_time: Optional[datetime] = None
        
        # Register with global clock
        clock.register_listener(self._on_clock_tick)
        self._clock_driven: bool = True
        self.time: datetime = datetime(2000, 1, 1, 0, 0, 0)
    
    def _on_clock_tick(self, now: datetime) -> None:
        """Clock listener callback for time synchronization.
        
        Args:
            now: Current simulation time from global clock.
        """
        self.time = now
        
        if self._last_clock_time is None:
            self._last_clock_time = now
            return
        
        dt_s = (now - self._last_clock_time).total_seconds()
        self._last_clock_time = now
        
        # Substep big dt in chunks of DT_MAX to keep physics stable
        remaining = max(0.0, float(dt_s))
        while remaining > 1e-6:
            step = min(self.DT_MAX, remaining)
            self._step_dt(step)
            remaining -= step
        
        self._notify_listeners()
    
    def add_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback to be notified of state changes.
        
        Args:
            callback: Function to call when state changes.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)
    
    def _notify_listeners(self) -> None:
        """Notify all registered listeners of state changes."""
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener raised an exception")
    
    def set_inputs(
        self,
        power_kw: float = None,
        service_brake: bool = None,
        emergency_brake: bool = None,
        grade_percent: float = None,
        beacon_info: str = None,
        commanded_speed_mph: float = None,
        authority_yd: float = None,
        temperature_setpoint_f: float = None,
        announcement: str = None,
        **kwargs
    ) -> None:
        """Update train control inputs.
        
        Args:
            power_kw: Engine power in kilowatts.
            service_brake: Service brake engaged flag.
            emergency_brake: Emergency brake engaged flag.
            grade_percent: Track grade as percentage.
            beacon_info: Beacon data string.
            commanded_speed_mph: Commanded speed in mph.
            authority_yd: Movement authority in yards.
            temperature_setpoint_f: Cabin temperature setpoint in Fahrenheit.
            announcement: Current announcement text.
            **kwargs: Additional toggles (cabin_lights, headlights, doors, etc).
        """
        if power_kw is not None:
            self.power_kw = max(0.0, float(power_kw))
        if service_brake is not None:
            self.service_brake = bool(service_brake)
        if emergency_brake is not None:
            self.emergency_brake = bool(emergency_brake)
        if grade_percent is not None:
            self.grade_percent = float(grade_percent)
        if beacon_info is not None:
            self.beacon_info = str(beacon_info)
        if commanded_speed_mph is not None:
            self.commanded_speed = float(commanded_speed_mph) / self.MPS_TO_MPH
        if authority_yd is not None:
            self.authority_m = float(authority_yd) * 0.9144  # yd to m
        if temperature_setpoint_f is not None:
            temp_c = (float(temperature_setpoint_f) - 32.0) * 5.0 / 9.0
            self.temperature_setpoint = temp_c
            logger.info(
                "Temperature setpoint updated: %.1f°F = %.1f°C",
                temperature_setpoint_f,
                self.temperature_setpoint
            )
        if announcement is not None:
            self.current_announcement = str(announcement)
        
        # Toggles
        toggle_names = (
            "cabin_lights", "headlights", "left_doors", "right_doors",
            "heating", "air_conditioning"
        )
        for name in toggle_names:
            if name in kwargs:
                setattr(self, name, bool(kwargs[name]))
        
        self._notify_listeners()
    
    def _step_dt(self, dt: float) -> None:
        """Advance physics simulation by dt seconds.
        
        Args:
            dt: Time step in seconds.
        """
        if dt <= 0.0:
            return
        
        # Compute mass
        passenger_mass = self.passenger_count * self.PASSENGER_MASS_KG
        mass = max(1.0, (self.mass_kg * self.num_cars) + passenger_mass)
        v_old = self.velocity
        
        if (self.engine_failure or self.signal_pickup_failure or
            self.brake_failure):
            self.emergency_brake = True
            logger.warning("FAILURE DETECTED - Emergency brake activated!")
        
        # Tractive force from power
        if self.engine_failure:
            power_w = 0.0
        else:
            power_w = max(0.0, self.power_kw) * 1000.0
        
        v_eff = max(self.V_EPS, abs(v_old))
        f_tractive = power_w / v_eff  # N
        
        # Traction-limit accel
        f_tractive = min(f_tractive, mass * self.MAX_ACCEL)
        
        # If brakes applied, engine power shouldn't accelerate the train
        if self.service_brake or self.emergency_brake:
            f_tractive = 0.0
        
        # Resistive forces
        f_grade = mass * self.GRAVITY * (self.grade_percent / 100.0)
        f_drag = (0.5 * self.AIR_DENSITY * self.FRONTAL_AREA *
                  self.DRAG_COEFF * v_old * abs(v_old))
        f_roll = self.ROLLING_C * mass * self.GRAVITY
        
        resist = f_drag + f_roll + f_grade
        
        # Net force / base acceleration
        a_base = (f_tractive - resist) / mass  # m/s^2
        
        # Braking caps
        if self.emergency_brake:
            a_target = min(self.MAX_EBRAKE, a_base)
        elif self.service_brake:
            a_target = min(self.MAX_DECEL, a_base)
        else:
            a_target = max(-10.0, min(self.MAX_ACCEL, a_base))
        
        if (not self.emergency_brake and not self.service_brake and
            self.authority_m > 0.0):
            service_a = abs(self.MAX_DECEL)
            if service_a > 0.0:
                stopping_dist = (v_old ** 2) / (2.0 * service_a)
                if self.authority_m <= stopping_dist and v_old > 0.1:
                    a_target = min(a_target, self.MAX_DECEL)
        
        # Integrate (semi-implicit / Euler)
        v_new = v_old + a_target * dt
        if v_new < 0.0:
            v_new = 0.0
            a_target = 0.0
        
        # Position integrates velocity
        self.position += 0.5 * (v_old + v_new) * dt
        
        # Authority decreases as distance is consumed
        self.authority_m = max(0.0, self.authority_m - 0.5 * (v_old + v_new) * dt)
        
        # Commit
        self.velocity = v_new
        self.acceleration = a_target
        self.block_occupied = self.velocity > 0.01
        
        # Cabin temperature update
        if dt > 0.0:
            temp_diff = self.temperature_setpoint - self.actual_temperature
            
            if abs(temp_diff) > 0.1:
                base_rate = 0.05 / 60.0  # 0.05°C per minute
                hvac_rate = 0.5 / 60.0  # 0.5°C per minute
                
                if temp_diff > 0:  # Need to heat
                    rate = hvac_rate if self.heating else base_rate
                    d_t = min(rate * dt, temp_diff)
                else:  # Need to cool
                    rate = hvac_rate if self.air_conditioning else base_rate
                    d_t = max(-rate * dt, temp_diff)
                
                self.actual_temperature += d_t
                
                # Debug log
                if abs(temp_diff) > 0.2:
                    logger.debug(
                        "Temp control: setpoint=%.1f°C, actual=%.1f°C, "
                        "heating=%s, AC=%s",
                        self.temperature_setpoint,
                        self.actual_temperature,
                        self.heating,
                        self.air_conditioning
                    )
    
    def board_passengers(self, n: int) -> int:
        """Increase passengers up to capacity.
        
        Args:
            n: Number of passengers attempting to board.
            
        Returns:
            Number of passengers actually boarded.
        """
        n = max(0, int(n))
        room = max(0, self.CAPACITY - int(self.passenger_count))
        boarded = min(room, n)
        self.passenger_count += boarded
        self._notify_listeners()
        return boarded
    
    def alight_passengers(self, n: int) -> int:
        """Decrease passengers.
        
        Args:
            n: Number of passengers attempting to exit.
            
        Returns:
            Number of passengers actually exited.
        """
        n = max(0, int(n))
        exited = min(n, int(self.passenger_count))
        self.passenger_count -= exited
        self._notify_listeners()
        return exited
    
    def set_failure_state(self, failure_type: str, state: bool) -> None:
        """Set failure state for a specific system.
        
        Args:
            failure_type: Type of failure ("engine", "brake", or "signal").
            state: True to enable failure, False to clear.
        """
        if failure_type == "engine":
            self.engine_failure = bool(state)
            if state:
                self.emergency_brake = True
        elif failure_type == "brake":
            self.brake_failure = bool(state)
            if state:
                self.emergency_brake = True
        elif failure_type == "signal":
            self.signal_pickup_failure = bool(state)
            if state:
                self.emergency_brake = True
        else:
            logger.error("Invalid failure type: %s", failure_type)
            return
        logger.warning("Failure state changed: %s=%s", failure_type, state)
        self._notify_listeners()
    
    def report_state(self) -> Dict[str, object]:
        """Get complete train state as dictionary.
        
        Returns:
            Dictionary containing all train state variables.
        """
        return {
            # Dynamics
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "power_kw": self.power_kw,
            "grade": self.grade_percent,
            "authority": self.authority_m,
            "position": self.position,
            "commanded_speed": self.commanded_speed,
            
            # Static / physical
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "mass_kg": self.mass_kg,
            "crew_count": self.crew_count,
            "passenger_count": self.passenger_count,
            
            # Misc / status
            "beacon": self.beacon_info,
            "track_segment": self.track_segment,
            "service_brake": self.service_brake,
            "emergency_brake": self.emergency_brake,
            "engine_failure": self.engine_failure,
            "brake_failure": self.brake_failure,
            "signal_pickup_failure": self.signal_pickup_failure,
            "block_occupied": self.block_occupied,
            "train_id": getattr(self, "train_id", "T1"),
            "line_name": getattr(self, "line_name", "-"),
            
            # Cabin
            "actual_temperature_c": self.actual_temperature,
            "temperature_setpoint_c": self.temperature_setpoint,
            "current_announcement": self.current_announcement,
            "cabin_lights": self.cabin_lights,
            "headlights": self.headlights,
            "left_doors": self.left_doors,
            "right_doors": self.right_doors,
            "heating": self.heating,
            "air_conditioning": self.air_conditioning,
        }
    
    def set_time(self, new_time: datetime) -> None:
        """Set simulation time manually.
        
        Note: Does not advance physics; _on_clock_tick handles stepping.
        
        Args:
            new_time: New simulation time.
        """
        self.time = new_time
        self._notify_listeners()
    
    def manual_set_time(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        second: int,
    ) -> None:
        """Manually override simulation time.
        
        Args:
            year: Year component.
            month: Month component.
            day: Day component.
            hour: Hour component.
            minute: Minute component.
            second: Second component.
        """
        self.time = datetime(year, month, day, hour, minute, second)
        logger.info(
            "%s: Time manually set to %s",
            getattr(self, "line_name", "TrainModel"),
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._notify_listeners()


class Train:
    """Train wrapper that binds TrainModelBackend to Track Network.
    
    Attributes:
        train_id: Integer identifier for this train.
        tm: TrainModelBackend instance handling physics.
        network: Reference to Track Network.
        current_segment: Current track segment the train occupies.
        segment_displacement_m: Position within current segment in meters.
    """
    
    def __init__(
        self,
        train_id: int,
        backend: Optional["TrainModelBackend"] = None
    ) -> None:
        """Initialize train wrapper.
        
        Args:
            train_id: Unique identifier for this train.
            backend: TrainModelBackend instance. Creates new if None.
        """
        self.train_id = train_id
        self.tm = backend if backend is not None else TrainModelBackend()
        self.tm.train_id = self.train_id
        
        self.network: Optional[object] = None
        self.current_segment: Optional[object] = None
        self.segment_displacement_m: float = 0.0
        
        self._prev_left_doors = False
        self._prev_right_doors = False
        
        clock.register_listener(self._auto_tick)
        self._last_tick_time: Optional[datetime] = None
    
    def _auto_tick(self, current_time: datetime) -> None:
        """Automatic tick called by global clock.
        
        Pulls commands from Track Model and runs physics simulation.
        
        Args:
            current_time: Current simulation time from global clock.
        """
        if self._last_tick_time is None:
            self._last_tick_time = current_time
            return
        
        dt_s = (current_time - self._last_tick_time).total_seconds()
        self._last_tick_time = current_time
        
        if dt_s <= 0.0:
            return
        
        # Pull track inputs (grade, beacon, speed limit)
        trk = self._pull_track_inputs()
        
        if (self.current_segment and
            hasattr(self.current_segment, 'active_command')):
            cmd = self.current_segment.active_command
            if cmd:
                spd = getattr(cmd, "commanded_speed", None)
                auth = getattr(cmd, "authority", None)
                
                if spd is not None:
                    self.tm.commanded_speed = max(0.0, float(spd))
                if auth is not None:
                    self.tm.authority_m = max(0.0, float(auth))
        
        self.tm.set_inputs(
            power_kw=self.tm.power_kw,
            service_brake=self.tm.service_brake,
            emergency_brake=self.tm.emergency_brake,
            grade_percent=float(trk["grade_percent"]),
            beacon_info=trk["beacon_info"],
        )
        
        try:
            limit = float(trk["speed_limit_mps"])
            if self.tm.velocity > limit:
                self.tm.velocity = limit
        except Exception:
            pass
        
        # Move
        if dt_s > 0.0:
            distance = float(self.tm.velocity) * float(dt_s)
            self._advance_along_track(distance)
    
    def _next_segment(self):
        """Get next segment in track topology.
        
        Returns:
            Next track segment or None if at end of line.
        """
        if self.current_segment is None:
            return None
        return self.current_segment.get_next_segment()
    
    def _prev_segment(self):
        """Get previous segment in track topology.
        
        Returns:
            Previous track segment or None if at start of line.
        """
        if self.current_segment is None:
            return None
        return self.current_segment.get_previous_segment()
    
    @staticmethod
    def _is_red(seg) -> bool:
        """Check if segment signal is red.
        
        Args:
            seg: Track segment to check.
            
        Returns:
            True if signal is red, False otherwise.
        """
        st = getattr(seg, "signal_state", None)
        val = getattr(st, "value", st)
        name = getattr(st, "name", None)
        s = str(val or name or st).lower()
        return "red" in s
    
    def _sync_backend_track_segment(self) -> None:
        """Send segment label to backend for UI display."""
        try:
            block_id = getattr(self.current_segment, "block_id", None)
            if block_id is not None:
                label = block_id
            else:
                label = getattr(self.current_segment, "name", "-")
            self.tm.track_segment = str(label)
        except Exception:
            self.tm.track_segment = "-"
    
    def _network_set_location(
        self,
        block_id: int,
        displacement_m: float
    ) -> bool:
        """Tell TrackNetwork that train moved to new location.
        
        Args:
            block_id: ID of block train is moving to.
            displacement_m: Position within block in meters.
            
        Returns:
            True on success, False if network cannot be updated.
        """
        if not self.network:
            return False
        
        try:
            self.network.connect_train(
                self.train_id,
                int(block_id),
                float(displacement_m)
            )
            return True
        except Exception:
            logging.exception(
                "Failed to update network location for train %s -> "
                "block %s, disp %.2f",
                self.train_id,
                block_id,
                displacement_m
            )
            return False
    
    def _pull_track_inputs(self) -> dict:
        """Sync inputs from track to send to physics.
        
        Returns:
            Dictionary containing grade_percent, beacon_info, speed_limit_mps.
        """
        if self.current_segment is None:
            return {
                "grade_percent": 0.0,
                "beacon_info": "None",
                "speed_limit_mps": float(self.tm.MAX_SPEED)
            }
        
        seg = self.current_segment
        speed_limit_mps = float(getattr(seg, "speed_limit", self.tm.MAX_SPEED))
        grade_percent = float(getattr(seg, "grade", 0.0))
        beacon_raw = getattr(seg, "beacon_data", "")
        beacon_info = str(beacon_raw) if beacon_raw else "None"
        return {
            "grade_percent": grade_percent,
            "beacon_info": beacon_info,
            "speed_limit_mps": speed_limit_mps
        }
    
    def mto(self, distance_m: float) -> bool:
        """Externally move train by distance (bypass physics).
        
        Args:
            distance_m: Distance to move in meters.
            
        Returns:
            True if moved, False if blocked.
        """
        return self._advance_along_track(float(distance_m))
    
    def _advance_along_track(self, distance_m: float) -> bool:
        """Move train by distance and update network.
        
        Toggles block occupancy on segment objects.
        
        Args:
            distance_m: Distance to move in meters (can be negative).
            
        Returns:
            True if moved, False if blocked.
        """
        if (self.current_segment is None or self.network is None or
            distance_m == 0.0):
            return False
        
        seg = self.current_segment
        seg_len = float(getattr(seg, "length", 0.0))
        pos = self.segment_displacement_m
        new_pos = pos + float(distance_m)
        
        def _set_occ(segment, occ: bool) -> None:
            """Helper to set segment occupancy."""
            try:
                if hasattr(segment, "set_occupancy"):
                    segment.set_occupancy(bool(occ))
                elif hasattr(segment, "occupied"):
                    segment.occupied = bool(occ)
            except Exception:
                logger.exception(
                    "Failed to set occupancy=%s for segment %r",
                    occ,
                    segment
                )
        
        # Moving backwards
        if new_pos < 0.0:
            prev_seg = self._prev_segment()
            if (prev_seg is None or getattr(prev_seg, "closed", False) or
                self._is_red(prev_seg)):
                self.segment_displacement_m = 0.0
                return False
            
            prev_len = float(getattr(prev_seg, "length", 0.0))
            new_disp = max(0.0, new_pos + prev_len)
            
            # Clear occupancy from current segment before updating network
            _set_occ(self.current_segment, False)
            
            # Tell network first; if it fails, revert
            ok = self._network_set_location(
                getattr(prev_seg, "block_id", getattr(prev_seg, "id", -1)),
                new_disp,
            )
            if not ok:
                _set_occ(self.current_segment, True)
                return False
            
            # Toggle occupancies
            _set_occ(prev_seg, True)
            
            self.current_segment = prev_seg
            self.segment_displacement_m = new_disp
            self._sync_backend_track_segment()
            logger.debug(
                "Train %s moved backwards to block %s",
                self.train_id,
                prev_seg.block_id
            )
            return True
        
        # Moving forwards
        if new_pos > seg_len:
            next_seg = self._next_segment()
            if next_seg is None:
                self.segment_displacement_m = seg_len
                return False
            
            next_len = float(getattr(next_seg, "length", 0.0))
            new_disp = min(next_len, new_pos - seg_len)
            
            _set_occ(self.current_segment, False)
            _set_occ(next_seg, True)
            
            self.current_segment = next_seg
            self.segment_displacement_m = new_disp
            self._sync_backend_track_segment()
            logger.debug(
                "Train %s moved forward to block %s",
                self.train_id,
                next_seg.block_id
            )
            return True
        
        # Still inside this block
        self.segment_displacement_m = new_pos
        _set_occ(seg, True)
        return True
    
    def _check_door_events(self) -> None:
        """Detect door opening events and handle passenger exits."""
        left_opened = self.tm.left_doors and not self._prev_left_doors
        right_opened = self.tm.right_doors and not self._prev_right_doors
        
        if left_opened or right_opened:
            if self.tm.passenger_count > 0:
                # 30% of passengers exiting at each stop
                exit_count = max(1, int(self.tm.passenger_count * 0.3))
                exited = self.tm.alight_passengers(exit_count)
                
                # Report back to Track Model
                if self.network and hasattr(self.network, 'passengers_exiting'):
                    try:
                        block_id = getattr(self.current_segment, 'block_id', None)
                        if block_id is not None:
                            self.network.passengers_exiting(
                                block_id,
                                self.train_id,
                                exited
                            )
                            logger.info(
                                "Train %s: %s passengers exited at block %s",
                                self.train_id,
                                exited,
                                block_id
                            )
                    except Exception as e:
                        logger.warning(
                            "Failed to report passenger exits to Track Model: %s",
                            e
                        )
        
        # Update previous door states
        self._prev_left_doors = self.tm.left_doors
        self._prev_right_doors = self.tm.right_doors

    def report_state(self) -> dict:
        """Get complete train state as dictionary.
        
        Returns:
            Dictionary containing all train state variables.
        """
        s = self.tm.report_state()
        s.update({
            "train_id": self.train_id,
            "track_block_id": (
                None if self.current_segment is None
                else getattr(self.current_segment, "block_id", None)
            ),
            "inblock_displacement_m": self.segment_displacement_m,
        })
        return s
    
    def board_passengers(self, n: int) -> int:
        """TrackModel calls this at stations to add riders.
        
        Args:
            n: Number of passengers attempting to board.
            
        Returns:
            Number of passengers actually boarded.
        """
        return self.tm.board_passengers(n)
    
    def alight_passengers(self, n: int) -> int:
        """Remove passengers and report to Track Model.
        
        Args:
            n: Number of passengers attempting to exit.
            
        Returns:
            Number of passengers actually exited.
        """
        exited = self.tm.alight_passengers(n)
        
        # Report to Track Model when passengers exit
        if exited > 0 and self.network and hasattr(self.network, 'passengers_exiting'):
            try:
                block_id = getattr(self.current_segment, 'block_id', None)
                if block_id is not None:
                    self.network.passengers_exiting(
                        block_id,
                        self.train_id,
                        exited
                    )
                    logger.info(
                        "Train %s: %s passengers exited at block %s",
                        self.train_id,
                        exited,
                        block_id
                    )
            except Exception as e:
                logger.warning(
                    "Failed to report passenger exits to Track Model: %s",
                    e
                )
        
        return exited
    
    def train_command_interrupt(self, block_id: int) -> None:
        """Called by TrackModel when new train command is available.
        
        Args:
            block_id: Block ID where command is available.
        """
        if (self.current_segment and
            self.current_segment.block_id == block_id):
            self.apply_train_command(self.current_segment.active_command)
    
    def apply_train_command(self, active_command: TrainCommand) -> None:
        """Apply train command from Track Model.
        
        Args:
            active_command: TrainCommand object with speed and authority.
        """
        spd = getattr(active_command, "commanded_speed", None)
        if spd is not None:
            self.tm.commanded_speed = max(0.0, float(spd))
        
        auth = getattr(active_command, "authority", None)
        if auth is not None:
            self.tm.authority_m = max(0.0, float(auth))
        
        logger.debug(
            "Train %s applied command: speed=%.2f m/s, authority=%.1f m",
            self.train_id,
            spd,
            auth
        )