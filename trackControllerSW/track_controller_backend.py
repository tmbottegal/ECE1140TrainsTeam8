from __future__ import annotations
import sys, os, logging, importlib.util, threading, time, math
from typing import Callable, Dict, List, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from collections import deque

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)


from universal.universal import SignalState, TrainCommand, ConversionFunctions
from trackModel.track_model_backend import TrackNetwork

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class SafetyException(Exception):
    """Raised when operation would violate safety rules."""

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

@dataclass
class WaysideStatusUpdate:
    block_id: int
    occupied: bool
    signal_state: SignalState
    switch_position: int | None = None
    crossing_status: bool | None = None

class TrackControllerBackend:

    def __init__(self, track_model: TrackNetwork, line_name: str = "Green Line") -> None:
        self.track_model = track_model
        self.line_name = line_name
        self._suggested_speed_mps: Dict[int, float] = {}
        self._suggested_auth_m: Dict[int, float] = {}
        self._commanded_speed_mps: Dict[int, int] = {}
        self._commanded_auth_m: Dict[int, int] = {}
        self.switches: Dict[int, int] = {}
        self.switch_map: Dict[int, Tuple[int, ...]] = {}
        self.crossings: Dict[int, bool] = {}
        self.crossing_blocks: Dict[int, int] = {}
        self._listeners: List[Callable[[], None]] = []
        self.time = datetime(2000,1,1,0,0,0)
        self.maintenance_mode: bool = False
        self._known_occupancy: Dict[int, bool] = {}
        self._known_signal: Dict[int, SignalState] = {}
        self._known_commanded_speed: Dict[int, int] = {}
        self._known_commanded_auth: Dict[int, int] = {}
        self.incoming_messages: deque[TrackModelMessage] = deque()
        self._live_thread_running: bool = False
        self.ctc_backend = None
        self._ctc_update_enabled: bool = True
        self._initialize_infrastructure()
        self._initial_sync()
    
    def set_ctc_backend(self, ctc_backend: Any) -> None:
        self.ctc_backend = ctc_backend
        logger.info("%s: CTC backend connected", self.line_name)
    
    def enable_ctc_updates(self, enabled: bool = True) -> None:
        self._ctc_update_enabled = enabled
        logger.info("%s: CTC updates %s", self.line_name, 
                   "enabled" if enabled else "disabled")
    
    def receive_ctc_suggestion(self, block: int, suggested_speed_mps: float, suggested_auth_m: float) -> None:
        if block not in self._line_block_ids():
            logger.warning("CTC suggestion for invalid block %d on %s", block, self.line_name)
            return
        self._suggested_speed_mps[block] = suggested_speed_mps
        self._suggested_auth_m[block] = suggested_auth_m
        logger.info("%s: CTC suggestion for block %d: %.2f m/s, %.2f m", self.line_name, block, suggested_speed_mps, suggested_auth_m)
        self._notify_listeners()
    
    def _send_status_to_ctc(self) -> None:
        if not self._ctc_update_enabled or self.ctc_backend is None:
            return
        status_updates: List[WaysideStatusUpdate] = []
        for block_id in self._line_block_ids():
            if block_id not in self.track_model.segments:
                continue
            occupied = self._known_occupancy.get(block_id, False)
            signal = self._known_signal.get(block_id, SignalState.RED)
            switch_pos = None
            if block_id in self.switches:
                switch_pos = self.switches[block_id]
            crossing_status = None
            for cid, cblock in self.crossing_blocks.items():
                if cblock == block_id:
                    crossing_status = self.crossings.get(cid)
                    break
            status = WaysideStatusUpdate(
                block_id=block_id,
                occupied=occupied,
                signal_state=signal,
                switch_position=switch_pos,
                crossing_status=crossing_status
            )
            status_updates.append(status)
        try:
            if hasattr(self.ctc_backend, 'receive_wayside_status'):
                self.ctc_backend.receive_wayside_status(self.line_name, status_updates)
                logger.debug("%s: Sent %d status updates to CTC", self.line_name, len(status_updates))
            else:
                for status in status_updates:
                    self._send_single_status_to_ctc(status)
        except Exception:
            logger.exception("%s: Failed to send status to CTC", self.line_name)
    
    def _send_single_status_to_ctc(self, status: WaysideStatusUpdate) -> None:
        if self.ctc_backend is None:
            return
        try:
            if hasattr(self.ctc_backend, 'update_block_occupancy'):
                self.ctc_backend.update_block_occupancy(self.line_name, status.block_id, status.occupied)
            
            if hasattr(self.ctc_backend, 'update_signal_state'):
                self.ctc_backend.update_signal_state(self.line_name, status.block_id, status.signal_state)
            
            if status.switch_position is not None and hasattr(self.ctc_backend, 'update_switch_position'):
                self.ctc_backend.update_switch_position(self.line_name, status.block_id, status.switch_position)
            
            if status.crossing_status is not None and hasattr(self.ctc_backend, 'update_crossing_status'):
                self.ctc_backend.update_crossing_status(self.line_name, status.block_id, status.crossing_status)
        except Exception:
            logger.exception("%s: Failed to send single status for block %d", 
                           self.line_name, status.block_id)

    def _initialize_infrastructure(self) -> None:
        for sid in self.switch_map:
            self.switches[sid] = 0
        for cid in self.crossing_blocks:
            self.crossings[cid] = False

    def _initial_sync(self) -> None:
        logger.info("Starting initial sync with Track Model for %s", self.line_name)
        try:
            if not hasattr(self.track_model, "get_wayside_status"):
                logger.warning("Track Model does not have get_wayside_status(), skipping sync")
                return  
            status = self.track_model.get_wayside_status()
            if isinstance(status, dict) and "segments" in status:
                segments = status.get("segments", {})
                for block_id, info in segments.items():
                    try:
                        bid = int(block_id)
                    except:
                        continue
                    if bid not in self._line_block_ids():
                        continue
                    if not isinstance(info, dict):
                        continue
                    if "occupied" in info:
                        self._known_occupancy[bid] = bool(info["occupied"])
                        logger.debug("Synced block %d occupancy: %s", bid, info["occupied"])
                    if "signal_state" in info:
                        self._known_signal[bid] = info["signal_state"]
                        logger.debug("Synced block %d signal: %s", bid, info["signal_state"])
                    if "current_position" in info and bid in self.switches:
                        self.switches[bid] = int(info["current_position"])
                        logger.debug("Synced switch %d position: %d", bid, self.switches[bid])
                    if "gate_status" in info:
                        for cid, cblock in self.crossing_blocks.items():
                            if cblock == bid:
                                self.crossings[cid] = bool(info["gate_status"])
                                logger.debug("Synced crossing %d status: %s", cid, self.crossings[cid])
            logger.info("Initial sync completed for %s", self.line_name)
        except Exception:
            logger.exception("Failed to perform initial sync with track model")

    def receive_model_update(self, block_id: int, attribute: str, value: Any) -> None:
        msg = TrackModelMessage(block_id, attribute, value)
        self.incoming_messages.append(msg)
        logger.info("Received Track Model update: block=%d, attr=%s, value=%s", block_id, attribute, value)
        self._process_next_model_message()

    def _process_next_model_message(self) -> None:
        if not self.incoming_messages:
            return
        msg = self.incoming_messages.popleft()
        match msg.attribute.lower():
            case "occupancy":
                self._update_occupancy_from_model(msg.block_id, bool(msg.value))
            case "signal":
                self._known_signal[msg.block_id] = msg.value
                logger.info("Signal %d state updated from model -> %s", msg.block_id, msg.value)
            case "switch":
                self.switches[msg.block_id] = int(msg.value)
                logger.info("Switch %d position updated from model -> %d", msg.block_id, msg.value)
            case "crossing":
                for cid, cblock in self.crossing_blocks.items():
                    if cblock == msg.block_id:
                        self.crossings[cid] = bool(msg.value)
                logger.info("Crossing at block %d status updated from model -> %s", msg.block_id, msg.value)
            case _:
                logger.warning("Unknown Track Model attribute: %s", msg.attribute)
        self._notify_listeners()
        self._send_status_to_ctc()

    def set_commanded_speed(self, block_id: int, speed_mps: int) -> None:
        if block_id not in self._line_block_ids():
            logger.warning("Cannot set commanded speed: block %d not in %s", block_id, self.line_name)
            return
        self._commanded_speed_mps[block_id] = speed_mps
        self._known_commanded_speed[block_id] = speed_mps
        logger.info("[%s] Commanded speed -> block %d = %d m/s", 
                self.line_name, block_id, speed_mps)
        try:
            auth_m = self._commanded_auth_m.get(block_id, 0)
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(auth_m))
            logger.info("Sent to Track Model: block %d, speed=%d m/s, auth=%d m", 
                    block_id, int(speed_mps), int(auth_m))
        except Exception as e:
            logger.warning("Track Model rejected commanded speed for block %d: %s", block_id, e)
        self._notify_listeners()

    def set_commanded_authority(self, block_id: int, authority_m: int) -> None:
        if block_id not in self._line_block_ids():
            logger.warning("Cannot set commanded authority: block %d not in %s", block_id, self.line_name)
            return
        self._commanded_auth_m[block_id] = authority_m
        self._known_commanded_auth[block_id] = authority_m
        logger.info("[%s] Commanded authority -> block %d = %d m", 
                self.line_name, block_id, authority_m)
        try:
            speed_mps = self._commanded_speed_mps.get(block_id, 0)
            self.track_model.broadcast_train_command(block_id, int(speed_mps), int(authority_m))
            logger.info("Sent to Track Model: block %d, speed=%d m/s, auth=%d m", block_id, int(speed_mps), int(authority_m))
        except Exception as e:
            logger.warning("Track Model rejected commanded authority for block %d: %s", block_id, e)
        self._notify_listeners()

    def upload_plc(self, filepath: str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to upload PLC")
        ext = os.path.splitext(filepath)[1].lower()
        logger.info("Uploading PLC file: %s", filepath)
        if ext == ".py":
            self._upload_plc_python(filepath)
        else:
            self._upload_plc_text(filepath)
        self._sync_after_plc_upload()
        self._notify_listeners()
        self._send_status_to_ctc()
        logger.info("PLC upload completed for %s", self.line_name)

    def _upload_plc_python(self, filepath: str) -> None:
        spec = importlib.util.spec_from_file_location("plc_module", filepath)
        if spec is None or spec.loader is None:
            logger.error("Could not load PLC module from %s", filepath)
            return
        plc_module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(plc_module)
        except Exception:
            logger.exception("Failed to execute PLC Python file %s", filepath)
            return
        for name, value in vars(plc_module).items():
            lname = name.lower()
            try:
                if lname.startswith("block_") and "_occupied" in lname:
                    parts = lname.split("_")
                    if len(parts) >= 3:
                        block_id = int(parts[1])
                        if block_id in self._line_block_ids():
                            self.set_block_occupancy(block_id, bool(value))
                    continue
                if lname.startswith("switch_"):
                    sid = int(lname.split("_")[1])
                    if sid in self.switches:
                        if isinstance(value, bool):
                            pos = 0 if value else 1
                        elif isinstance(value, int):
                            pos = value
                        else:
                            pos_str = str(value).title()
                            pos = 0 if pos_str == "Normal" else 1
                        self._plc_set_switch(sid, pos)
                    continue
                if lname.startswith("crossing_"):
                    cid = int(lname.split("_")[1])
                    if cid in self.crossings:
                        if isinstance(value, bool):
                            status = value
                        else:
                            status_str = str(value).title()
                            status = True if status_str == "Active" else False
                        self._plc_set_crossing(cid, status)
                    continue
                if lname.startswith("commanded_speed_") or lname.startswith("cmd_speed_"):
                    block_id = int(lname.split("_")[-1])
                    if block_id in self._line_block_ids():
                        speed_mph = float(value)
                        speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
                        self.set_commanded_speed(block_id, int(speed_mps))
                        logger.info("PLC: Set block %d speed: %d mph -> %d m/s", block_id, int(speed_mph), int(speed_mps))
                    continue
                if (lname.startswith("commanded_auth_") or 
                    lname.startswith("cmd_auth_") or 
                    lname.startswith("commanded_authority_")):
                    block_id = int(lname.split("_")[-1])
                    if block_id in self._line_block_ids():
                        auth_yd = float(value)
                        auth_m = ConversionFunctions.yards_to_meters(auth_yd)
                        self.set_commanded_authority(block_id, int(auth_m))
                        logger.info("PLC: Set block %d auth: %d yd -> %d m", block_id, int(auth_yd), int(auth_m))
                    continue
                if lname.startswith("signal_"):
                    block_id = int(lname.split("_")[1])
                    if block_id in self._line_block_ids():
                        if isinstance(value, SignalState):
                            self.set_signal(block_id, value)
                        else:
                            self.set_signal(block_id, str(value))
                    continue
            except Exception:
                logger.exception("PLC variable handling failed for %s=%r", name, value)
                continue

    def _upload_plc_text(self, filepath: str) -> None:
        try:
            with open(filepath, "r") as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            logger.error("PLC file not found: %s", filepath)
            return
        for line_num, line in enumerate(lines, 1):
            parts = line.split()
            if not parts or line.strip().startswith("#"):
                continue
            cmd = parts[0].upper()
            try:
                if cmd == "SWITCH" and len(parts) >= 3:
                    sid = int(parts[1])
                    if sid in self.switches:
                        if parts[2].isdigit():
                            self.safe_set_switch(sid, int(parts[2]))
                        else:
                            pos_str = parts[2].title()
                            pos = 0 if pos_str == "Normal" else 1
                            self._plc_set_switch(sid, pos)
                elif cmd == "CROSSING" and len(parts) >= 3:
                    cid = int(parts[1])
                    if cid in self.crossings:
                        if parts[2].lower() in ('true', 'false'):
                            status = parts[2].lower() == 'true'
                        else:
                            status_str = parts[2].title()
                            status = True if status_str == "Active" else False
                        self._plc_set_crossing(cid, status)
                elif cmd == "SIGNAL" and len(parts) >= 3:
                    bid = int(parts[1])
                    if bid in self._line_block_ids():
                        self.set_signal(bid, parts[2])
                    else:
                        logger.debug("TXT PLC SIGNAL for block %d ignored (not part of %s)", bid, self.line_name)
                elif cmd == "CMD_SPEED" and len(parts) >= 3:
                    bid = int(parts[1])
                    if bid in self._line_block_ids():
                        speed_mph = float(parts[2])
                        speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
                        self.set_commanded_speed(bid, int(speed_mps))
                        logger.info("TXT PLC: Set block %d speed: %d mph -> %d m/s", bid, int(speed_mph), int(speed_mps))
                    else:
                        logger.debug("TXT PLC CMD_SPEED for block %d ignored (not part of %s)", bid, self.line_name)
                elif cmd == "CMD_AUTH" and len(parts) >= 3:
                    bid = int(parts[1])
                    if bid in self._line_block_ids():
                        auth_yd = float(parts[2])
                        auth_m = ConversionFunctions.yards_to_meters(auth_yd)
                        self.set_commanded_authority(bid, int(auth_m))
                        logger.info("TXT PLC: Set block %d auth: %d yd -> %d m", bid, int(auth_yd), int(auth_m))
                    else:
                        logger.debug("TXT PLC CMD_AUTH for block %d ignored (not part of %s)", bid, self.line_name)                        
            except Exception:
                logger.exception("PLC line %d failed: %s", line_num, line)
                continue

    def _sync_after_plc_upload(self) -> None:
        for block_id in self._line_block_ids():
            seg = self.track_model.segments.get(block_id)
            if not seg:
                continue
            if hasattr(seg, 'signal_state'):
                self._known_signal[block_id] = seg.signal_state
            if hasattr(seg, 'active_command') and seg.active_command:
                cmd = seg.active_command
                if hasattr(cmd, 'commanded_speed') and cmd.commanded_speed:
                    speed_mps = int(cmd.commanded_speed)
                    self._commanded_speed_mps[block_id] = speed_mps
                    self._known_commanded_speed[block_id] = speed_mps
                if hasattr(cmd, 'authority') and cmd.authority:
                    auth_m = int(cmd.authority)
                    self._commanded_auth_m[block_id] = auth_m
                    self._known_commanded_auth[block_id] = auth_m

    def report_state(self) -> Dict[str, object]:
        switches_display = {}
        for sid, pos in self.switches.items():
            switches_display[sid] = "Normal" if pos == 0 else "Alternate"
        crossings_display = {}
        for cid, status in self.crossings.items():
            crossings_display[cid] = {
                "block": self.crossing_blocks.get(cid),
                "status": "Active" if status else "Inactive"
            }
        return {
            "line": self.line_name,
            "maintenance_mode": self.maintenance_mode,
            "blocks": {
                b: {
                    "occupied": d["occupied"],
                    "suggested_speed": d["suggested_speed"],
                    "suggested_auth": d["suggested_auth"],
                    "commanded_speed": d["commanded_speed"],
                    "commanded_auth": d["commanded_auth"],
                    "signal": (d["signal"].name.title() 
                             if isinstance(d["signal"], SignalState) 
                             else (d["signal"] if isinstance(d["signal"], str) else "N/A")),
                } for b, d in self.blocks.items()
            },
            "switches": switches_display,
            "switch_map": self.switch_map.copy(),
            "crossing": crossings_display,
        }

    def _update_occupancy_from_model(self, block_id: int, occupied: bool) -> None:
        old_state = self._known_occupancy.get(block_id)
        self._known_occupancy[block_id] = occupied
        logger.info("%s: Block %d occupancy updated from model -> %s", self.line_name, block_id, occupied)
        if old_state == occupied:
            return
        for cid, cblock in self.crossing_blocks.items():
            if cblock == block_id:
                try:
                    seg = self.track_model.segments.get(block_id)
                    if seg and isinstance(seg, TrackNetwork):
                        seg.set_gate_status(occupied)
                        self.crossings[cid] = occupied
                        logger.info("Auto-managed crossing %d gates: %s (block %d occupancy=%s)", cid, self.crossings[cid], block_id, occupied)
                except Exception:
                    logger.exception("Failed to auto-update crossing gate for block %d", block_id)
        if occupied:
            if block_id in self._commanded_auth_m:
                self._commanded_auth_m[block_id] = 0
                self._known_commanded_auth[block_id] = 0
        else:
            suggested_auth = self._suggested_auth_m.get(block_id, 50)
            self._commanded_auth_m[block_id] = int(suggested_auth)
            self._known_commanded_auth[block_id] = int(suggested_auth)

    def start_live_link(self, poll_interval: float = 1.0) -> None:
        if self._live_thread_running:
            logger.warning("Live link already running for %s", self.line_name)
            return
        self._live_thread_running = True
        def _poll_loop() -> None:
            while self._live_thread_running:
                try:
                    self._poll_track_model()
                except Exception:
                    logger.exception("Error during Track Model polling loop")
                time.sleep(poll_interval)
        thread = threading.Thread(target=_poll_loop, daemon=True, name=f"TrackPoll-{self.line_name}")
        thread.start()
        logger.info("Live link started for %s (poll interval: %.1fs)", self.line_name, poll_interval)

    def stop_live_link(self) -> None:
        self._live_thread_running = False
        logger.info("Live link stopped for %s", self.line_name)

    def _poll_track_model(self) -> None:
        if not hasattr(self.track_model, "segments"):
            return
        state_changed = False
        for block_id in self._line_block_ids():
            segment = self.track_model.segments.get(block_id)
            if segment is None:
                continue
            try:
                current_occ = getattr(segment, 'occupied', None)
                if current_occ is not None:
                    known_occ = self._known_occupancy.get(block_id)
                    if known_occ != current_occ:
                        self._update_occupancy_from_model(block_id, current_occ)
                        state_changed = True
                current_signal = getattr(segment, 'signal_state', None)
                if current_signal is not None:
                    known_signal = self._known_signal.get(block_id)
                    if known_signal != current_signal:
                        self._known_signal[block_id] = current_signal
                        logger.info("Signal %d state updated from model -> %s", block_id, current_signal)
                        state_changed = True
                if hasattr(segment, 'current_position'):
                    current_pos = int(segment.current_position)
                    known_pos = self.switches.get(block_id)
                    if known_pos != current_pos:
                        self.switches[block_id] = current_pos
                        logger.info("Switch %d position updated from model -> %d", block_id, current_pos)
                        state_changed = True
                if hasattr(segment, 'gate_status'):
                    current_gate = bool(segment.gate_status)
                    for cid, cblock in self.crossing_blocks.items():
                        if cblock == block_id:
                            known_state = self.crossings.get(cid)
                            if known_state != current_gate:
                                self.crossings[cid] = current_gate
                                logger.info("Crossing %d status updated from model -> %s", cid, current_gate)
                                state_changed = True
                if hasattr(segment, 'active_command') and segment.active_command:
                    cmd = segment.active_command
                    if hasattr(cmd, 'commanded_speed') and cmd.commanded_speed:
                        speed_mps = int(cmd.commanded_speed)
                        known_speed = self._known_commanded_speed.get(block_id)
                        if known_speed != speed_mps:
                            self._commanded_speed_mps[block_id] = speed_mps
                            self._known_commanded_speed[block_id] = speed_mps
                            logger.debug("Block %d commanded speed synced: %d m/s", block_id, speed_mps)
                    if hasattr(cmd, 'authority') and cmd.authority:
                        auth_m = int(cmd.authority)
                        known_auth = self._known_commanded_auth.get(block_id)
                        if known_auth != auth_m:
                            self._commanded_auth_m[block_id] = auth_m
                            self._known_commanded_auth[block_id] = auth_m
                            logger.debug("Block %d commanded authority synced: %d m", block_id, auth_m)
            except Exception as e:
                logger.debug("Error polling block %d: %s", block_id, e)
                continue
        if state_changed:
            self._notify_listeners()
            self._send_status_to_ctc()

    def _line_block_ids(self) -> List[int]:
        rng = LINE_BLOCK_MAP.get(self.line_name)
        if rng is None:
            return sorted(self.track_model.segments.keys())
        return [b for b in rng if b in self.track_model.segments]
    
    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug("Added listener %r for %s", callback, self.line_name)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        try:
            self._listeners.remove(callback)
            logger.debug("Removed listener %r for %s", callback, self.line_name)
        except ValueError:
            logger.debug("Listener %r not registered for %s", callback, self.line_name)

    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener %r raised exception while notifying", cb)

    def set_maintenance_mode(self, enabled: bool) -> None:
        self.maintenance_mode = bool(enabled)
        logger.info("%s: maintenance mode -> %s", self.line_name, self.maintenance_mode)
        self._notify_listeners()

    def _get_segment(self, block: int) -> TrackNetwork:
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
            if b not in self.track_model.segments:
                continue
            if b in self._known_occupancy:
                occupied_val = bool(self._known_occupancy[b])
            else:
                occupied_val = "N/A"
            suggested_speed_mps = self._suggested_speed_mps.get(b, 0.0)
            suggested_auth_m = self._suggested_auth_m.get(b, 0.0)
            suggested_speed_mph = ConversionFunctions.mps_to_mph(suggested_speed_mps)
            suggested_auth_yd = ConversionFunctions.meters_to_yards(suggested_auth_m)
            if b in self._commanded_speed_mps or b in self._known_commanded_speed:
                commanded_speed_mps = self._commanded_speed_mps.get(b) or self._known_commanded_speed.get(b, 0)
                commanded_speed_mph = ConversionFunctions.mps_to_mph(commanded_speed_mps)
                commanded_speed_mph = int(math.ceil(commanded_speed_mph))
            else:
                commanded_speed_mph = "N/A"
            if b in self._commanded_auth_m or b in self._known_commanded_auth:
                commanded_auth_m = self._commanded_auth_m.get(b) or self._known_commanded_auth.get(b, 0)
                commanded_auth_yd = ConversionFunctions.meters_to_yards(commanded_auth_m)
                commanded_auth_yd = int(math.ceil(commanded_auth_yd))
            else:
                commanded_auth_yd = "N/A"
            if b in self._known_signal:
                signal_val = self._known_signal[b]
            else:
                signal_val = "N/A"
            d[b] = {
                "occupied": occupied_val,
                "suggested_speed": int(round(suggested_speed_mph)),
                "suggested_auth": int(round(suggested_auth_yd)),
                "commanded_speed": commanded_speed_mph,
                "commanded_auth": commanded_auth_yd,
                "signal": signal_val,
            }
        return d
    
    @property
    def num_blocks(self) -> int:
        return len(self._line_block_ids())

    def set_block_occupancy(self, block: int, status: bool) -> None:
        seg = self._get_segment(block)
        seg.set_occupancy(bool(status))
        self._known_occupancy[block] = bool(status)
        logger.info("%s: Block %d occupancy -> %s", self.line_name, block, status)
        self._notify_listeners()
        self._send_status_to_ctc()

    def set_signal(self, block: int, color: str | SignalState) -> None:
        if isinstance(color, SignalState):
            state = color
        else:
            try:
                enum_name = str(color).replace(" ", "").upper()
                state = SignalState[enum_name]
            except Exception:
                raise ValueError(f"Invalid signal color '{color}'")
        self._known_signal[block] = state
        try:
            self.track_model.set_signal_state(block, state)
            logger.info("Sent to Track Model: Block %d signal -> %s", 
                    block, state.name)
        except Exception as e:
            logger.warning("Failed to set signal %d in Track Model: %s", block, e)
        self._notify_listeners()
        self._send_status_to_ctc()

    def safe_set_switch(self, switch_id: int, position: int | str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")
        if isinstance(position, str):
            pos_str = position.title()
            if pos_str == "Normal":
                pos_int = 0
            elif pos_str == "Alternate":
                pos_int = 1
            else:
                raise ValueError("Invalid switch position")
        else:
            pos_int = int(position)
            if pos_int not in (0, 1):
                raise ValueError("Invalid switch position. Must be 0 or 1.")
        blocks = self.switch_map.get(switch_id)
        if not blocks and switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if hasattr(seg, 'straight_segment') and hasattr(seg, 'diverging_segment'):
                blocks = tuple(b.block_id for b in 
                            (seg.straight_segment, seg.diverging_segment) if b is not None)
                self.switch_map[switch_id] = blocks
        if blocks:
            for b in blocks:
                if b in self.track_model.segments:
                    if getattr(self.track_model.segments[b], 'occupied', False):
                        raise SafetyException(f"Cannot change switch {switch_id}: block {b} occupied")
        self.switches[switch_id] = pos_int
        try:
            self.track_model.set_switch_position(switch_id, pos_int)
            logger.info("Sent to Track Model: Switch %d -> %d", switch_id, pos_int)
        except Exception as e:
            logger.warning("Failed to set switch %d in Track Model: %s", switch_id, e)
        self._notify_listeners()
        self._send_status_to_ctc()

    def safe_set_crossing(self, crossing_id: int, status: bool | str) -> None:
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")
        if isinstance(status, str):
            stat_str = status.title()
            if stat_str == "Active":
                stat_bool = True
            elif stat_str == "Inactive":
                stat_bool = False
            else:
                raise ValueError("Invalid crossing status")
        else:
            stat_bool = bool(status)
        block = self.crossing_blocks.get(crossing_id)
        if block and block in self.track_model.segments:
            if getattr(self.track_model.segments[block], 'occupied', False):
                if not stat_bool:
                    raise SafetyException(f"Cannot set crossing {crossing_id} inactive you dumb ass: block {block} occupied")
        self.crossings[crossing_id] = stat_bool
        if block:
            try:
                self.track_model.set_gate_status(block, stat_bool)
                logger.info("Track Model: Crossing %d (block %d): %s", crossing_id, block, stat_bool)
            except Exception as e:
                logger.warning("Failed to set crossing %d: %s", crossing_id, e)
        self._notify_listeners()
        self._send_status_to_ctc()

    def set_time(self, new_time: datetime) -> None:
        self.time = new_time
        self._notify_listeners()

    def manual_set_time(self, year: int, month: int, day: int, hour: int, minute: int, second: int) -> None:
        self.time = datetime(year, month, day, hour, minute, second)
        logger.info("%s: Time manually set to %s", self.line_name, self.time.strftime("%Y-%m-%d %H:%M:%S"))
        self._notify_listeners()
    
    def _plc_set_switch(self, switch_id: int, position: int) -> None:
        if isinstance(position, str):
            pos_str = position.title()
            pos_int = 0 if pos_str == "Normal" else 1
        else:
            pos_int = int(position)
        self.switches[switch_id] = pos_int
        try:
            self.track_model.set_switch_position(switch_id, pos_int)
            logger.info("PLC set switch %d -> %d", switch_id, pos_int)
        except Exception as e:
            logger.warning("Failed to set switch %d in Track Model: %s", switch_id, e)

    def _plc_set_crossing(self, crossing_id: int, status: bool) -> None:
        if isinstance(status, str):
            stat_bool = True if status.title() == "Active" else False
        else:
            stat_bool = bool(status)
        self.crossings[crossing_id] = stat_bool
        block = self.crossing_blocks.get(crossing_id)
        if block:
            try:
                self.track_model.set_gate_status(block, stat_bool)
                logger.info("PLC set crossing %d (block %d): %s", crossing_id, block, stat_bool)
            except Exception as e:
                logger.warning("Failed to set crossing %d: %s", crossing_id, e)