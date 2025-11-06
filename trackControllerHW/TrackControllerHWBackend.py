from __future__ import annotations
import time, threading, logging
from typing import Dict, Tuple, Any, Callable, List, Optional

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# -------------------- External types --------------------
try:
    from universal.universal import SignalState, TrainCommand, ConversionFunctions
except Exception:
    from enum import Enum
    class SignalState(str, Enum):
        RED = "Red"
        YELLOW = "Yellow"
        GREEN = "Green"
    class TrainCommand:
        def __init__(self, train_id: int, commanded_speed: int, authority: int) -> None:
            self.train_id = train_id
            self.commanded_speed = commanded_speed
            self.authority = authority
    class ConversionFunctions:
        @staticmethod
        def mph_to_mps(mph: int) -> float: return mph * 0.44704
        @staticmethod
        def yards_to_meters(yd: int) -> float: return yd * 0.9144

# -------- Track Model (use real one if available, else adapter) --------
try:
    from trackModel.track_model_backend import (
        TrackNetwork as TrackModelNetwork,
        TrackSegment, TrackSwitch, LevelCrossing,
    )
except Exception:
    class TrackSegment:
        def __init__(self, block_id: int) -> None:
            self.block_id = block_id
            self.occupied = False
            self.signal_state: SignalState | str = "N/A"
        def set_occupancy(self, occ: bool) -> None: self.occupied = bool(occ)
        def set_signal_state(self, state: SignalState) -> None: self.signal_state = state
    class TrackSwitch(TrackSegment):
        def __init__(self, block_id: int) -> None:
            super().__init__(block_id)
            self.current_position = 0
            self.straight_segment = None
            self.diverging_segment = None
        def set_switch_position(self, pos: int) -> None: self.current_position = int(pos)
    class LevelCrossing(TrackSegment):
        def __init__(self, block_id: int) -> None:
            super().__init__(block_id)
            self.gate_status = False
        def set_gate_status(self, closed: bool) -> None: self.gate_status = bool(closed)
    class TrackModelNetwork:
        def __init__(self) -> None:
            self.segments: Dict[int, TrackSegment] = {}
        def ensure_blocks(self, ids: List[int]) -> None:
            for i in ids:
                self.segments[i] = TrackSegment(i)
        def set_signal_state(self, block_id: int, state: SignalState) -> None:
            self.segments[block_id].set_signal_state(state)
        def set_switch_position(self, block_id: int, pos: int) -> None:
            seg = self.segments.get(block_id)
            if isinstance(seg, TrackSwitch): seg.set_switch_position(pos)
        def set_gate_status(self, block_id: int, closed: bool) -> None:
            seg = self.segments.get(block_id)
            if isinstance(seg, LevelCrossing): seg.set_gate_status(closed)
    class TrackModelAdapter(TrackModelNetwork): ...
else:
    class TrackModelAdapter(TrackModelNetwork):
        def ensure_blocks(self, ids: List[int]) -> None:
            segs = getattr(self, "segments", None)
            if isinstance(segs, dict):
                for i in ids:
                    if i not in segs:
                        segs[i] = TrackSegment(i)

# -------------------- Import software backend core --------------------
try:
    from trackControllerSW.track_controller_backend import (
        TrackControllerBackend as SoftwareTrackControllerBackend,
        SafetyException,
        LINE_BLOCK_MAP as SW_LINE_BLOCK_MAP,
    )
except Exception:
    try:
        from trackController.track_controller_backend import (
            TrackControllerBackend as SoftwareTrackControllerBackend,
            SafetyException,
            LINE_BLOCK_MAP as SW_LINE_BLOCK_MAP,
        )
    except Exception:
        class SafetyException(Exception): ...
        SW_LINE_BLOCK_MAP: Dict[str, range] = {
            "Red Line": range(1, 77),
            "Green Line": range(1, 151),
            "Blue Line": range(1, 16),
        }
        class SoftwareTrackControllerBackend:
            def __init__(self, track_model: TrackModelNetwork, line_name: str = "Blue Line") -> None:
                self.track_model = track_model
                self.line_name = line_name
                self._listeners: List[Callable[[], None]] = []
                self.switches: Dict[int, str] = {}
                self.switch_map: Dict[int, Tuple[int, ...]] = {}
                self.crossings: Dict[int, str] = {}
                self.crossing_blocks: Dict[int, int] = {}
                self._known_occupancy: Dict[int, bool] = {}
                self._known_signal: Dict[int, SignalState] = {}
                self._suggested_speed_mph: Dict[int, int] = {}
                self._suggested_auth_yd: Dict[int, int] = {}
                self._commanded_speed_mph: Dict[int, int] = {}
                self._commanded_auth_yd: Dict[int, int] = {}
                self.maintenance_mode = False
                self._live_thread_running = False
            def add_listener(self, cb: Callable[[], None]) -> None:
                if cb not in self._listeners: self._listeners.append(cb)
            def remove_listener(self, cb: Callable[[], None]) -> None:
                try: self._listeners.remove(cb)
                except ValueError: pass
            def _notify_listeners(self) -> None:
                for cb in list(self._listeners):
                    try: cb()
                    except Exception: logger.exception("Listener raised")
            def receive_model_update(self, block_id: int, attribute: str, value: Any) -> None:
                attr = attribute.lower()
                if attr == "occupancy":
                    self.set_block_occupancy(block_id, bool(value))
                elif attr == "signal":
                    self.set_signal(block_id, value)
                elif attr == "switch":
                    self.switches[block_id] = "Normal" if int(value) == 0 else "Alternate"
                elif attr == "crossing":
                    self.crossings[block_id] = "Active" if bool(value) else "Inactive"
                self._notify_listeners()
            def start_live_link(self, poll_interval: float = 1.0) -> None:
                if self._live_thread_running: return
                self._live_thread_running = True
                def loop():
                    while self._live_thread_running:
                        try: self._poll_track_model()
                        except Exception: logger.exception("poll loop")
                        time.sleep(poll_interval)
                threading.Thread(target=loop, daemon=True).start()
            def stop_live_link(self) -> None:
                self._live_thread_running = False
            def _poll_track_model(self) -> None:
                for b, seg in self.track_model.segments.items():
                    occ = bool(getattr(seg, "occupied", False))
                    if self._known_occupancy.get(b) != occ:
                        self.receive_model_update(b, "occupancy", occ)
                        self._known_occupancy[b] = occ
                    sig = getattr(seg, "signal_state", "N/A")
                    if self._known_signal.get(b) != sig and sig != "N/A":
                        self.receive_model_update(b, "signal", sig)
                        self._known_signal[b] = sig
            def set_block_occupancy(self, block: int, status: bool) -> None:
                seg = self.track_model.segments.get(block)
                if not seg: return
                seg.set_occupancy(bool(status))
                self._known_occupancy[block] = bool(status)
            def set_signal(self, block: int, color: str | SignalState) -> None:
                seg = self.track_model.segments.get(block)
                if not seg: return
                if isinstance(color, SignalState):
                    state = color
                else:
                    state = SignalState[str(color).replace(" ", "").upper()]
                seg.set_signal_state(state)
                self._known_signal[block] = state
            def set_maintenance_mode(self, enabled: bool) -> None:
                self.maintenance_mode = bool(enabled)
            def safe_set_switch(self, switch_id: int, position: str) -> None:
                if not self.maintenance_mode:
                    raise PermissionError("Must be in maintenance mode to change switches")
                pos = position.title()
                if pos not in ("Normal", "Alternate"):
                    raise ValueError("Invalid switch position")
                self.switches[switch_id] = pos
            def safe_set_crossing(self, crossing_id: int, status: str) -> None:
                if not self.maintenance_mode:
                    raise PermissionError("Must be in maintenance mode to change crossings")
                stat = status.title()
                if stat not in ("Active", "Inactive"):
                    raise ValueError("Invalid crossing status")
                self.crossings[crossing_id] = stat
            def set_commanded_speed(self, block: int, speed_mph: int) -> None:
                self._commanded_speed_mph[block] = int(speed_mph)
            def set_commanded_authority(self, block: int, auth_yd: int) -> None:
                self._commanded_auth_yd[block] = int(auth_yd)
            @property
            def blocks(self) -> Dict[int, Dict[str, object]]:
                d: Dict[int, Dict[str, object]] = {}
                rng = SW_LINE_BLOCK_MAP.get(self.line_name, range(1, 1))
                for b in rng:
                    if b not in self.track_model.segments: continue
                    cmd_spd = self._commanded_speed_mph.get(b, 0) or "N/A"
                    cmd_auth = self._commanded_auth_yd.get(b, 0) or "N/A"
                    d[b] = {
                        "occupied": self._known_occupancy.get(b, "N/A"),
                        "suggested_speed": int(self._suggested_speed_mph.get(b, 50)),
                        "suggested_auth": int(self._suggested_auth_yd.get(b, 50)),
                        "commanded_speed": cmd_spd,
                        "commanded_auth": cmd_auth,
                        "signal": self._known_signal.get(b, "N/A"),
                    }
                return d

# -------------------- Hardware block map --------------------
HW_LINE_BLOCK_MAP: Dict[str, range] = {
    "Blue Line":  range(1, 16),     # 1..15
    "Red Line":   range(74, 151),   # 74..150
    "Green Line": range(1, 151),    # 1..150
}

# -------------------- Hardware Backend --------------------
class HardwareTrackControllerBackend(SoftwareTrackControllerBackend):
    def __init__(self, track_model: TrackModelNetwork, line_name: str = "Blue Line") -> None:
        super().__init__(track_model, line_name=line_name)

        # Compute guard blocks (neighbors just outside our range if present)
        self._guard_blocks: List[int] = []
        rng = HW_LINE_BLOCK_MAP.get(self.line_name)
        first: Optional[int] = None
        last: Optional[int] = None
        if isinstance(rng, range):
            first = rng.start
            last = rng.stop - 1
        if first is not None and last is not None:
            before = first - 1
            after  = last + 1
            if before in self.track_model.segments: self._guard_blocks.append(before)
            if after  in self.track_model.segments: self._guard_blocks.append(after)

        self._guard_thread_running = False
        self._guard_poll_interval = 1.0

    # Robust: always returns something for the three lines you use
    def get_line_block_ids(self) -> List[int]:
        ids = list(HW_LINE_BLOCK_MAP.get(self.line_name, []))
        if not ids and self.line_name in ("Blue Line", "Red Line", "Green Line"):
            if self.line_name == "Blue Line":  ids = list(range(1, 16))
            if self.line_name == "Red Line":   ids = list(range(74, 151))
            if self.line_name == "Green Line": ids = list(range(1, 151))
        return ids

    @property
    def blocks(self) -> Dict[int, Dict[str, object]]:
        d: Dict[int, Dict[str, object]] = {}
        for b in self.get_line_block_ids():
            occupied_val = self._known_occupancy.get(b, "N/A")
            signal_val   = self._known_signal.get(b, "N/A")
            suggested_speed = int(getattr(self, "_suggested_speed_mph", {}).get(b, 50))
            suggested_auth  = int(getattr(self, "_suggested_auth_yd", {}).get(b, 50))
            cmd_spd  = int(getattr(self, "_commanded_speed_mph", {}).get(b, 0)) or "N/A"
            cmd_auth = int(getattr(self, "_commanded_auth_yd", {}).get(b, 0)) or "N/A"
            d[b] = {
                "occupied": occupied_val,
                "suggested_speed": suggested_speed,
                "suggested_auth": suggested_auth,
                "commanded_speed": cmd_spd,
                "commanded_auth": cmd_auth,
                "signal": signal_val,
            }
        return d

    def start_live_link(self, poll_interval: float = 1.0) -> None:
        super().start_live_link(poll_interval=poll_interval)
        self._guard_poll_interval = max(0.25, float(poll_interval))
        if self._guard_blocks and not self._guard_thread_running:
            self._guard_thread_running = True
            threading.Thread(target=self._guard_loop, daemon=True).start()
            logger.info("Guard-block polling started for %s; guards=%s", self.line_name, self._guard_blocks)

    def stop_live_link(self) -> None:
        try:
            self._guard_thread_running = False
        finally:
            super().stop_live_link()
            logger.info("Live link stopped for %s", self.line_name)

    def _guard_loop(self) -> None:
        while self._guard_thread_running:
            try:
                for gb in list(self._guard_blocks):
                    seg = self.track_model.segments.get(gb)
                    if not seg:
                        continue
                    occ = bool(getattr(seg, "occupied", False))
                    self.receive_model_update(gb, "occupancy", occ)
                    sig = getattr(seg, "signal_state", "N/A")
                    if sig != "N/A":
                        self.receive_model_update(gb, "signal", sig)
            except Exception:
                logger.exception("Guard-block polling error")
            time.sleep(self._guard_poll_interval)

    def run_line_test(self, plc_path: str) -> Dict[str, Any]:
        self.set_maintenance_mode(True)
        self.upload_plc(plc_path)
        blocks = self.blocks
        return {
            "line": self.line_name,
            "switches": getattr(self, "switches", {}).copy(),
            "crossings": getattr(self, "crossings", {}).copy(),
            "signals_set": {
                b: (d["signal"].name.title() if hasattr(d["signal"], "name") else d["signal"])
                for b, d in blocks.items() if d.get("signal") not in (None, "N/A")
            },
            "commanded": {
                b: {"speed_mph": d["commanded_speed"], "auth_yd": d["commanded_auth"]}
                for b, d in blocks.items()
                if d.get("commanded_speed") != "N/A" or d.get("commanded_auth") != "N/A"
            },
        }

def build_backend_for_sim(track_model: TrackModelNetwork, line_name: str = "Blue Line") -> HardwareTrackControllerBackend:
    return HardwareTrackControllerBackend(track_model, line_name=line_name)


# Clock function from CTC, display it, pulling it
# When CTC pauses clock our clock pauses
