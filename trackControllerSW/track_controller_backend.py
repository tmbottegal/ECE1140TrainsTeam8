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
        
        self._initialize_infrastructure()
        self._initial_sync()

    def _initialize_infrastructure(self) -> None:
        """Initialize switch and crossing mappings based on line."""
        if self.line_name == "Blue Line":
            self.switch_map[1] = (5, 6, 11)
            self.crossing_blocks[1] = 3
        elif self.line_name == "Red Line":
            self.switch_map[1] = (15, 16, 1)
            self.switch_map[2] = (27, 28, 76)
            self.switch_map[3] = (32, 33, 72)
            self.switch_map[4] = (38, 39, 71)
            self.switch_map[5] = (43, 44, 67)
            self.switch_map[6] = (52, 53, 66)
            self.crossing_blocks[1] = 11
        elif self.line_name == "Green Line":
            self.switch_map[1] = (12, 13, 1)
            self.switch_map[2] = (28, 29, 150)
            self.switch_map[3] = (76, 77, 101)
            self.switch_map[4] = (85, 86, 100)
            self.crossing_blocks[1] = 19
        
        for sid in self.switch_map:
            self.switches[sid] = "Normal"
        for cid in self.crossing_blocks:
            self.crossings[cid] = "Inactive"

    def _initial_sync(self) -> None:
        """Perform initial synchronization with track model on startup."""
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
                    
                    # Sync occupancy
                    if "occupied" in info:
                        self._known_occupancy[bid] = bool(info["occupied"])
                        logger.debug("Synced block %d occupancy: %s", bid, info["occupied"])
                    
                    # Sync signal state
                    if "signal_state" in info:
                        self._known_signal[bid] = info["signal_state"]
                        logger.debug("Synced block %d signal: %s", bid, info["signal_state"])
                    
                    # Sync switch positions
                    if "current_position" in info and bid in self.switches:
                        pos = info.get("current_position")
                        self.switches[bid] = "Normal" if pos == 0 else "Alternate"
                        logger.debug("Synced switch %d position: %s", bid, self.switches[bid])
                    
                    # Sync crossing status
                    if "gate_status" in info:
                        for cid, cblock in self.crossing_blocks.items():
                            if cblock == bid:
                                self.crossings[cid] = "Active" if info["gate_status"] else "Inactive"
                                logger.debug("Synced crossing %d status: %s", cid, self.crossings[cid])
            
            logger.info("Initial sync completed for %s", self.line_name)
        except Exception:
            logger.exception("Failed to perform initial sync with track model")

    def receive_model_update(self, block_id: int, attribute: str, value: Any) -> None:
        """Receive an update from the Track Model."""
        msg = TrackModelMessage(block_id, attribute, value)
        self.incoming_messages.append(msg)
        logger.info("Received Track Model update: block=%d, attr=%s, value=%s", 
                   block_id, attribute, value)
        self._process_next_model_message()

    def _process_next_model_message(self) -> None:
        """Process the next message from Track Model queue."""
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
                pos = "Normal" if msg.value == 0 else "Alternate"
                self.switches[msg.block_id] = pos
                logger.info("Switch %d position updated from model -> %s", msg.block_id, pos)
            case "crossing":
                stat = "Active" if msg.value else "Inactive"
                for cid, cblock in self.crossing_blocks.items():
                    if cblock == msg.block_id:
                        self.crossings[cid] = stat
                logger.info("Crossing at block %d status updated from model -> %s", 
                           msg.block_id, stat)
            case _:
                logger.warning("Unknown Track Model attribute: %s", msg.attribute)
        self._notify_listeners()

    def _update_occupancy_from_model(self, block_id: int, occupied: bool) -> None:
        """Update occupancy state from track model and handle side effects."""
        old_state = self._known_occupancy.get(block_id)
        self._known_occupancy[block_id] = occupied
        logger.info("%s: Block %d occupancy updated from model -> %s", 
                   self.line_name, block_id, occupied)

        if old_state == occupied:
            return

        for cid, cblock in self.crossing_blocks.items():
            if cblock == block_id:
                try:
                    seg = self.track_model.segments.get(block_id)
                    if seg and isinstance(seg, LevelCrossing):
                        seg.set_gate_status(occupied)
                        self.crossings[cid] = "Active" if occupied else "Inactive"
                        logger.info("Auto-managed crossing %d gates: %s (block %d occupancy=%s)", 
                                   cid, self.crossings[cid], block_id, occupied)
                except Exception:
                    logger.exception("Failed to auto-update crossing gate for block %d", block_id)
        
        if occupied:
            # When block becomes occupied, set authority to 0
            if block_id in self._commanded_auth_yd:
                self._commanded_auth_yd[block_id] = 0
                self._known_commanded_auth[block_id] = 0
        else:
            # When block clears, restore suggested authority
            suggested_auth = self._suggested_auth_yd.get(block_id, 50)
            self._commanded_auth_yd[block_id] = suggested_auth
            self._known_commanded_auth[block_id] = suggested_auth

    def start_live_link(self, poll_interval: float = 1.0) -> None:
        """Start live polling of Track Model for state updates."""
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

        thread = threading.Thread(target=_poll_loop, daemon=True, 
                                 name=f"TrackPoll-{self.line_name}")
        thread.start()
        logger.info("Live link started for %s (poll interval: %.1fs)", 
                   self.line_name, poll_interval)

    def stop_live_link(self) -> None:
        """Stop live polling of Track Model."""
        self._live_thread_running = False
        logger.info("Live link stopped for %s", self.line_name)

    def _poll_track_model(self) -> None:
        """Poll track model for status updates."""
        if not hasattr(self.track_model, "get_wayside_status"):
            return
            
        try:
            status_snapshot = self.track_model.get_wayside_status()
        except Exception:
            logger.exception("Failed to retrieve wayside status from TrackModel")
            return
        
        if isinstance(status_snapshot, dict) and "segments" in status_snapshot:
            segments = status_snapshot.get("segments", {})
        elif isinstance(status_snapshot, dict):
            segments = status_snapshot
        else:
            logger.warning("Unexpected wayside status format: %r", type(status_snapshot))
            return

        for block_id, info in segments.items():
            try:
                bid = int(block_id)
            except Exception:
                continue
                
            if bid not in self._line_block_ids():
                continue

            if not isinstance(info, dict):
                continue

            # Check occupancy changes
            occ = info.get("occupied") if "occupied" in info else info.get("occupancy")
            if occ is not None:
                occ_bool = bool(occ)
                if self._known_occupancy.get(bid) != occ_bool:
                    self.receive_model_update(bid, "occupancy", occ_bool)

            # Check signal changes
            sig = info.get("signal_state") if "signal_state" in info else info.get("signal")
            if sig is not None:
                if self._known_signal.get(bid) != sig:
                    self.receive_model_update(bid, "signal", sig)

            # Check switch position changes
            if "current_position" in info and bid in self.switches:
                pos = info.get("current_position")
                pos_str = "Normal" if pos == 0 else "Alternate"
                if self.switches.get(bid) != pos_str:
                    self.receive_model_update(bid, "switch", pos)

            # Check crossing gate changes
            if "gate_status" in info:
                gate = bool(info.get("gate_status"))
                for cid, cblock in self.crossing_blocks.items():
                    if cblock == bid:
                        state_str = "Active" if gate else "Inactive"
                        if self.crossings.get(cid) != state_str:
                            self.receive_model_update(bid, "crossing", gate)

    def _line_block_ids(self) -> List[int]:
        """Get list of block IDs for this line."""
        rng = LINE_BLOCK_MAP.get(self.line_name)
        if rng is None:
            return sorted(self.track_model.segments.keys())
        return [b for b in rng if b in self.track_model.segments]
    
    def add_listener(self, callback: Callable[[], None]) -> None:
        """Add a listener callback for state changes."""
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug("Added listener %r for %s", callback, self.line_name)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        """Remove a listener callback."""
        try:
            self._listeners.remove(callback)
            logger.debug("Removed listener %r for %s", callback, self.line_name)
        except ValueError:
            logger.debug("Listener %r not registered for %s", callback, self.line_name)

    def _notify_listeners(self) -> None:
        """Notify all registered listeners of state changes."""
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener %r raised exception while notifying", cb)

    def set_maintenance_mode(self, enabled: bool) -> None:
        """Enable or disable maintenance mode."""
        self.maintenance_mode = bool(enabled)
        logger.info("%s: maintenance mode -> %s", self.line_name, self.maintenance_mode)
        self._notify_listeners()

    def _get_segment(self, block: int) -> TrackSegment:
        """Get segment from track model with validation."""
        seg = self.track_model.segments.get(block)
        if seg is None:
            raise ValueError(f"Invalid block {block}")
        if block not in self._line_block_ids():
            raise ValueError(f"Block {block} is not part of {self.line_name}")
        return seg

    @property
    def blocks(self) -> Dict[int, Dict[str, object]]:
        """Get dictionary of all blocks and their states."""
        d: Dict[int, Dict[str, object]] = {}
        for b in self._line_block_ids():
            if b not in self.track_model.segments:
                continue
                
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
        """Get number of blocks in this line."""
        return len(self._line_block_ids())

    def set_block_occupancy(self, block: int, status: bool) -> None:
        """Set occupancy for a block (typically called from model updates)."""
        seg = self._get_segment(block)
        seg.set_occupancy(bool(status))
        self._known_occupancy[block] = bool(status)
        logger.info("%s: Block %d occupancy -> %s", self.line_name, block, status)
        self._notify_listeners()

    def set_signal(self, block: int, color: str | SignalState) -> None:
        """Set signal state for a block and send to Track Model."""
        seg = self._get_segment(block)
        
        if isinstance(color, SignalState):
            state = color
        else:
            try:
                enum_name = str(color).replace(" ", "").upper()
                state = SignalState[enum_name]
            except Exception:
                raise ValueError(f"Invalid signal color '{color}'")
        
        # Send to Track Model
        seg.set_signal_state(state)
        self._known_signal[block] = state
        logger.info("%s: Block %d signal -> %s (sent to Track Model)", 
                   self.line_name, block, state.name)
        self._notify_listeners()

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        """Set switch position (maintenance mode only)."""
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")
            
        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position")
        
        # Get blocks controlled by this switch
        blocks = self.switch_map.get(switch_id)
        if not blocks and switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if isinstance(seg, TrackSwitch):
                blocks = tuple(b.block_id for b in (seg.straight_segment, seg.diverging_segment) if b is not None)
                self.switch_map[switch_id] = blocks
        
        # Safety check: no controlled blocks can be occupied
        if blocks:
            for b in blocks:
                if b in self.track_model.segments and self.track_model.segments[b].occupied:
                    raise SafetyException(f"Cannot change switch {switch_id}: block {b} occupied")
        
        # Send command to Track Model
        if switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if isinstance(seg, TrackSwitch):
                idx = 0 if pos == "Normal" else 1
                seg.set_switch_position(idx)
                logger.info("%s: Switch %d -> %s (sent to Track Model)", 
                           self.line_name, switch_id, pos)
            else:
                logger.warning("Block %d is not a TrackSwitch", switch_id)
        else:
            logger.info("%s: Switch id %d not in model; storing state only", 
                       self.line_name, switch_id)
        
        self.switches[switch_id] = pos
        self._notify_listeners()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        """Set crossing status (maintenance mode only)."""
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")
            
        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status")
        
        # Get block for this crossing
        block = self.crossing_blocks.get(crossing_id)
        
        # Safety check: cannot open gates if block is occupied
        if block and self.track_model.segments.get(block):
            if self.track_model.segments[block].occupied and stat == "Inactive":
                raise SafetyException(
                    f"Cannot set crossing {crossing_id} Inactive: block {block} occupied")
        
        # Send command to Track Model
        if block and block in self.track_model.segments:
            seg = self.track_model.segments[block]
            if isinstance(seg, LevelCrossing):
                closed = (stat == "Active")
                seg.set_gate_status(closed)
                logger.info("%s: Crossing %d (block %d) -> %s (sent to Track Model)", 
                           self.line_name, crossing_id, block, stat)
            else:
                logger.warning("Block %d is not a LevelCrossing", block)
        
        self.crossings[crossing_id] = stat
        self._notify_listeners()

    def receive_ctc_suggestion(self, block: int, suggested_speed_mph: int, 
                              suggested_auth_yd: int) -> None:
        """Receive suggested speed and authority from CTC."""
        if block in self.track_model.segments and block in self._line_block_ids():
            self._suggested_speed_mph[block] = int(suggested_speed_mph)
            self._suggested_auth_yd[block] = int(suggested_auth_yd)
            logger.info("CTC suggestion for block %d: speed=%d mph, auth=%d yd", 
                       block, suggested_speed_mph, suggested_auth_yd)
            self._notify_listeners()
        else:
            logger.warning("CTC suggestion for invalid block %d", block)

    def set_commanded_speed(self, block_id: int, speed_mph: int) -> None:
        """Set commanded speed and send to Track Model."""
        if block_id not in self._line_block_ids():
            logger.warning("Cannot set commanded speed: block %d not in %s", 
                          block_id, self.line_name)
            return
            
        self._commanded_speed_mph[block_id] = speed_mph
        self._known_commanded_speed[block_id] = speed_mph
        logger.info("[%s] Commanded speed -> block %d = %d mph", 
                   self.line_name, block_id, speed_mph)

        try:
            # Convert mph to m/s and send to Track Model
            speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
            auth_yd = self._commanded_auth_yd.get(block_id, 0)
            auth_meters = ConversionFunctions.yards_to_meters(auth_yd)
            
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(auth_meters))
            
            logger.info("Sent train command to Track Model: block %d, speed=%d m/s, auth=%d m", 
                       block_id, int(speed_mps), int(auth_meters))
        except Exception as e:
            logger.warning("Track Model rejected commanded speed for block %d: %s", 
                          block_id, e)

        self._notify_listeners()

    def set_commanded_authority(self, block_id: int, yards: int) -> None:
        """Set commanded authority and send to Track Model."""
        if block_id not in self._line_block_ids():
            logger.warning("Cannot set commanded authority: block %d not in %s", 
                          block_id, self.line_name)
            return
            
        self._commanded_auth_yd[block_id] = yards
        self._known_commanded_auth[block_id] = yards
        logger.info("[%s] Commanded authority -> block %d = %d yd", 
                   self.line_name, block_id, yards)

        try:
            # Convert yards to meters and send to Track Model
            speed_mph = self._commanded_speed_mph.get(block_id, 0)
            speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
            auth_meters = ConversionFunctions.yards_to_meters(yards)
            
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(auth_meters))
            
            logger.info("Sent train command to Track Model: block %d, speed=%d m/s, auth=%d m", 
                       block_id, int(speed_mps), int(auth_meters))
        except Exception as e:
            logger.warning("Track Model rejected commanded authority for block %d: %s", 
                          block_id, e)

        self._notify_listeners()

    def relay_to_train_model(self, block: int) -> TrainCommand:
        """Get the current train command for a block (for Train Model to query)."""
        if block not in self.track_model.segments or block not in self._line_block_ids():
            raise ValueError("Invalid block")
            
        speed_mph = int(self._commanded_speed_mph.get(block, 0))
        auth_yd = int(self._commanded_auth_yd.get(block, 0))
        speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
        auth_meters = ConversionFunctions.yards_to_meters(auth_yd)
        
        return TrainCommand(commanded_speed=int(speed_mps), authority=int(auth_meters))

    def upload_plc(self, filepath: str) -> None:
        """Upload and execute PLC file."""
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to upload PLC")
        
        ext = os.path.splitext(filepath)[1].lower()
        logger.info("Uploading PLC file: %s", filepath)
        
        if ext == ".py":
            self._upload_plc_python(filepath)
        else:
            self._upload_plc_text(filepath)
        
        # After PLC upload, sync states and notify
        self._sync_after_plc_upload()
        self._notify_listeners()
        logger.info("PLC upload completed for %s", self.line_name)

    def _upload_plc_python(self, filepath: str) -> None:
        """Handle Python PLC file upload."""
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
                # Occupancy: block_<id>_occupied
                if lname.startswith("block_") and "_occupied" in lname:
                    parts = lname.split("_")
                    if len(parts) >= 3:
                        block_id = int(parts[1])
                        if block_id in self._line_block_ids():
                            self.set_block_occupancy(block_id, bool(value))
                    continue
                
                # Switch: switch_<id>
                if lname.startswith("switch_"):
                    sid = int(lname.split("_")[1])
                    if sid in self.switches:
                        if isinstance(value, bool):
                            pos = "Normal" if value else "Alternate"
                        else:
                            pos = str(value).title()
                        self.safe_set_switch(sid, pos)
                    continue

                # Crossing: crossing_<id>
                if lname.startswith("crossing_"):
                    cid = int(lname.split("_")[1])
                    if cid in self.crossings:
                        if isinstance(value, bool):
                            status = "Active" if value else "Inactive"
                        else:
                            status = str(value).title()
                        self.safe_set_crossing(cid, status)
                    continue

                # Commanded speed
                if lname.startswith("commanded_speed_") or lname.startswith("cmd_speed_"):
                    block_id = int(lname.split("_")[-1])
                    if block_id in self._line_block_ids():
                        self.set_commanded_speed(block_id, int(value))
                    continue

                # Commanded authority
                if (lname.startswith("commanded_auth_") or 
                    lname.startswith("cmd_auth_") or 
                    lname.startswith("commanded_authority_")):
                    block_id = int(lname.split("_")[-1])
                    if block_id in self._line_block_ids():
                        self.set_commanded_authority(block_id, int(value))
                    continue

                # Signal
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
        """Handle text PLC file upload."""
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
                        self.safe_set_switch(sid, parts[2])
                        
                elif cmd == "CROSSING" and len(parts) >= 3:
                    cid = int(parts[1])
                    if cid in self.crossings:
                        self.safe_set_crossing(cid, parts[2])
                        
                elif cmd == "SIGNAL" and len(parts) >= 3:
                    bid = int(parts[1])
                    if bid in self._line_block_ids():
                        self.set_signal(bid, parts[2])
                    else:
                        logger.debug("TXT PLC SIGNAL for block %d ignored (not part of %s)", 
                                   bid, self.line_name)
                        
                elif cmd == "CMD_SPEED" and len(parts) >= 3:
                    bid = int(parts[1])
                    if bid in self._line_block_ids():
                        self.set_commanded_speed(bid, int(parts[2]))
                    else:
                        logger.debug("TXT PLC CMD_SPEED for block %d ignored (not part of %s)", 
                                   bid, self.line_name)
                        
                elif cmd == "CMD_AUTH" and len(parts) >= 3:
                    bid = int(parts[1])
                    if bid in self._line_block_ids():
                        self.set_commanded_authority(bid, int(parts[2]))
                    else:
                        logger.debug("TXT PLC CMD_AUTH for block %d ignored (not part of %s)", 
                                   bid, self.line_name)
                        
            except Exception:
                logger.exception("PLC line %d failed: %s", line_num, line)
                continue

    def _sync_after_plc_upload(self) -> None:
        """Synchronize all states after PLC upload."""
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
                    speed_mph = ConversionFunctions.mps_to_mph(speed_mps)
                    self._commanded_speed_mph[block_id] = int(speed_mph)
                    self._known_commanded_speed[block_id] = int(speed_mph)
                    
                if hasattr(cmd, 'authority') and cmd.authority:
                    auth_m = int(cmd.authority)
                    auth_yd = ConversionFunctions.meters_to_yards(auth_m)
                    self._commanded_auth_yd[block_id] = int(auth_yd)
                    self._known_commanded_auth[block_id] = int(auth_yd)

    def report_state(self) -> Dict[str, object]:
        """Generate comprehensive state report for UI or debugging."""
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
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "crossing": {
                cid: {
                    "block": self.crossing_blocks.get(cid), 
                    "status": status
                }
                for cid, status in self.crossings.items()
            },
        }