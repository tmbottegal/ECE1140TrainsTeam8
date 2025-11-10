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

@dataclass
class WaysideStatusUpdate:
    """Status update sent to CTC."""
    block_id: int
    occupied: bool
    signal_state: SignalState
    switch_position: str | None = None
    crossing_status: str | None = None

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
        # State tracking
        self._known_occupancy: Dict[int, bool] = {}
        self._known_signal: Dict[int, SignalState] = {}
        self._known_commanded_speed: Dict[int, int] = {}
        self._known_commanded_auth: Dict[int, int] = {}
        # Track Model message queue
        self.incoming_messages: deque[TrackModelMessage] = deque()
        self._live_thread_running: bool = False
        # CTC Integration
        self.ctc_backend = None  # Reference to CTC backend
        self._ctc_update_enabled: bool = True  # Can be disabled if needed for
        
        self._initialize_infrastructure()
        self._initial_sync()
    
    def set_ctc_backend(self, ctc_backend: Any) -> None:
        """
        Set reference to CTC backend for bidirectional communication.
        
        Args:
            ctc_backend: Reference to CTC backend instance
        """
        self.ctc_backend = ctc_backend
        logger.info("%s: CTC backend connected", self.line_name)
    
    def enable_ctc_updates(self, enabled: bool = True) -> None:
        """Enable or disable automatic updates to CTC."""
        self._ctc_update_enabled = enabled
        logger.info("%s: CTC updates %s", self.line_name, 
                   "enabled" if enabled else "disabled")
    
    def receive_ctc_suggestion(self, block: int, suggested_speed_mps: float, 
                              suggested_auth_m: float) -> None:
        """ (ADDED FOR GRACE)
        Args:
            block: Block number
            suggested_speed_mps: Suggested speed in meters per second (from CTC)
            suggested_auth_m: Suggested authority in meters (from CTC)
        """
        if block not in self._line_block_ids():
            logger.warning("CTC suggestion for invalid block %d on %s", 
                         block, self.line_name)
            return
        
        # Convert from CTC units (m/s, meters) to Wayside units (mph, yards)
        suggested_speed_mph = ConversionFunctions.mps_to_mph(suggested_speed_mps)
        suggested_auth_yd = ConversionFunctions.meters_to_yards(suggested_auth_m)
        
        # Round to integers for display
        suggested_speed_mph = int(round(suggested_speed_mph))
        suggested_auth_yd = int(round(suggested_auth_yd))
        
        # Store the suggestions
        self._suggested_speed_mph[block] = suggested_speed_mph
        self._suggested_auth_yd[block] = suggested_auth_yd
        
        logger.info(
            "%s: CTC suggestion for block %d: %.2f m/s → %d mph, %.2f m → %d yd",
            self.line_name, block, suggested_speed_mps, suggested_speed_mph,
            suggested_auth_m, suggested_auth_yd
        )
        
        self._notify_listeners()
    
    def _send_status_to_ctc(self) -> None:
        """
        Send current wayside status to CTC.
        Sends: occupancy, signal state, switch positions, crossing status.
    
        WaysideStatusUpdate is a list that sends the value
        """
        if not self._ctc_update_enabled or self.ctc_backend is None:
            return
        
        status_updates: List[WaysideStatusUpdate] = []
        
        # Collect status for all blocks
        for block_id in self._line_block_ids():
            if block_id not in self.track_model.segments:
                continue
            
            # Get occupancy
            occupied = self._known_occupancy.get(block_id, False)
            
            # Get signal state
            signal = self._known_signal.get(block_id, SignalState.RED)
            
            # Check if this block has a switch
            switch_pos = None
            if block_id in self.switches:
                switch_pos = self.switches[block_id]
            
            # Check if this block has a crossing
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
        
        # Send to CTC
        try:
            if hasattr(self.ctc_backend, 'receive_wayside_status'):
                # Batch update
                self.ctc_backend.receive_wayside_status(self.line_name, status_updates)
                logger.debug("%s: Sent %d status updates to CTC", 
                           self.line_name, len(status_updates))
            else:
                # Individual updates
                for status in status_updates:
                    self._send_single_status_to_ctc(status)
        except Exception:
            logger.exception("%s: Failed to send status to CTC", self.line_name)
    
    def _send_single_status_to_ctc(self, status: WaysideStatusUpdate) -> None:
        """Send a single status update to CTC."""
        if self.ctc_backend is None:
            return
        
        try:
            # Update occupancy
            if hasattr(self.ctc_backend, 'update_block_occupancy'):
                self.ctc_backend.update_block_occupancy(
                    self.line_name, status.block_id, status.occupied
                )
            
            # Update signal state
            if hasattr(self.ctc_backend, 'update_signal_state'):
                self.ctc_backend.update_signal_state(
                    self.line_name, status.block_id, status.signal_state
                )
            
            # Update switch position
            if status.switch_position and hasattr(self.ctc_backend, 'update_switch_position'):
                self.ctc_backend.update_switch_position(
                    self.line_name, status.block_id, status.switch_position
                )
            
            # Update crossing status
            if status.crossing_status and hasattr(self.ctc_backend, 'update_crossing_status'):
                self.ctc_backend.update_crossing_status(
                    self.line_name, status.block_id, status.crossing_status
                )
        except Exception:
            logger.exception("%s: Failed to send single status for block %d", 
                           self.line_name, status.block_id)

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
                    
                    if "occupied" in info:
                        self._known_occupancy[bid] = bool(info["occupied"])
                        logger.debug("Synced block %d occupancy: %s", bid, info["occupied"])
                    
                    if "signal_state" in info:
                        self._known_signal[bid] = info["signal_state"]
                        logger.debug("Synced block %d signal: %s", bid, info["signal_state"])
                    
                    if "current_position" in info and bid in self.switches:
                        pos = info.get("current_position")
                        self.switches[bid] = "Normal" if pos == 0 else "Alternate"
                        logger.debug("Synced switch %d position: %s", bid, self.switches[bid])
                    
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
        self._send_status_to_ctc()  # Send update to CTC

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
            if block_id in self._commanded_auth_yd:
                self._commanded_auth_yd[block_id] = 0
                self._known_commanded_auth[block_id] = 0
        else:
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
        """Poll track model for status updates with comprehensive state detection."""
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
                        logger.info("Signal %d state updated from model -> %s", 
                                block_id, current_signal)
                        state_changed = True
                
                if hasattr(segment, 'current_position'):
                    current_pos = segment.current_position
                    pos_str = "Normal" if current_pos == 0 else "Alternate"
                    known_pos = self.switches.get(block_id)
                    if known_pos != pos_str:
                        self.switches[block_id] = pos_str
                        logger.info("Switch %d position updated from model -> %s", 
                                block_id, pos_str)
                        state_changed = True
                
                if hasattr(segment, 'gate_status'):
                    current_gate = segment.gate_status
                    for cid, cblock in self.crossing_blocks.items():
                        if cblock == block_id:
                            state_str = "Active" if current_gate else "Inactive"
                            known_state = self.crossings.get(cid)
                            if known_state != state_str:
                                self.crossings[cid] = state_str
                                logger.info("Crossing %d status updated from model -> %s", 
                                        cid, state_str)
                                state_changed = True
                
                if hasattr(segment, 'active_command') and segment.active_command:
                    cmd = segment.active_command
                    
                    if hasattr(cmd, 'commanded_speed') and cmd.commanded_speed:
                        speed_mps = int(cmd.commanded_speed)
                        speed_mph = ConversionFunctions.mps_to_mph(speed_mps)
                        speed_mph = int(speed_mph)
                        
                        known_speed = self._known_commanded_speed.get(block_id)
                        if known_speed != speed_mph:
                            self._commanded_speed_mph[block_id] = speed_mph
                            self._known_commanded_speed[block_id] = speed_mph
                            logger.debug("Block %d commanded speed synced: %d mph", 
                                        block_id, speed_mph)
                    
                    if hasattr(cmd, 'authority') and cmd.authority:
                        auth_m = int(cmd.authority)
                        auth_yd = ConversionFunctions.meters_to_yards(auth_m)
                        auth_yd = int(auth_yd)
                        
                        known_auth = self._known_commanded_auth.get(block_id)
                        if known_auth != auth_yd:
                            self._commanded_auth_yd[block_id] = auth_yd
                            self._known_commanded_auth[block_id] = auth_yd
                            logger.debug("Block %d commanded authority synced: %d yd", 
                                        block_id, auth_yd)
            
            except Exception as e:
                logger.debug("Error polling block %d: %s", block_id, e)
                continue
        
        if state_changed:
            self._notify_listeners()
            self._send_status_to_ctc()  # Send updates to CTC

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
        """Set occupancy for a block."""
        seg = self._get_segment(block)
        seg.set_occupancy(bool(status))
        self._known_occupancy[block] = bool(status)
        logger.info("%s: Block %d occupancy -> %s", self.line_name, block, status)
        self._notify_listeners()
        self._send_status_to_ctc()

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
        
        self._known_signal[block] = state
        
        try:
            self.track_model.set_signal_state(block, state)
            logger.info("✓ Sent to Track Model: Block %d signal -> %s", 
                    block, state.name)
        except Exception as e:
            logger.warning("Failed to set signal %d in Track Model: %s", block, e)
        
        self._notify_listeners()
        self._send_status_to_ctc()

    def safe_set_switch(self, switch_id: int, position: str) -> None:
        """Set switch position (maintenance mode only)."""
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")
        
        pos = position.title()
        if pos not in ("Normal", "Alternate"):
            raise ValueError("Invalid switch position")
        
        blocks = self.switch_map.get(switch_id)
        if not blocks and switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if hasattr(seg, 'straight_segment') and hasattr(seg, 'diverging_segment'):
                blocks = tuple(b.block_id for b in 
                            (seg.straight_segment, seg.diverging_segment) 
                            if b is not None)
                self.switch_map[switch_id] = blocks
        
        if blocks:
            for b in blocks:
                if b in self.track_model.segments:
                    if getattr(self.track_model.segments[b], 'occupied', False):
                        raise SafetyException(
                            f"Cannot change switch {switch_id}: block {b} occupied")
        
        self.switches[switch_id] = pos
        
        try:
            idx = 0 if pos == "Normal" else 1
            self.track_model.set_switch_position(switch_id, idx)
            logger.info("✓ Sent to Track Model: Switch %d -> %s", switch_id, pos)
        except Exception as e:
            logger.warning("Failed to set switch %d in Track Model: %s", 
                        switch_id, e)
        
        self._notify_listeners()
        self._send_status_to_ctc()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        """Set crossing status (maintenance mode only)."""
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")
        
        stat = status.title()
        if stat not in ("Active", "Inactive"):
            raise ValueError("Invalid crossing status")
        
        block = self.crossing_blocks.get(crossing_id)
        
        if block and block in self.track_model.segments:
            if getattr(self.track_model.segments[block], 'occupied', False):
                if stat == "Inactive":
                    raise SafetyException(
                        f"Cannot set crossing {crossing_id} Inactive: block {block} occupied")
        
        self.crossings[crossing_id] = stat
        
        if block:
            try:
                closed = (stat == "Active")
                self.track_model.set_gate_status(block, closed)
                logger.info("✓ Sent to Track Model: Crossing %d (block %d) -> %s", 
                        crossing_id, block, stat)
            except Exception as e:
                logger.warning("Failed to set crossing %d in Track Model: %s", 
                            crossing_id, e)
        
        self._notify_listeners()
        self._send_status_to_ctc()

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
            speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
            auth_yd = self._commanded_auth_yd.get(block_id, 0)
            auth_meters = ConversionFunctions.yards_to_meters(auth_yd)
            
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(auth_meters))
            
            logger.info("✓ Sent to Track Model: block %d, speed=%d m/s, auth=%d m", 
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
            speed_mph = self._commanded_speed_mph.get(block_id, 0)
            speed_mps = ConversionFunctions.mph_to_mps(speed_mph)
            auth_meters = ConversionFunctions.yards_to_meters(yards)
            
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(auth_meters))
            
            logger.info("✓ Sent to Track Model: block %d, speed=%d m/s, auth=%d m", 
                    block_id, int(speed_mps), int(auth_meters))
            
        except Exception as e:
            logger.warning("Track Model rejected commanded authority for block %d: %s", 
                        block_id, e)
        
        self._notify_listeners()

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
        
        self._sync_after_plc_upload()
        self._notify_listeners()
        self._send_status_to_ctc()
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
                            pos = "Normal" if value else "Alternate"
                        else:
                            pos = str(value).title()
                        self.safe_set_switch(sid, pos)
                    continue

                if lname.startswith("crossing_"):
                    cid = int(lname.split("_")[1])
                    if cid in self.crossings:
                        if isinstance(value, bool):
                            status = "Active" if value else "Inactive"
                        else:
                            status = str(value).title()
                        self.safe_set_crossing(cid, status)
                    continue

                if lname.startswith("commanded_speed_") or lname.startswith("cmd_speed_"):
                    block_id = int(lname.split("_")[-1])
                    if block_id in self._line_block_ids():
                        self.set_commanded_speed(block_id, int(value))
                    continue

                if (lname.startswith("commanded_auth_") or 
                    lname.startswith("cmd_auth_") or 
                    lname.startswith("commanded_authority_")):
                    block_id = int(lname.split("_")[-1])
                    if block_id in self._line_block_ids():
                        self.set_commanded_authority(block_id, int(value))
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
    # Globel clock function add pls, day, hour, minute, second