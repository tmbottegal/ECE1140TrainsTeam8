import time
import sys
import os
import logging
from typing import Callable, List, Dict, Optional
import math
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.global_clock import clock 
from universal.universal import TrainCommand

logger = logging.getLogger(__name__)

class TrainModelBackend:
    # constants (SI)
    GRAVITY = 9.81            # m/s^2
    AIR_DENSITY = 1.225       # kg/m^3 (sea level)
    DRAG_COEFF = 1.1          # rough; adjust as needed
    FRONTAL_AREA = 3.4 * 2.6  # m^2 (height * width)
    ROLLING_C = 0.0015        # rolling resistance coeff (small, optional)
    V_EPS = 0.2               # m/s to avoid P/v blow-up at low speed
    DT_MAX = 0.25             # clamp large time steps
    MPS_TO_MPH  = 2.23694
    
    # performance limits
    MAX_ACCEL = 0.8           # m/s^2 traction-limited accel
    MAX_DECEL = -1.2          # m/s^2 service-brake
    MAX_EBRAKE = -2.73        # m/s^2 emergency-brake
    MAX_SPEED = 22.35         # m/s (≈50 mph)

    # passenger boarding
    PASSENGER_MASS_KG = 70.0  #avg weight
    CAPACITY = 272

    def __init__(self, line_name: str | None = None) -> None:
        self.line_name = line_name or "-"
        self.train_id: str = "T1"

        # physical properties 
        self.length_m = 32.2
        self.height_m = 3.4
        self.width_m = 2.6
        self.mass_kg = 40900.0
        self.num_cars: int = 1
        self.crew_count = 2
        self.passenger_count = 200

        # dynamics state
        self.velocity: float = 0.0      # m/s
        self.acceleration: float = 0.0  # m/s^2
        self.position: float = 0.0      # m

        # inputs from testbench
        self.power_kw: float = 0.0      # kW
        self.grade_percent: float = 0.0 # %
        self.authority_m: float = 0.0 # m
        self.commanded_speed: float = 0.0  # m/s 
        # device / failures
        self.service_brake: bool = False
        self.emergency_brake: bool = False
        # environment
        self.cabin_lights: bool = False
        self.headlights: bool = False
        self.left_doors: bool = False  
        self.right_doors: bool = False
        self.heating: bool = False
        self.air_conditioning: bool = False

        # device / failures
        self.engine_failure: bool = False
        self.brake_failure: bool = False
        self.signal_pickup_failure: bool = False

        self.block_occupied: bool = True

        # cabin environment (C, then UI converts to F)
        self.temperature_setpoint: float = 22.0
        self.actual_temperature: float = 22.0

        # misc / I/O
        self.current_announcement: str = "" 
        self.beacon_info: str = ""
        self.track_segment: Optional[str] = None  # filled by Train._sync_backend_track_segment()

        # observers
        self._listeners: List[Callable[[], None]] = []

        # integrator time bases
        self._last_clock_time: Optional[datetime] = None      # global clock stepping

        # register with global clock
        clock.register_listener(self._on_clock_tick)
        self._clock_driven: bool = True  # registered to global clock; suppress local stepping
        self.time: datetime = datetime(2000, 1, 1, 0, 0, 0)

    # ------------------------------------------------------------------
    # clock listener
    def _on_clock_tick(self, now: datetime) -> None:
        # keep local time in sync with global clock
        self.time = now

        if self._last_clock_time is None:
            self._last_clock_time = now
            return

        dt_s = (now - self._last_clock_time).total_seconds()
        self._last_clock_time = now

        # substep big dt in chunks of DT_MAX to keep physics stable
        remaining = max(0.0, float(dt_s))
        while remaining > 1e-6:
            step = min(self.DT_MAX, remaining)
            self._step_dt(step)
            remaining -= step

        self._notify_listeners()


    # ------------------------------------------------------------------
    # listeners
    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener raised an exception")

    # ------------------------------------------------------------------
    # inputs
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
            self.temperature_setpoint = (float(temperature_setpoint_f) - 32.0) * 5.0 / 9.0
            logger.info(f"Temperature setpoint updated: {temperature_setpoint_f:.1f}°F = {self.temperature_setpoint:.1f}°C")
        if announcement is not None:
            self.current_announcement = str(announcement)
            
        # toggles
        for name in ("cabin_lights", "headlights", "left_doors", "right_doors",
                     "heating", "air_conditioning"):
            if name in kwargs:
                setattr(self, name, bool(kwargs[name]))
                
        self._notify_listeners()

    # ------------------------------------------------------------------
    def _step_dt(self, dt: float) -> None:
        """advance physics by provided dt (seconds)"""
        if dt <= 0.0:
            return

         # compute once
        mass = max(1.0, (self.mass_kg * self.num_cars) + self.passenger_count * self.PASSENGER_MASS_KG)
        v_old = self.velocity

        if self.engine_failure or self.signal_pickup_failure or self.brake_failure:
            self.emergency_brake = True
            logger.warning("FAILURE DETECTED - Emergency brake activated!")

        # tractive force from power
        if self.engine_failure:
            power_w = 0.0
        else:
            power_w = max(0.0, self.power_kw) * 1000.0

        v_eff = max(self.V_EPS, abs(v_old))  # avoid blow-up at low speed
        F_tractive = power_w / v_eff  # N

        # traction-limit accel
        F_tractive = min(F_tractive, mass * self.MAX_ACCEL)

        # if brakes applied, engine power shouldn’t accelerate the train
        if self.service_brake or self.emergency_brake:
            F_tractive = 0.0

        # resistive forces 
        # gravity along grade: F = m g (grade/100) (sign opposes uphill motion)
        F_grade = mass * self.GRAVITY * (self.grade_percent / 100.0)

        # air drag (quadratic): 0.5 rho A Cd v^2 (opposes motion)
        F_drag = 0.5 * self.AIR_DENSITY * self.FRONTAL_AREA * self.DRAG_COEFF * v_old * abs(v_old)

        # rolling resistance (rough, always opposing motion)
        F_roll = self.ROLLING_C * mass * self.GRAVITY

        resist = F_drag + F_roll + F_grade

        # net force / base acceleration
        a_base = (F_tractive - resist) / mass  # m/s^2

        # braking caps (still affected by grade via a_base)
        if self.emergency_brake:
            a_target = min(self.MAX_EBRAKE, a_base)
        elif self.service_brake:
            a_target = min(self.MAX_DECEL, a_base)
        else:
            a_target = max(-10.0, min(self.MAX_ACCEL, a_base))  # clamp absurd values

        if (
            not self.emergency_brake
            and not self.service_brake
            and self.authority_m > 0.0
        ):
            # approximate stopping distance using service-brake decel
            service_a = abs(self.MAX_DECEL)
            if service_a > 0.0:
                stopping_dist = (v_old ** 2) / (2.0 * service_a)  # d = v^2 / (2a)
                if self.authority_m <= stopping_dist and v_old > 0.1:
                    # begin service braking
                    a_target = min(a_target, self.MAX_DECEL)

        # integrate (semi-implicit / Euler ok for small dt)
        v_new = v_old + a_target * dt
        if v_new < 0.0:
            v_new = 0.0
            a_target = 0.0

        # position integrates velocity
        self.position += 0.5 * (v_old + v_new) * dt

        # authority decreases as distance is consumed
        self.authority_m = max(0.0, self.authority_m - 0.5 * (v_old + v_new) * dt)
        """
        # if out of authority, stop train
        if self.authority_m <= 0.0 and v_new > 0.0:
            v_new = 0.0
            a_new = 0.0
            logger.warning("Authority limit reached. Train stopped.")
        """
        # commit
        self.velocity = v_new
        self.acceleration = a_target
        self.block_occupied = self.velocity > 0.01

        # cabin temperature update
        if dt > 0.0:
            temp_diff = self.temperature_setpoint - self.actual_temperature
            
            if abs(temp_diff) > 0.1:
                base_rate = 0.05 / 60.0  # 0.05°C per minute
                
                hvac_rate = 0.5 / 60.0  # 0.5°C per minute
                
                if temp_diff > 0:  # need to heat
                    rate = hvac_rate if self.heating else base_rate
                    dT = min(rate * dt, temp_diff) 
                else:  # need to cool
                    rate = hvac_rate if self.air_conditioning else base_rate
                    dT = max(-rate * dt, temp_diff) 
                
                self.actual_temperature += dT
                
                # debug log
                if abs(temp_diff) > 0.2:
                    logger.debug(
                        f"Temp control: setpoint={self.temperature_setpoint:.1f}°C, "
                        f"actual={self.actual_temperature:.1f}°C, "
                        f"heating={self.heating}, AC={self.air_conditioning}"
                    )

    def board_passengers(self, n: int) -> int:
        """increase passengers up to CAPACITY. Returns actually boarded"""
        n = max(0, int(n)) 
        room = max(0, self.CAPACITY - int(self.passenger_count))
        boarded = min(room, n) 
        self.passenger_count += boarded
        self._notify_listeners()
        return boarded

    def alight_passengers(self, n: int) -> int:
        """decrease passengers. Returns actually exited."""
        n = max(0, int(n))
        exited = min(n, int(self.passenger_count))
        self.passenger_count -= exited
        self._notify_listeners()
        return exited
    
    # ------------------------------------------------------------------
    # failures
    def set_failure_state(self, failure_type: str, state: bool) -> None:
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

    # ------------------------------------------------------------------
    # report
    def report_state(self) -> Dict[str, object]:
        return {
            # dynamics
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "power_kw": self.power_kw,
            "grade": self.grade_percent,
            "authority": self.authority_m,
            "position": self.position,
            "commanded_speed": self.commanded_speed,

            # static / physical
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "mass_kg": self.mass_kg,
            "crew_count": self.crew_count,
            "passenger_count": self.passenger_count,

            # misc / status
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

            # cabin
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
    
    # ------------------------------------------------------------------
    # time (kept in sync with universal.global_clock)
    def set_time(self, new_time: datetime) -> None:
        """
        Called by UI when the global clock ticks
        Does not advance physics; _on_clock_tick handles stepping.
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
        """
        manual override
        """
        self.time = datetime(year, month, day, hour, minute, second)
        logger.info(
            "%s: Time manually set to %s",
            getattr(self, "line_name", "TrainModel"),
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._notify_listeners()


# multi-train wrapper that binds a TrainModelBackend to the Track Network 
class Train:
    def __init__(self, train_id: int, backend: Optional["TrainModelBackend"] = None) -> None:
        self.train_id = train_id
        self.tm = backend if backend is not None else TrainModelBackend()
        self.tm.train_id = self.train_id

        self.network: Optional[object] = None
        self.current_segment: Optional[object] = None
        self.segment_displacement_m: float = 0.0

        clock.register_listener(self._auto_tick)
        self._last_tick_time: Optional[datetime] = None

    def _auto_tick(self, current_time: datetime) -> None:
        """
        called automatically by global clock every tick; pulls commands from Track Model and runs physics
        """
        if self._last_tick_time is None:
            self._last_tick_time = current_time
            return

        dt_s = (current_time - self._last_tick_time).total_seconds()
        self._last_tick_time = current_time

        if dt_s <= 0.0:
            return

        # pull track inputs (grade, beacon, speed limit)
        trk = self._pull_track_inputs()

        if self.current_segment and hasattr(self.current_segment, 'active_command'):
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
        
        # move
        if dt_s > 0.0:
            distance = float(self.tm.velocity) * float(dt_s)
            self._advance_along_track(distance)


    # helpers from track graph
    # what is next
    def _next_segment(self):
        return None if self.current_segment is None else self.current_segment.get_next_segment()

    #what is previous
    def _prev_segment(self):
        return None if self.current_segment is None else self.current_segment.get_previous_segment()

    # signal to stop at "red"
    @staticmethod
    def _is_red(seg) -> bool:
        st = getattr(seg, "signal_state", None)
        val = getattr(st, "value", st)
        name = getattr(st, "name", None)
        s = str(val or name or st).lower()
        return "red" in s
    
    # send label to backend
    def _sync_backend_track_segment(self) -> None:
        try:
            block_id = getattr(self.current_segment, "block_id", None)
            label = block_id if block_id is not None else getattr(self.current_segment, "name", "-")
            self.tm.track_segment = str(label)
        except Exception:
            self.tm.track_segment = "-"


    def _network_set_location(self, block_id: int, displacement_m: float) -> bool:
        """
        tell TrackNetwork that train moved to block_id at displacement_m
        returns T on success, F if the network cannot be updated
        """
        if not self.network:
            return False

        try:
            self.network.connect_train(self.train_id, int(block_id), float(displacement_m))
            return True

        except Exception:
            logging.exception(
                "Failed to update network location for train %s -> block %s, disp %.2f",
                self.train_id, block_id, displacement_m
            )
            return False


    # per-step sync from track to send to physics
    def _pull_track_inputs(self) -> dict:
        if self.current_segment is None:
            return {"grade_percent": 0.0, "beacon_info": "None", "speed_limit_mps": float(self.tm.MAX_SPEED)}

        seg = self.current_segment
        speed_limit_mps = float(getattr(seg, "speed_limit", self.tm.MAX_SPEED))
        grade_percent = float(getattr(seg, "grade", 0.0))
        beacon_raw = getattr(seg, "beacon_data", "")
        beacon_info = str(beacon_raw) if beacon_raw else "None"
        return {"grade_percent": grade_percent, "beacon_info": beacon_info, "speed_limit_mps": speed_limit_mps}

    def mto(self, distance_m: float) -> bool: #DEBUG
        """
        externally move the train by distance_m (bypass physics)
        returns T if moved, F if blocked
        """
        return self._advance_along_track(float(distance_m))
    
    def _advance_along_track(self, distance_m: float) -> bool:      #BUG: #118 edge case: cannot traverse more than one segment at a time
        """
        move by distance_m and ask the network to reflect the new location
        T if moved, F if blocked
        toggles block occupancy on segment objects
        """
        if self.current_segment is None or self.network is None or distance_m == 0.0:
            return False

        seg = self.current_segment # current segment
        seg_len = float(getattr(seg, "length", 0.0)) # segment length 
        pos = self.segment_displacement_m # where i am inside the block
        new_pos = pos + float(distance_m) #updated position

        # helper for occupancy; returns true if occ
        def _set_occ(segment, occ: bool) -> None:
            try:
                if hasattr(segment, "set_occupancy"):
                    segment.set_occupancy(bool(occ))
                elif hasattr(segment, "occupied"):
                    segment.occupied = bool(occ)
            except Exception:
                logger.exception("Failed to set occupancy=%s for segment %r", occ, segment)

        # moving backwards
        if new_pos < 0.0:
            prev_seg = self._prev_segment() # grab whatever is linked before this 
            if prev_seg is None or getattr(prev_seg, "closed", False) or self._is_red(prev_seg):
                # cannot move into previous block
                self.segment_displacement_m = 0.0
                return False

            prev_len = float(getattr(prev_seg, "length", 0.0))
            new_disp = max(0.0, new_pos + prev_len)

            # bug fix: clear occupancy from current segment before updating network
            _set_occ(self.current_segment, False)

            # tell network first; if it fails, revert
            ok = self._network_set_location(
                getattr(prev_seg, "block_id", getattr(prev_seg, "id", -1)),
                new_disp,
            )
            if not ok:
                # revert occupancy
                _set_occ(self.current_segment, True)
                return False

            # toggle occupancies
            _set_occ(prev_seg, True)

            self.current_segment = prev_seg
            self.segment_displacement_m = new_disp
            self._sync_backend_track_segment()
            logger.debug(f"Train {self.train_id} moved backwards to block {prev_seg.block_id}")
            return True

        # moving forwards
        if new_pos > seg_len:
            next_seg = self._next_segment()
            if next_seg is None:
                # end of line, clamp to end of block
                self.segment_displacement_m = seg_len
                # _set_occ(seg, True)
                return False

            next_len = float(getattr(next_seg, "length", 0.0))
            new_disp = min(next_len, new_pos - seg_len)

            _set_occ(self.current_segment, False)
            _set_occ(next_seg, True)

            self.current_segment = next_seg
            self.segment_displacement_m = new_disp
            self._sync_backend_track_segment()
            logger.debug(f"Train {self.train_id} moved forward to block {next_seg.block_id}")
            return True

        # still inside this block
        self.segment_displacement_m = new_pos
        _set_occ(seg, True)  # make sure block stays marked occupied
        return True
    
    # UI/report 
    def report_state(self) -> dict:
        s = self.tm.report_state()
        s.update({
            "train_id": self.train_id,
            "track_block_id": None if self.current_segment is None else getattr(self.current_segment, "block_id", None),
            "inblock_displacement_m": self.segment_displacement_m,
        })
        return s

    def _check_door_events(self) -> None:
        # detect door opening events
        left_opened = self.tm.left_doors and not self._prev_left_doors
        right_opened = self.tm.right_doors and not self._prev_right_doors

        if left_opened or right_opened:
            # doors just opened, calculate passengers exiting
            if self.tm.passenger_count > 0:
                # 30% of passengers exiting at each stop
                exit_count = max(1, int(self.tm.passenger_count * 0.3))
                exited = self.tm.alight_passengers(exit_count)
                
                # report back to Track Model
                if self.network and hasattr(self.network, 'passengers_exiting'):
                    try:
                        block_id = getattr(self.current_segment, 'block_id', None)
                        if block_id is not None:
                            self.network.passengers_exiting(block_id, self.train_id, exited)
                            logger.info(f"Train {self.train_id}: {exited} passengers exited at block {block_id}")
                    except Exception as e:
                        logger.warning(f"Failed to report passenger exits to Track Model: {e}")

        # update previous door states
        self._prev_left_doors = self.tm.left_doors
        self._prev_right_doors = self.tm.right_doors
        s = self.tm.report_state()
        s.update({
            "train_id": self.train_id,
            "track_block_id": None if self.current_segment is None else getattr(self.current_segment, "block_id", None),
            "inblock_displacement_m": self.segment_displacement_m,
        })
        return s
    
    # public passenger APIs the Track Model can call
    def board_passengers(self, n: int) -> int:
        """TrackModel calls this at stations to add riders"""
        return self.tm.board_passengers(n)

    def alight_passengers(self, n: int) -> int:
        exited = self.tm.alight_passengers(n)
        
        # report to Track Model when passengers exit
        if exited > 0 and self.network and hasattr(self.network, 'passengers_exiting'):
            try:
                block_id = getattr(self.current_segment, 'block_id', None)
                if block_id is not None:
                    self.network.passengers_exiting(block_id, self.train_id, exited)
                    logger.info(f"Train {self.train_id}: {exited} passengers exited at block {block_id}")
            except Exception as e:
                logger.warning(f"Failed to report passenger exits to Track Model: {e}")
        
        return exited
    
    def train_command_interrupt(self, block_id: int) -> None:
        """
        called by TrackModel when a new train command is available
        """
        if block_id is self.current_segment.block_id:
            self.apply_train_command(self.current_segment.active_command)
        pass

    def apply_train_command(self, active_command: TrainCommand) -> None:
        """Apply train command from Track Model"""
        spd = getattr(active_command, "commanded_speed", None)
        if spd is not None:
            self.tm.commanded_speed = max(0.0, float(spd))
        
        auth = getattr(active_command, "authority", None)
        if auth is not None:
            self.tm.authority_m = max(0.0, float(auth))

        logger.debug(f"Train {self.train_id} applied command: speed={spd:.2f} m/s, authority={auth:.1f} m")
