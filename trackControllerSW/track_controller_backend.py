from __future__ import annotations
import sys, os, logging, importlib.util, threading, time
from typing import Callable, Dict, List, Tuple, Any
from dataclasses import dataclass
from collections import deque

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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
    "Red Line": range(1, 77),
    "Green Line": range(1, 151),
    "Blue Line": range(1, 16),
}

@dataclass
class TrackModelMessage:
    block_id: int
    attribute: str
    value: Any

class TrackControllerBackend:

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
        # Maintenance mode
        self.maintenance_mode: bool = False
        self._known_occupancy: Dict[int, bool] = {}
        self._known_signal: Dict[int, SignalState] = {}
        self._known_commanded_speed: Dict[int, int] = {}
        self._known_commanded_auth: Dict[int, int] = {}
        self.incoming_messages: deque[TrackModelMessage] = deque()
        self._live_thread_running: bool = False

    def receive_model_update(self, block_id: int, attribute: str, value: Any) -> None:
        msg = TrackModelMessage(block_id, attribute, value)
        self.incoming_messages.append(msg)
        logger.info("Received Track Model update: %s", msg)
        self._process_next_model_message()

    def _process_next_model_message(self) -> None:
        if not self.incoming_messages:
            return
        msg = self.incoming_messages.popleft()
        match msg.attribute.lower():
            case "occupancy":
                self.set_block_occupancy(msg.block_id, bool(msg.value))
            case "signal":
                self.set_signal(msg.block_id, msg.value)
            case "switch":
                pos = "Normal" if msg.value == 0 else "Alternate"
                self.switches[msg.block_id] = pos
                logger.info("Switch %d position updated from model -> %s", msg.block_id, pos)
            case "crossing":
                stat = "Active" if msg.value else "Inactive"
                self.crossings[msg.block_id] = stat
                logger.info("Crossing %d status updated from model -> %s", msg.block_id, stat)
            case _:
                logger.warning("Unknown Track Model attribute: %s", msg.attribute)
        self._notify_listeners()

    def send_signal_command(self, block_id: int, state: SignalState) -> None:
        self.track_model.set_signal_state(block_id, state)
        logger.info("Sent signal command: Block %d -> %s", block_id, state.name)

    def send_switch_command(self, block_id: int, position: int) -> None:
        self.track_model.set_switch_position(block_id, position)
        logger.info("Sent switch command: Switch %d -> Position %d", block_id, position)

    def send_crossing_command(self, block_id: int, closed: bool) -> None:
        self.track_model.set_gate_status(block_id, closed)
        logger.info(
            "Sent crossing command: Crossing %d -> %s", block_id, "Closed" if closed else "Open"
        )

    def start_live_link(self, poll_interval: float = 1.0) -> None:
        if self._live_thread_running:
            return
        self._live_thread_running = True

        def _poll_loop() -> None:
            while self._live_thread_running:
                try:
                    self._poll_track_model()
                except Exception:
                    logger.exception("Error during Track Model polling loop")
                time.sleep(poll_interval)

        thread = threading.Thread(target=_poll_loop, daemon=True)
        thread.start()
        logger.info("Live link started for %s", self.line_name)

    def stop_live_link(self) -> None:
        self._live_thread_running = False
        logger.info("Live link stopped for %s", self.line_name)

    def _poll_track_model(self) -> None:
        for block_id, segment in self.track_model.segments.items():
            # Occupancy
            current_occ = bool(segment.occupied)
            if self._known_occupancy.get(block_id) != current_occ:
                self.receive_model_update(block_id, "occupancy", current_occ)
                self._known_occupancy[block_id] = current_occ
            # Signal
            current_sig = segment.signal_state
            if self._known_signal.get(block_id) != current_sig:
                self.receive_model_update(block_id, "signal", current_sig)
                self._known_signal[block_id] = current_sig
            # Switch
            if isinstance(segment, TrackSwitch):
                pos = segment.current_position
                prev = 0 if self.switches.get(block_id) == "Normal" else 1
                if pos != prev:
                    self.receive_model_update(block_id, "switch", pos)
                    self.switches[block_id] = "Normal" if pos == 0 else "Alternate"
            # Crossing
            if isinstance(segment, LevelCrossing):
                gate = bool(segment.gate_status)
                prev_state = self.crossings.get(block_id)
                current_state = "Active" if gate else "Inactive"
                if prev_state != current_state:
                    self.receive_model_update(block_id, "crossing", gate)
                    self.crossings[block_id] = current_state

    def _line_block_ids(self) -> List[int]:
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

    # Maintenance mode API
    def set_maintenance_mode(self, enabled: bool) -> None:
        self.maintenance_mode = bool(enabled)
        logger.info("%s: maintenance mode -> %s", self.line_name, self.maintenance_mode)
        self._notify_listeners()

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
        d: Dict[int, Dict[str, object]] = {}
        for b in self._line_block_ids():
            seg = self.track_model.segments[b]
            if b in self._known_occupancy:
                occupied_val = bool(self._known_occupancy[b])
            else:
                occupied_val = "N/A"
            suggested_speed = int(self._suggested_speed_mph.get(b, 50))
            suggested_auth = int(self._suggested_auth_yd.get(b, 50))
            if b in self._known_commanded_speed and int(self._commanded_speed_mph.get(b, 0)) != 0:
                commanded_speed = int(self._commanded_speed_mph.get(b, 0))
            else:
                commanded_speed = "N/A"
            if b in self._known_commanded_auth and int(self._commanded_auth_yd.get(b, 0)) != 0:
                commanded_auth = int(self._commanded_auth_yd.get(b, 0))
            else:
                commanded_auth = "N/A"
            if b in self._known_signal:
                signal_val = self._known_signal[b]
            else:
                signal_val = "N/A"

            d[b] = {
                "occupied": occupied_val,
                "suggested_speed": suggested_speed,
                "suggested_auth": suggested_auth,
                "commanded_speed": commanded_speed,
                "commanded_auth": commanded_auth,
                "signal": signal_val,
            }
        return d

    @property
    def num_blocks(self) -> int:
        return len(self._line_block_ids())

    # State mutation methods
    def set_block_occupancy(self, block: int, status: bool) -> None:
        seg = self._get_segment(block)
        seg.set_occupancy(bool(status))
        self._known_occupancy[block] = bool(status)

        logger.info("%s: Block %d occupancy -> %s", self.line_name, block, status)
        if status:
            self._commanded_auth_yd[block] = 0
            self._known_commanded_auth[block] = 0
            if isinstance(seg, LevelCrossing):
                seg.set_gate_status(True)
        else:
            self._commanded_auth_yd[block] = self._suggested_auth_yd.get(block, 50)
            self._known_commanded_auth[block] = int(self._commanded_auth_yd[block])
            if isinstance(seg, LevelCrossing):
                seg.set_gate_status(False)
        self._notify_listeners()

    def set_signal(self, block: int, color: str | SignalState) -> None:
        seg = self._get_segment(block)
        if isinstance(color, SignalState):
            state = color
        else:
            try:
                enum_name = str(color).replace(" ", "").upper()
                state = SignalState[enum_name]
            except Exception:
                raise ValueError(f"Invalid signal color '{color}'")
        seg.set_signal_state(state)
        self._known_signal[block] = state
        logger.info("%s: Block %d signal -> %s", self.line_name, block, state)
        self._notify_listeners()

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        """Switches may only be changed in maintenance mode (UI or PLC)."""
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")
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
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")
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

    def receive_ctc_suggestion(self, block: int, suggested_speed_mph: int, suggested_auth_yd: int) -> None:
        if block in self.track_model.segments and block in self._line_block_ids():
            self._suggested_speed_mph[block] = int(suggested_speed_mph)
            self._suggested_auth_yd[block] = int(suggested_auth_yd)
            self._notify_listeners()

    def set_commanded_speed(self, block: int, speed_mph: int) -> None:
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
        self._commanded_speed_mph[block] = int(speed_mph)
        self._known_commanded_speed[block] = int(self._commanded_speed_mph.get(block, 0))
        self._notify_listeners()

    def set_commanded_authority(self, block: int, auth_yd: int) -> None:
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
        if auth_yd > 0 and self.track_model.segments[block].occupied:
            raise SafetyException(f"Cannot grant authority on occupied block {block}")
        self._commanded_auth_yd[block] = int(auth_yd)
        self._known_commanded_auth[block] = int(self._commanded_auth_yd.get(block, 0))
        self._notify_listeners()

    def relay_to_train_model(self, block: int) -> TrainCommand:
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
        speed_mph = int(self._commanded_speed_mph.get(block, 0))
        auth_yd = int(self._commanded_auth_yd.get(block, 0))
        speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
        auth_meters = ConversionFunctions.yards_to_meters(auth_yd)
        return TrainCommand(train_id=block, commanded_speed=int(speed_mps), authority=int(auth_meters))

    # PLC upload
    def upload_plc(self, filepath: str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to upload PLC")
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
            for name, value in vars(plc_module).items():
                lname = name.lower()
                try:
                    # Occupancy: block_<id>_occupied
                    if lname.startswith("block_") and "_occupied" in lname:
                        parts = lname.split("_")
                        if len(parts) >= 3:
                            block_id = int(parts[1])
                            if block_id in self._line_block_ids():
                                self.set_block_occupancy(block_id, bool(value))
                        continue
                    # Switch: switch_<id>_bool
                    if lname.startswith("switch_"):
                        sid = int(lname.split("_")[1])
                        if isinstance(value, bool):
                            pos = "Normal" if value else "Alternate"
                        else:
                            pos = str(value).title()
                        self.safe_set_switch(sid, pos)
                        continue

                    # Crossing: crossing_<id>_bool
                    if lname.startswith("crossing_"):
                        cid = int(lname.split("_")[1])
                        if isinstance(value, bool):
                            status = "Active" if value else "Inactive"
                        else:
                            status = str(value).title()
                        self.safe_set_crossing(cid, status)
                        continue

                    # commanded speed: commanded_speed_<id> or cmd_speed_<id>
                    if lname.startswith("commanded_speed_") or lname.startswith("cmd_speed_"):
                        parts = lname.split("_")
                        block_id = int(parts[-1])
                        self.set_commanded_speed(block_id, int(value))
                        continue

                    # commanded authority: commanded_auth_<id> or cmd_auth_<id>
                    if lname.startswith("commanded_auth_") or lname.startswith("cmd_auth_") or lname.startswith("commanded_authority_"):
                        parts = lname.split("_")
                        block_id = int(parts[-1])
                        self.set_commanded_authority(block_id, int(value))
                        continue

                    # signal: signal_<id>_SignalState
                    if lname.startswith("signal_"):
                        block_id = int(lname.split("_")[1])
                        # Accept either SignalState or string
                        if isinstance(value, SignalState):
                            self.set_signal(block_id, value)
                        else:
                            self.set_signal(block_id, str(value))
                        continue
                except Exception:
                    logger.exception("PLC variable handling failed for %s=%r", name, value)
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
                try:
                    if cmd == "SWITCH" and len(parts) >= 3:
                        self.safe_set_switch(int(parts[1]), parts[2])
                    elif cmd == "CROSSING" and len(parts) >= 3:
                        self.safe_set_crossing(int(parts[1]), parts[2])
                    elif cmd == "SIGNAL" and len(parts) >= 3:
                        self.set_signal(int(parts[1]), parts[2])
                    elif cmd == "CMD_SPEED" and len(parts) >= 3:
                        self.set_commanded_speed(int(parts[1]), int(parts[2]))
                    elif cmd == "CMD_AUTH" and len(parts) >= 3:
                        self.set_commanded_authority(int(parts[1]), int(parts[2]))
                except Exception:
                    logger.exception("PLC line failed: %s", line)
                    continue

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
                    "signal": d["signal"].name.title() if isinstance(d["signal"], SignalState) else (d["signal"] if isinstance(d["signal"], str) else "N/A"),
                } for b, d in self.blocks.items()
            },
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "crossings": {
                cid: {"block": self.crossing_blocks.get(cid), "status": status}
                for cid, status in self.crossings.items()
            },
        }
