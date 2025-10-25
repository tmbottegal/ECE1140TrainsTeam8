from __future__ import annotations
import sys,os,logging,importlib.util
from typing import Callable, Dict, List, Tuple
_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) # it makes shit work
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)
from universal.universal import SignalState, TrainCommand, ConversionFunctions
from trackModel.track_model_backend import (
    TrackNetwork as TrackModelNetwork,
    TrackSegment,
    TrackSwitch,
    LevelCrossing,
)
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class SafetyException(Exception):
    """Raised when a requested operation would violate safety rules."""

LINE_BLOCK_MAP: Dict[str, range] = {
    "Red Line": range(1, 77),    # 1..76
    "Green Line": range(1, 151), # 1..150
    "Blue Line": range(1, 16),   # 1..15
}

class TrackControllerBackend:
    """Controller adapter that operates on a TrackModel.TrackNetwork instance.
    Scoped to a named line which limits the blocks presented to the UI.
    """

    def __init__(self, track_model: TrackModelNetwork, line_name: str = "Blue Line") -> None:
        self.track_model = track_model
        self.line_name = line_name
        self._suggested_speed_mph: Dict[int, int] = {}
        self._suggested_auth_yd: Dict[int, int] = {}
        self._commanded_speed_mph: Dict[int, int] = {}
        self._commanded_auth_yd: Dict[int, int] = {}
        self.switches: Dict[int, str] = {}
        self.switch_map: Dict[int, Tuple[int, ...]] = {}
        self.crossings: Dict[int, str] = {}
        self.crossing_blocks: Dict[int, int] = {}
        self._listeners: List[Callable[[], None]] = []

    def _line_block_ids(self) -> List[int]:
        """Return the block IDs that belong to this controller's line and exist in the model."""
        rng = LINE_BLOCK_MAP.get(self.line_name)
        if rng is None:
            return sorted(self.track_model.segments.keys())
        return [b for b in rng if b in self.track_model.segments]

    # Listener API
    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug("Added listener %r for %s", callback, self.line_name)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            logger.debug("Listener %r not registered for %s", callback, self.line_name)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener %r raised while notifying", cb)

    # Helpers
    def _get_segment(self, block: int) -> TrackSegment:
        seg = self.track_model.segments.get(block)
        if seg is None:
            raise ValueError(f"Invalid block {block}")
        if block not in self._line_block_ids():
            raise ValueError(f"Block {block} is not part of {self.line_name}")
        return seg

    @property
    def blocks(self) -> Dict[int, Dict[str, object]]:
        """Construct a live UI-friendly blocks dict limited to this line."""
        d: Dict[int, Dict[str, object]] = {}
        for b in self._line_block_ids():
            seg = self.track_model.segments[b]
            d[b] = {
                "occupied": bool(seg.occupied),
                "suggested_speed": int(self._suggested_speed_mph.get(b, 50)),
                "suggested_auth": int(self._suggested_auth_yd.get(b, 50)),
                "commanded_speed": int(self._commanded_speed_mph.get(b, 0)),
                "commanded_auth": int(self._commanded_auth_yd.get(b, 0)),
                "signal": seg.signal_state if hasattr(seg, "signal_state") else SignalState.GREEN,
            }
        return d
    
    @property
    def num_blocks(self) -> int:
        return len(self._line_block_ids())

    # State mutation methods
    def set_block_occupancy(self, block: int, status: bool) -> None:
        seg = self._get_segment(block)
        seg.set_occupancy(bool(status))
        logger.info("%s: Block %d occupancy -> %s", self.line_name, block, status)
        if status:
            self._commanded_auth_yd[block] = 0
            if isinstance(seg, LevelCrossing):
                seg.set_gate_status(True)
        else:
            self._commanded_auth_yd[block] = self._suggested_auth_yd.get(block, 50)
            if isinstance(seg, LevelCrossing):
                seg.set_gate_status(False)
        self._notify_listeners()

    def set_signal(self, block: int, color: str | SignalState) -> None:
        seg = self._get_segment(block)
        if isinstance(color, SignalState):
            state = color
        else:
            try:
                enum_name = color.replace(" ", "").upper()
                state = SignalState[enum_name]
            except Exception:
                raise ValueError(f"Invalid signal color '{color}'")
        seg.set_signal_state(state)
        logger.info("%s: Block %d signal -> %s", self.line_name, block, state)
        self._notify_listeners()

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position")
        blocks = self.switch_map.get(switch_id)
        if not blocks and switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if isinstance(seg, TrackSwitch):
                blocks = tuple(b.block_id for b in (seg.straight_segment, seg.diverging_segment) if b is not None)
                self.switch_map[switch_id] = blocks
        if blocks:
            for b in blocks:
                if b in self.track_model.segments and self.track_model.segments[b].occupied:
                    raise SafetyException(f"Cannot change switch {switch_id}: block {b} occupied")
        if switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if isinstance(seg, TrackSwitch):
                idx = 0 if pos == "Normal" else 1
                seg.set_switch_position(idx)
                logger.info("%s: Switch %d -> %s", self.line_name, switch_id, pos)
        else:
            logger.info("%s: Switch id %d not present in model; storing state only", self.line_name, switch_id)
        self.switches[switch_id] = pos
        self._notify_listeners()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status")
        block = self.crossing_blocks.get(crossing_id)
        if block and self.track_model.segments.get(block) and self.track_model.segments[block].occupied and stat == "Inactive":
            raise SafetyException(f"Cannot set crossing {crossing_id} Inactive: block {block} occupied")
        if block and block in self.track_model.segments:
            seg = self.track_model.segments[block]
            if isinstance(seg, LevelCrossing):
                seg.set_gate_status(stat == "Active")
                logger.info("%s: Crossing %d (block %d) -> %s", self.line_name, crossing_id, block, stat)
        self.crossings[crossing_id] = stat
        self._notify_listeners()

    # pls ignore this part for now, needs to be fixed
    def receive_ctc_suggestion(self, block: int, suggested_speed_mph: int, suggested_auth_yd: int) -> None:
        if block in self.track_model.segments and block in self._line_block_ids():
            self._suggested_speed_mph[block] = int(suggested_speed_mph)
            self._suggested_auth_yd[block] = int(suggested_auth_yd)
            self._notify_listeners()

    # pls ignore this part for now, needs to be fixed
    def set_commanded_speed(self, block: int, speed_mph: int) -> None:
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
        self._commanded_speed_mph[block] = int(speed_mph)
        self._notify_listeners()

    # pls ignore this part for now, needs to be fixed
    def set_commanded_authority(self, block: int, auth_yd: int) -> None:
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
        if auth_yd > 0 and self.track_model.segments[block].occupied:
            raise SafetyException(f"Cannot grant authority on occupied block {block}")
        self._commanded_auth_yd[block] = int(auth_yd)
        self._notify_listeners()

    # pls ignore this part for now, needs to be fixed
    def relay_to_train_model(self, block: int) -> TrainCommand:
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
        speed_mph = int(self._commanded_speed_mph.get(block, 0))
        auth_yd = int(self._commanded_auth_yd.get(block, 0))
        speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
        auth_meters = ConversionFunctions.yards_to_meters(auth_yd)
        return TrainCommand(train_id=block, commanded_speed=int(speed_mps), authority=int(auth_meters))

    # PLC upload
    # pls ignore this part for now, needs to be fixed
    def upload_plc(self, filepath: str) -> None:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".py":
            spec = importlib.util.spec_from_file_location("plc_module", filepath)
            if spec is None or spec.loader is None:
                return
            plc_module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(plc_module)  # type: ignore
            except Exception:
                logger.exception("Failed to execute PLC Python file %s", filepath)
                return
            plc_vars = {k: v for k, v in vars(plc_module).items() if isinstance(v, bool)}
            for name, value in plc_vars.items():
                lname = name.lower()
                if lname.startswith("block_") and "_occupied" in lname:
                    try:
                        block_id = int(lname.split("_")[1])
                        if block_id in self._line_block_ids():
                            self.set_block_occupancy(block_id, value)
                    except ValueError:
                        continue
                if lname.startswith("switch_"):
                    try:
                        switch_id = int(lname.split("_")[1])
                        pos = "Normal" if value else "Alternate"
                        self.safe_set_switch(switch_id, pos)
                    except Exception:
                        continue
                if lname.startswith("crossing_"):
                    try:
                        crossing_id = int(lname.split("_")[1])
                        status = "Active" if value else "Inactive"
                        self.safe_set_crossing(crossing_id, status)
                    except Exception:
                        continue
        else:
            try:
                with open(filepath, "r") as f:
                    lines = f.read().splitlines()
            except FileNotFoundError:
                return
            for line in lines:
                parts = line.split()
                if not parts:
                    continue
                cmd = parts[0].upper()
                if cmd == "SWITCH" and len(parts) >= 3:
                    self.safe_set_switch(int(parts[1]), parts[2])
                elif cmd == "CROSSING" and len(parts) >= 3:
                    self.safe_set_crossing(int(parts[1]), parts[2])
        self._notify_listeners()

    # Reporting for UI
    def report_state(self) -> Dict[str, object]:
        return {
            "line": self.line_name,
            "blocks": {
                b: {
                    "occupied": d["occupied"],
                    "suggested_speed": d["suggested_speed"],
                    "suggested_auth": d["suggested_auth"],
                    "commanded_speed": d["commanded_speed"],
                    "commanded_auth": d["commanded_auth"],
                    "signal": d["signal"].name.title(),
                } for b, d in self.blocks.items()
            },
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "crossings": {
                cid: {"block": self.crossing_blocks.get(cid), "status": status}
                for cid, status in self.crossings.items()
            },
        }
