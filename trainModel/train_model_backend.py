import time
import logging
from typing import Callable, List, Dict, Optional
import math
from datetime import datetime

from universal.global_clock import clock 

logger = logging.getLogger(__name__)

class TrainModelBackend:
    """
    Backend simulation for a single train (SI units internally -> UI converts to imperial)
    """
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

    def __init__(self, line_name: str = "Green Line") -> None:
        self.line_name = line_name
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
        self.power_kw: float = 0.0      # kW
        self.grade_percent: float = 0.0 # %
        self.authority_m: float = 500.0 # m
        self.commanded_speed: float = 0.0  # m/s 

        # device / failures
        self.service_brake: bool = False
        self.emergency_brake: bool = False
        self.engine_failure: bool = False
        self.brake_failure: bool = False
        self.signal_pickup_failure: bool = False
        self.block_occupied: bool = True

        self.cabin_lights: bool = False
        self.headlights: bool = False
        self.left_doors: bool = False  
        self.right_doors: bool = False
        self.heating: bool = False
        self.air_conditioning: bool = False

        # cabin environment (C, then UI converts to F)
        self.actual_temperature: float = 22.0

        # misc / I/O
        self.beacon_info: str = "None"
        self.track_segment: Optional[str] = None  # filled by Train._sync_backend_track_segment()

        # observers
        self._listeners: List[Callable[[], None]] = []

        # integrator time bases
        self._last_t_monotonic: Optional[float] = None        # legacy/local stepping
        self._last_clock_time: Optional[datetime] = None      # global clock stepping

        # register with global clock
        clock.register_listener(self._on_clock_tick)
        self._clock_driven: bool = True  # registered to global clock; suppress local stepping


    # ------------------------------------------------------------------
    # clock listener
    def _on_clock_tick(self, now: datetime) -> None:
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
        power_kw: float,
        service_brake: bool,
        emergency_brake: bool,
        grade_percent: float,
        beacon_info: str = "None",
        **kwargs,
    ) -> None:
        """
        Update control inputs (called by Test UI). Extra kwargs supported:
          cabin_lights, headlights, left_doors, right_doors,
          heating, air_conditioning, commanded_speed_mph
        """
        self.power_kw = max(0.0, float(power_kw))
        self.service_brake = bool(service_brake)
        self.emergency_brake = bool(emergency_brake)
        self.grade_percent = float(grade_percent)
        self.beacon_info = str(beacon_info)

        # device toggles
        for name in ("cabin_lights", "headlights", "left_doors", "right_doors",
                     "heating", "air_conditioning"):
            if name in kwargs:
                setattr(self, name, bool(kwargs[name]))

        # commanded speed (mph -> m/s)
        if "commanded_speed_mph" in kwargs:
            self.commanded_speed = max(0.0, float(kwargs["commanded_speed_mph"])) / 2.23694

        # one physics step per input change (legacy local dt)
        if not self._clock_driven:
            self._simulate_step()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # legacy local stepper (kept so existing callers still work)
    def _simulate_step(self) -> None:
        """Physics update using a local monotonic-clock dt (for standalone use)."""
        now = time.monotonic()
        if self._last_t_monotonic is None:
            dt = 0.0
        else:
            dt = max(0.0, min(self.DT_MAX, now - self._last_t_monotonic))
        self._last_t_monotonic = now
        self._step_dt(dt)

    # ------------------------------------------------------------------
    # core stepper (used by both global-clock and legacy stepping)
    def _step_dt(self, dt: float) -> None:
        """Advance physics by a provided dt (seconds)."""
        # compute once
        mass = max(1.0, self.mass_kg * self.num_cars)  # guard
        v_old = self.velocity

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
        elif self.service_brake and not self.brake_failure:
            a_target = min(self.MAX_DECEL, a_base)
        else:
            a_target = max(-10.0, min(self.MAX_ACCEL, a_base))  # clamp absurd values

        # integrate (semi-implicit / Euler ok for small dt)
        a_new = a_target
        v_new = v_old + a_new * dt
        if v_new < 0.0:
            v_new = 0.0

        # hard speed cap from commanded speed (if provided)
        if v_new > self.commanded_speed:
            v_new = self.commanded_speed

        # position integrates velocity
        self.position += 0.5 * (v_old + v_new) * dt

        # authority decreases as distance is consumed
        self.authority_m = max(0.0, self.authority_m - 0.5 * (v_old + v_new) * dt)

        # if out of authority, stop train
        if self.authority_m <= 0.0 and v_new > 0.0:
            v_new = 0.0
            a_new = 0.0
            logger.warning("Authority limit reached. Train stopped.")

        # commit
        self.velocity = v_new
        self.acceleration = a_new
        self.block_occupied = self.velocity > 0.01

        # cabin temperature update (gradual)
        if dt > 0.0:
            deg_per_sec = 0.5 / 60.0
            if self.heating and not self.air_conditioning:
                dT = deg_per_sec * dt
            elif self.air_conditioning and not self.heating:
                dT = -deg_per_sec * dt
            elif self.air_conditioning and self.heating:
                dT = 0.0
            else:
                dT = 0.02 / 60.0 * dt  # tiny background creep
            self.actual_temperature += dT

        logger.info(
            "v=%.2f m/s, a=%.2f m/s², x=%.1f m, auth=%.1f m, "
            "brk=%s EB=%s P=%.1f kW grade=%.2f%%",
            self.velocity, self.acceleration, self.position, self.authority_m,
            self.service_brake, self.emergency_brake, self.power_kw, self.grade_percent
        )

    # ------------------------------------------------------------------
    # failures
    def set_failure_state(self, failure_type: str, state: bool) -> None:
        if failure_type == "engine":
            self.engine_failure = bool(state)
        elif failure_type == "brake":
            self.brake_failure = bool(state)
        elif failure_type == "signal":
            self.signal_pickup_failure = bool(state)
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
            "line_name": getattr(self, "line_name", "Green Line"),

            # cabin
            "actual_temperature_c": self.actual_temperature,
        }

# multi-train wrapper that binds a TrainModelBackend to the Track Network 
class Train:
    """
      - owns its own TrainModelBackend 
      - can bind to TrackNetwork for grade/speed-limit/beacon/occupancy
      - maintains its block + in-block displacement
    """

    def __init__(self, train_id: int | str, backend: Optional["TrainModelBackend"] = None) -> None:
        self.train_id = str(train_id)
        self.tm = backend if backend is not None else TrainModelBackend()
        self.controller = None  # TrainControllerBackend instance

        self.tm.train_id = self.train_id

        # track binding
        self.network: Optional[object] = None
        self.current_segment: Optional[object] = None
        self.segment_displacement_m: float = 0.0

    #  binding to Track Model network
    def bind_to_track(self, network, start_block_id: int, displacement_m: float = 0.0) -> None:
        """
        attach this Train to a TrackNetwork (from trackModel/track_model_backend.py)
        without importing it here (keeps this file independent of TrackNetwork)
        """
        self.network = network
        seg = getattr(self.network, "segments", {}).get(start_block_id)
        if seg is None:
            raise ValueError(f"Block {start_block_id} not found in TrackNetwork")

        self.current_segment = seg
        self.segment_displacement_m = max(0.0, min(float(displacement_m), float(getattr(seg, "length", 0.0))))

        # mark occupancy
        try:
            self.current_segment.set_occupancy(True)
        except Exception:
            pass

        # keep backend label in sync for the UI
        self._sync_backend_track_segment()

    #  helpers from track graph 
    def _next_segment(self):
        return None if self.current_segment is None else self.current_segment.get_next_segment()

    def _prev_segment(self):
        return None if self.current_segment is None else self.current_segment.get_previous_segment()

    @staticmethod
    def _is_red(seg) -> bool:
        """tolerant check for a red signal state (enum, name, or string)"""
        st = getattr(seg, "signal_state", None)
        val = getattr(st, "value", st)
        name = getattr(st, "name", None)
        s = str(val or name or st).lower()
        return "red" in s  # catches "red", "SignalState.RED", etc.

    def _sync_backend_track_segment(self) -> None:
        """update backend.track_segment from the current segment (id/name)"""
        try:
            block_id = getattr(self.current_segment, "block_id", None)
            label = block_id if block_id is not None else getattr(self.current_segment, "name", "—")
            self.tm.track_segment = str(label)
        except Exception:
            self.tm.track_segment = "—"

    #  per-step sync from track -> physics 
    def _pull_track_inputs(self) -> dict:
        """
        read grade, speed-limit, beacon, etc. from current block (if bound)
        returns a dict for backend.set_inputs(...)
        """
        if self.current_segment is None:
            return {
                "grade_percent": 0.0,
                "beacon_info": "None",
                "speed_limit_mps": float(self.tm.MAX_SPEED),
            }

        seg = self.current_segment
        speed_limit_mps = float(getattr(seg, "speed_limit", self.tm.MAX_SPEED))
        grade_percent = float(getattr(seg, "grade", 0.0))
        beacon_raw = getattr(seg, "beacon_data", "")
        beacon_info = str(beacon_raw) if beacon_raw else "None"

        return {
            "grade_percent": grade_percent,
            "beacon_info": beacon_info,
            "speed_limit_mps": speed_limit_mps,
        }

    # movement along the track
    def _advance_along_track(self, distance_m: float) -> None:
        """
        move along the track graph by `distance_m`;
        updates occupancy when crossing block boundaries
        """
        if self.current_segment is None or self.network is None or distance_m == 0.0:
            return

        seg = self.current_segment
        seg_len = float(getattr(seg, "length", 0.0))
        pos = self.segment_displacement_m
        new_pos = pos + distance_m

        # moving backward
        if new_pos < 0.0:
            prev_seg = self._prev_segment()
            if prev_seg is None:
                # clamp to start of current block
                self.segment_displacement_m = 0.0
                return

            # stop at boundary if previous is closed or red
            if getattr(prev_seg, "closed", False) or self._is_red(prev_seg):
                self.segment_displacement_m = 0.0
                return

            # cross into previous block
            try:
                seg.set_occupancy(False)
            except Exception:
                pass
            self.current_segment = prev_seg
            try:
                self.current_segment.set_occupancy(True)
            except Exception:
                pass

            self.segment_displacement_m = max(0.0, new_pos + float(getattr(prev_seg, "length", 0.0)))
            self._sync_backend_track_segment()
            return

        # moving forward
        if new_pos > seg_len:
            next_seg = self._next_segment()
            if next_seg is None:
                # end of line
                self.segment_displacement_m = seg_len
                return

            if getattr(next_seg, "closed", False) or self._is_red(next_seg):
                # park at end of current block
                self.segment_displacement_m = seg_len
                return

            # cross into next block
            try:
                seg.set_occupancy(False)
            except Exception:
                pass
            self.current_segment = next_seg
            try:
                self.current_segment.set_occupancy(True)
            except Exception:
                pass

            self.segment_displacement_m = min(
                float(getattr(self.current_segment, "length", 0.0)),
                new_pos - seg_len,
            )
            self._sync_backend_track_segment()
            return

        # still within current block
        self.segment_displacement_m = new_pos

    # public tick
    def tick(
        self,
        dt_s: float,
        *,
        power_kw: float | None = None,
        service_brake: bool | None = None,
        emergency_brake: bool | None = None,
    ) -> None:
        """
        integration step for train:
          1) read track (grade, beacon, speed limit)
          2) apply inputs to physics and integrate (backend handles stepping)
          3) move along the track by v * dt and update occupancy
        """
        trk = self._pull_track_inputs()

        # feed physics; let backend/global clock handle time integration
        self.tm.set_inputs(
            power_kw=float(self.tm.power_kw if power_kw is None else power_kw),
            service_brake=bool(self.tm.service_brake if service_brake is None else service_brake),
            emergency_brake=bool(self.tm.emergency_brake if emergency_brake is None else emergency_brake),
            grade_percent=float(trk["grade_percent"]),
            beacon_info=trk["beacon_info"],
        )

        # enforce track speed limit (hard cap)
        try:
            limit = float(trk["speed_limit_mps"])
            if self.tm.velocity > limit:
                self.tm.velocity = limit
        except Exception:
            pass

        # move on the graph
        if dt_s > 0.0:
            self._advance_along_track(float(self.tm.velocity) * float(dt_s))

    def attach_to_global_clock(self):
        """call once after bind_to_track(..) so this Train advances each global tick"""
        self._last_clock_time = None

    def _on_clock(now):
        # first call just initializes
        if self._last_clock_time is None:
            self._last_clock_time = now
            return
        dt = (now - self._last_clock_time).total_seconds()
        self._last_clock_time = now

        # substep like the backend does, so crossings are smooth
        remaining = max(0.0, float(dt))
        while remaining > 1e-6:
            step = min(self.tm.DT_MAX, remaining)
            self.tick(step)  # tick moves along the track & updates occupancy
            remaining -= step

    from universal.global_clock import clock
    clock.register_listener(_on_clock)
    self._clock_cb = _on_clock  # keep a handle if you want to detach later

    # helpers for UI
    def report_state(self) -> dict:
        s = self.tm.report_state()
        s.update({
            "train_id": self.train_id,
            "track_block_id": None if self.current_segment is None else getattr(self.current_segment, "block_id", None),
            "inblock_displacement_m": self.segment_displacement_m,
            "line_name": getattr(self.tm, "line_name", "Green Line"),
        })
        return s

    # controller wiring
    def attach_controller(self, controller) -> None:
        """
        attach TrainControllerBackend-like object
        expected interface (methods):
        set_actual_speed(mps), set_commanded_speed(mps), set_commanded_authority(m),
        set_service_brake(bool), set_emergency_brake(bool), set_speed_limit(mps),
        get_display_values() -> dict, update(dt_s: float)
        """
        self.controller = controller
        # keep controller's idea of speed limit in sync with current block
        try:
            trk = self._pull_track_inputs()
            self.controller.set_speed_limit(float(trk["speed_limit_mps"]))
        except Exception:
            pass

    def send_to_controller(self) -> None:
        """
        push current TM/track state to controller:
        - commanded speed (from TM), authority
        - actual speed
        - manual brake requests (from TM flags)
        - speed limit (from current track block)
        """
        if not self.controller:
            return

        # actual speed/authority from the physics model
        self.controller.set_actual_speed(float(self.tm.velocity))
        self.controller.set_commanded_authority(float(self.tm.authority_m))

        # whichever module sets commanded speed (CTC/wayside) writes it into TM;
        # forward it into the controller (m/s expected).
        self.controller.set_commanded_speed(float(self.tm.commanded_speed))

        # driver/engineer brake requests (manual)
        self.controller.set_service_brake(bool(self.tm.service_brake))
        self.controller.set_emergency_brake(bool(self.tm.emergency_brake))

        # keep speed limit updated from the current track block
        try:
            trk = self._pull_track_inputs()
            self.controller.set_speed_limit(float(trk["speed_limit_mps"]))
        except Exception:
            pass

    def receive_from_controller(self) -> None:
        """
        - pull power/brake outputs from controller and apply to TM
        - grade/beacon from track so we include them in the same write
        """
        if not self.controller:
            return

        disp = self.controller.get_display_values()  # {'power_kw', 'service_brake', 'emergency_brake', ...}
        trk = self._pull_track_inputs()

        self.tm.set_inputs(
            power_kw=float(disp.get("power_kw", 0.0)),
            service_brake=bool(disp.get("service_brake", False)),
            emergency_brake=bool(disp.get("emergency_brake", False)),
            grade_percent=float(trk["grade_percent"]),
            beacon_info=trk["beacon_info"],
        )

    def step_controller(self, dt_s: float) -> None:
        """
        one controller step — send inputs -> update(dt) -> receive outputs
        call this before advancing along the track
        """
        if not self.controller:
            return
        self.send_to_controller()
        self.controller.update(float(dt_s))
        self.receive_from_controller()
