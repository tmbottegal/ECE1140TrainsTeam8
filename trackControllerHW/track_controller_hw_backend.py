"""Hardware Track Controller Backend.

Manages block, switch, and crossing state for hardware wayside controllers.
Handles PLC upload, safety/fault detection, and CTC integration.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class SignalState(str, Enum):
    """Signal light states."""

    RED = "Red"
    YELLOW = "Yellow"
    GREEN = "Green"


class TrackSegment:
    """Represents a track block segment."""

    def __init__(self, block_id: int) -> None:
        self.block_id = block_id
        self.occupied = False
        self.signal_state: SignalState | str = "N/A"

    def set_occupancy(self, occ: bool) -> None:
        self.occupied = bool(occ)

    def set_signal_state(self, state: SignalState) -> None:
        self.signal_state = state


class TrackSwitch(TrackSegment):
    """Represents a track switch."""

    def __init__(self, block_id: int) -> None:
        super().__init__(block_id)
        self.current_position = 0

    def set_switch_position(self, pos: int) -> None:
        self.current_position = int(pos)


class LevelCrossing(TrackSegment):
    """Represents a level crossing."""

    def __init__(self, block_id: int) -> None:
        super().__init__(block_id)
        self.gate_status = False

    def set_gate_status(self, closed: bool) -> None:
        self.gate_status = bool(closed)


class TrackModelAdapter:
    """Minimal local track model for standalone operation."""

    def __init__(self) -> None:
        self.segments: dict[int, TrackSegment] = {}

    def ensure_blocks(self, ids: list[int]) -> None:
        for i in ids:
            if i not in self.segments:
                self.segments[i] = TrackSegment(i)

    def set_signal_state(self, block_id: int, state: SignalState) -> None:
        if seg := self.segments.get(block_id):
            seg.set_signal_state(state)

    def set_switch_position(self, switch_id: int, pos: int) -> None:
        logger.debug(
            "TrackModelAdapter.set_switch_position(%s, %s) [stub]", switch_id, pos
        )

    def set_gate_status(self, block_id: int, closed: bool) -> None:
        if seg := self.segments.get(block_id):
            if isinstance(seg, LevelCrossing):
                seg.set_gate_status(closed)
                return
        logger.debug(
            "TrackModelAdapter.set_gate_status(%s, %s) [stub]", block_id, closed
        )

    def broadcast_train_command(
        self, block_id: int, speed_mph: int, auth_yd: int
    ) -> None:
        logger.debug(
            "TrackModelAdapter.broadcast_train_command(block=%s, speed=%s, auth=%s) "
            "[stub]",
            block_id,
            speed_mph,
            auth_yd,
        )


HW_CONTROLLED_BLOCK_MAP: dict[str, range] = {
    "Blue Line": range(1, 1),
    "Red Line": range(35, 72),
    "Green Line": range(63, 122),
}

HW_VIEW_ONLY_BLOCK_MAP: dict[str, list[int]] = {
    "Red Line": list(range(24, 35)) + list(range(72, 77)),
    "Green Line": list(range(58, 63)) + list(range(122, 144)),
    "Blue Line": [],
}

HW_LINE_BLOCK_MAP: dict[str, range] = HW_CONTROLLED_BLOCK_MAP.copy()


@dataclass
class WaysideStatusUpdate:
    """Status update for a wayside block."""

    block_id: int
    occupied: bool | str
    signal_state: SignalState | str
    switch_position: Optional[str]
    crossing_status: Optional[str]


@dataclass
class FailureSnapshot:
    """Record of a detected failure."""

    kind: str
    block_id: Optional[int]
    time: datetime
    details: str
    cleared: bool = False


@dataclass
class ActuatorCommandCheck:
    """Pending actuator command verification."""

    block_id: int
    actuator: str
    expected: Any
    issued_at: datetime
    cleared: bool = False


class HardwareTrackControllerBackend:
    """Backend for hardware track controller operations."""

    def __init__(
        self, track_model: TrackModelAdapter, line_name: str = "Blue Line"
    ) -> None:
        self.track_model = track_model
        self.line_name = line_name
        self._listeners: list[Callable[[], None]] = []

        self.switches: dict[int, str] = {}
        self.switch_map: dict[int, tuple[int, ...]] = {}
        self.crossings: dict[int, str] = {}
        self.crossing_blocks: dict[int, int] = {}
        self._switch_signals: dict[tuple[int, int], SignalState] = {}
        self._init_default_infrastructure()

        self._known_occupancy: dict[int, bool] = {}
        self._known_signal: dict[int, SignalState] = {}
        self._suggested_speed_mph: dict[int, int] = {}
        self._suggested_auth_yd: dict[int, int] = {}
        self._commanded_speed_mph: dict[int, int] = {}
        self._commanded_auth_yd: dict[int, int] = {}

        self.failures: dict[str, FailureSnapshot] = {}
        self.failure_history: list[FailureSnapshot] = []
        self._previous_occupancy: dict[int, bool] = {}
        self._occupancy_timestamps: dict[int, datetime] = {}
        self._expected_stop_blocks: dict[int, datetime] = {}
        self._pending_actuator_checks: dict[str, ActuatorCommandCheck] = {}
        self._actuator_retry_count: dict[str, int] = {}
        self._command_timeout_sec: float = 5.0
        self._max_command_attempts: int = 3

        self._plc_logic_module: Any | None = None
        self._plc_prev_occupancy: dict[int, bool] = {}

        self.maintenance_mode: bool = False
        self._live_thread_running = False
        self._batch_updates = False

        self.ctc_backend: Any | None = None
        self._ctc_update_enabled: bool = True

        self.time: datetime = datetime(2000, 1, 1, 0, 0, 0)

        self._hw_blocks: list[int] = list(
            HW_CONTROLLED_BLOCK_MAP.get(self.line_name, [])
        )
        self._view_blocks: list[int] = list(
            HW_VIEW_ONLY_BLOCK_MAP.get(self.line_name, [])
        )
        self._line_blocks: list[int] = sorted(
            set(self._hw_blocks) | set(self._view_blocks)
        )

        self._guard_blocks: list[int] = []
        if self._hw_blocks:
            first, last = min(self._hw_blocks), max(self._hw_blocks)
            segments = getattr(self.track_model, "segments", {})
            if first - 1 in segments:
                self._guard_blocks.append(first - 1)
            if last + 1 in segments:
                self._guard_blocks.append(last + 1)
        self._guard_thread_running = False
        self._guard_poll_interval = 1.0

        if hasattr(self.track_model, "ensure_blocks"):
            try:
                self.track_model.ensure_blocks(self._line_blocks)
            except Exception:
                logger.exception("ensure_blocks failed")
        self._initial_sync()

    def _init_default_infrastructure(self) -> None:
        """Initialize switches and crossings for the line."""
        if self.line_name == "Green Line":
            self.switch_map = {77: (77, 78, 101), 85: (85, 86, 100)}
        elif self.line_name == "Red Line":
            self.switch_map = {38: (38, 39, 71), 43: (43, 44, 67), 52: (52, 53, 66)}

        for sid in self.switch_map:
            self.switches.setdefault(sid, "Straight")

        for sid in self.switch_map:
            self._switch_signals[(sid, 0)] = SignalState.RED
            self._switch_signals[(sid, 1)] = SignalState.RED
            self._switch_signals[(sid, 2)] = SignalState.RED

        if self.line_name == "Green Line":
            self.crossing_blocks.setdefault(1, 108)
            self.crossings.setdefault(1, "Inactive")
        elif self.line_name == "Red Line":
            self.crossing_blocks.setdefault(1, 47)
            self.crossings.setdefault(1, "Inactive")

    def _update_switch_signals(self) -> None:
        """Update switch signals based on current switch positions.

        Signal logic:
            - Previous signal (side 0): Always GREEN
            - Straight signal (side 1): GREEN if Straight, RED if Diverging
            - Diverging signal (side 2): GREEN if Diverging, RED if Straight
        """
        for switch_id in self.switch_map:
            pos = self.switches.get(switch_id, "Straight")
            if isinstance(pos, str):
                pos_int = 0 if pos == "Straight" else 1
            else:
                pos_int = int(pos)

            signal_state = SignalState.GREEN
            try:
                self.track_model.set_signal_state(switch_id, 0, signal_state)
                self._switch_signals[(switch_id, 0)] = signal_state
                logger.debug("Set switch %d previous signal: %s", switch_id, signal_state)
            except Exception:
                logger.exception("Failed to set switch %d previous signal", switch_id)

            signal_state = SignalState.GREEN if pos_int == 0 else SignalState.RED
            try:
                self.track_model.set_signal_state(switch_id, 1, signal_state)
                self._switch_signals[(switch_id, 1)] = signal_state
                logger.debug("Set switch %d straight signal: %s", switch_id, signal_state)
            except Exception:
                logger.exception("Failed to set switch %d straight signal", switch_id)

            signal_state = SignalState.GREEN if pos_int == 1 else SignalState.RED
            try:
                self.track_model.set_signal_state(switch_id, 2, signal_state)
                self._switch_signals[(switch_id, 2)] = signal_state
                logger.debug("Set switch %d diverging signal: %s", switch_id, signal_state)
            except Exception:
                logger.exception("Failed to set switch %d diverging signal", switch_id)

    def add_listener(self, cb: Callable[[], None]) -> None:
        """Add a state change listener."""
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        if self._batch_updates:
            return
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                logger.exception("Listener raised")

    def _begin_batch(self) -> None:
        """Start batching listener notifications."""
        self._batch_updates = True

    def _end_batch(self) -> None:
        """End batching and notify listeners once."""
        self._batch_updates = False
        self._notify_listeners()

    def set_ctc_backend(self, ctc_backend: Any) -> None:
        """Set the CTC backend for status updates."""
        self.ctc_backend = ctc_backend

    def enable_ctc_updates(self, enabled: bool = True) -> None:
        """Enable or disable CTC status updates."""
        self._ctc_update_enabled = bool(enabled)

    def receive_ctc_suggestion(
        self, block: int, suggested_speed_mps: float, suggested_auth_m: float
    ) -> None:
        """Receive speed and authority suggestion from CTC.

        Args:
            block: The block ID for the suggestion.
            suggested_speed_mps: Suggested speed in meters per second.
            suggested_auth_m: Suggested authority in meters.
        """
        b = int(block)

        if b not in self._line_blocks:
            logger.debug(
                "CTC suggestion for block %d ignored (not in %s territory)",
                b,
                self.line_name,
            )
            return

        speed_mph = float(suggested_speed_mps) * 2.23694
        self._suggested_speed_mph[b] = int(round(speed_mph))

        auth_yd = float(suggested_auth_m) * 1.09361
        self._suggested_auth_yd[b] = int(round(auth_yd))

        logger.info(
            "%s: CTC suggestion for block %d: %d mph, %d yd",
            self.line_name,
            b,
            self._suggested_speed_mph[b],
            self._suggested_auth_yd[b],
        )

        self._notify_listeners()

    def _send_status_to_ctc(self) -> None:
        """Send current status to CTC backend."""
        if not self.ctc_backend or not self._ctc_update_enabled:
            return

        updates = []
        for b in self.get_line_block_ids():
            occ = self._known_occupancy.get(b, "N/A")
            sig = self._known_signal.get(b, "N/A")

            switch_pos = next(
                (
                    self.switches.get(sid)
                    for sid, mapping in self.switch_map.items()
                    if b in mapping
                ),
                None,
            )
            crossing_status = next(
                (
                    self.crossings.get(cid)
                    for cid, blk in self.crossing_blocks.items()
                    if blk == b
                ),
                None,
            )

            updates.append(
                WaysideStatusUpdate(b, occ, sig, switch_pos, crossing_status)
            )

        try:
            if hasattr(self.ctc_backend, "receive_wayside_status"):
                self.ctc_backend.receive_wayside_status(self.line_name, updates)
            else:
                for u in updates:
                    self._send_single_status_to_ctc(u)
        except Exception:
            logger.exception("Error sending status to CTC")

    def _send_single_status_to_ctc(self, u: WaysideStatusUpdate) -> None:
        """Send a single block status update to CTC."""
        if not self.ctc_backend:
            return
        try:
            if hasattr(self.ctc_backend, "update_block_occupancy"):
                self.ctc_backend.update_block_occupancy(
                    self.line_name, u.block_id, u.occupied
                )
            if hasattr(self.ctc_backend, "update_signal_state"):
                self.ctc_backend.update_signal_state(
                    self.line_name, u.block_id, u.signal_state
                )
            if u.switch_position is not None and hasattr(
                self.ctc_backend, "update_switch_position"
            ):
                self.ctc_backend.update_switch_position(
                    self.line_name, u.block_id, u.switch_position
                )
            if u.crossing_status is not None and hasattr(
                self.ctc_backend, "update_crossing_status"
            ):
                self.ctc_backend.update_crossing_status(
                    self.line_name, u.block_id, u.crossing_status
                )
        except Exception:
            logger.exception("CTC single-status update failed")

    def _initial_sync(self) -> None:
        """Sync initial state from track model."""
        segments = getattr(self.track_model, "segments", {})
        if not isinstance(segments, dict):
            return

        changed = False
        for b in self._line_blocks:
            if seg := segments.get(b):
                occ = bool(getattr(seg, "occupied", False))
                if self._known_occupancy.get(b) != occ:
                    self._known_occupancy[b] = occ
                    changed = True

                if b not in self.switch_map:
                    sig = getattr(seg, "signal_state", "N/A")
                    if sig != "N/A" and self._known_signal.get(b) != sig:
                        self._known_signal[b] = sig
                        changed = True

        if changed:
            self._notify_listeners()
            self._send_status_to_ctc()

    def sync_from_track_model(self) -> None:
        """Force sync occupancy data from track model."""
        segments = getattr(self.track_model, "segments", {})
        if not isinstance(segments, dict):
            return

        for b in self._line_blocks:
            if seg := segments.get(b):
                self._known_occupancy[b] = bool(getattr(seg, "occupied", False))

                if b not in self.switch_map:
                    if hasattr(seg, "signal_state") and seg.signal_state:
                        self._known_signal[b] = seg.signal_state

        self._notify_listeners()

    def _on_occupancy_change(self, block_id: int, occupied: bool) -> None:
        """Handle block occupancy change."""
        previous = self._known_occupancy.get(block_id, False)
        self._known_occupancy[block_id] = occupied

        for crossing_id, blk in self.crossing_blocks.items():
            if blk == block_id:
                new_status = "Active" if occupied else "Inactive"
                if occupied or self.crossings.get(crossing_id) == "Active":
                    self.crossings[crossing_id] = new_status
                    try:
                        if hasattr(self.track_model, "set_gate_status"):
                            self.track_model.set_gate_status(blk, occupied)
                    except Exception:
                        logger.exception(
                            "Failed to set gate for crossing %s", crossing_id
                        )

        if occupied and block_id in self._commanded_auth_yd:
            self._commanded_auth_yd[block_id] = 0

        if previous != occupied:
            self._occupancy_timestamps[block_id] = self.time
            self._previous_occupancy[block_id] = previous

        self._check_broken_rail(block_id, occupied)
        self._check_track_circuit(block_id, previous, occupied)

        if self._plc_logic_module is not None:
            try:
                self._invoke_plc_logic()
            except Exception:
                logger.exception("PLC logic execution failed during occupancy change")

    def _record_failure(
        self, kind: str, block_id: Optional[int], details: str
    ) -> None:
        """Record a failure event."""
        key = f"{kind}:{block_id}" if block_id is not None else kind
        if key in self.failures:
            return
        rec = FailureSnapshot(
            kind=kind, block_id=block_id, time=self.time, details=details
        )
        self.failures[key] = rec
        self.failure_history.append(rec)
        logger.error("[%s] block=%s :: %s", kind, block_id, details)

    def _adjacent_blocks(self, block_id: int) -> list[int]:
        """Get adjacent block IDs."""
        return [b for b in [block_id - 1, block_id + 1] if b in self._line_blocks]

    def _check_broken_rail(self, block_id: int, now_occupied: bool) -> None:
        """Check for broken rail condition."""
        if not now_occupied or block_id not in self._line_blocks:
            return

        neighbors = self._adjacent_blocks(block_id)
        if not neighbors:
            return

        recent_window = timedelta(seconds=12)
        if not any(
            ts and (self.time - ts) <= recent_window
            for nb in neighbors
            if (ts := self._occupancy_timestamps.get(nb))
        ):
            self._record_failure(
                "broken_rail",
                block_id,
                f"Block {block_id} became occupied without adjacent blocks "
                "touching first.",
            )

    def _check_track_circuit(
        self, block_id: int, prev_occupied: bool, now_occupied: bool
    ) -> None:
        """Check for track circuit failure."""
        if block_id not in self._expected_stop_blocks:
            return

        if prev_occupied and not now_occupied:
            cmd_time = self._expected_stop_blocks.get(block_id)
            if not cmd_time:
                self._expected_stop_blocks.pop(block_id, None)
                return

            elapsed = (self.time - cmd_time).total_seconds()
            if elapsed < 10.0:
                self._record_failure(
                    "track_circuit",
                    block_id,
                    f"Train left block {block_id} only {elapsed:.1f}s after "
                    "stop command.",
                )
                for b in range(block_id - 2, block_id + 3):
                    if b in self._line_blocks:
                        try:
                            self.set_signal(b, SignalState.RED)
                            self.set_commanded_speed(b, 0)
                            self.set_commanded_authority(b, 0)
                        except Exception:
                            pass

            self._expected_stop_blocks.pop(block_id, None)

    def _schedule_actuator_verification(
        self, target_id: int, target_type: str, expected: Any
    ) -> None:
        """Schedule verification of an actuator command."""
        key = f"{target_type}:{target_id}"
        self._pending_actuator_checks[key] = ActuatorCommandCheck(
            block_id=target_id,
            actuator=target_type,
            expected=expected,
            issued_at=self.time,
        )
        self._actuator_retry_count[key] = (
            self._actuator_retry_count.get(key, 0) + 1
        )

    def _review_actuator_responses(self) -> None:
        """Review pending actuator commands for timeouts."""
        if not self._pending_actuator_checks:
            return

        segments = getattr(self.track_model, "segments", {})
        to_drop = []

        for key, check in list(self._pending_actuator_checks.items()):
            if check.cleared:
                to_drop.append(key)
                continue

            if (self.time - check.issued_at).total_seconds() < self._command_timeout_sec:
                continue

            ok = True
            if seg := segments.get(check.block_id):
                if check.actuator == "signal":
                    ok = getattr(seg, "signal_state", None) == check.expected
                elif check.actuator == "switch":
                    ok = getattr(seg, "current_position", None) == check.expected

            if ok:
                check.cleared = True
                to_drop.append(key)
            elif (
                self._actuator_retry_count.get(key, 1) >= self._max_command_attempts
            ):
                self._record_failure(
                    "power_failure",
                    check.block_id,
                    f"No response for {check.actuator} on {check.block_id}",
                )
                if check.actuator == "switch" and check.block_id in self._line_blocks:
                    try:
                        self.set_commanded_speed(check.block_id, 0)
                    except Exception:
                        pass
                to_drop.append(key)
            else:
                check.issued_at = self.time

        for key in to_drop:
            self._pending_actuator_checks.pop(key, None)
            self._actuator_retry_count.pop(key, None)

    def start_live_link(self, poll_interval: float = 1.0) -> None:
        """Start live polling of track model."""
        if self._live_thread_running:
            return
        self._live_thread_running = True

        def loop():
            while self._live_thread_running:
                try:
                    self._poll_track_model()
                except Exception:
                    logger.exception("poll loop")
                time.sleep(poll_interval)

        threading.Thread(target=loop, daemon=True).start()

        self._guard_poll_interval = max(0.25, float(poll_interval))
        if self._guard_blocks and not self._guard_thread_running:
            self._guard_thread_running = True
            threading.Thread(target=self._guard_loop, daemon=True).start()

    def stop_live_link(self) -> None:
        """Stop live polling."""
        self._guard_thread_running = False
        self._live_thread_running = False

    def _poll_track_model(self) -> None:
        """Poll track model for changes."""
        segments = getattr(self.track_model, "segments", {})
        if not isinstance(segments, dict):
            return

        changed_ctc = False
        for b, seg in segments.items():
            occ = bool(getattr(seg, "occupied", False))
            if self._known_occupancy.get(b) != occ:
                self._on_occupancy_change(b, occ)
                changed_ctc = True

            sig = getattr(seg, "signal_state", "N/A")
            if sig != "N/A" and self._known_signal.get(b) != sig:
                self._known_signal[b] = sig
                changed_ctc = True

        if changed_ctc:
            self._notify_listeners()
            self._send_status_to_ctc()

        self._review_actuator_responses()

    def _guard_loop(self) -> None:
        """Poll guard blocks at territory boundaries."""
        while self._guard_thread_running:
            try:
                segments = getattr(self.track_model, "segments", {})
                for gb in self._guard_blocks:
                    if seg := segments.get(gb):
                        occ = bool(getattr(seg, "occupied", False))
                        if self._known_occupancy.get(gb) != occ:
                            self._known_occupancy[gb] = occ
                            self._notify_listeners()
            except Exception:
                logger.exception("Guard-block polling error")
            time.sleep(self._guard_poll_interval)

    def set_maintenance_mode(self, enabled: bool) -> None:
        """Set maintenance mode."""
        self.maintenance_mode = bool(enabled)

    def _check_switch_clear_for_move(self, switch_id: int) -> None:
        """Check if switch can be moved safely."""
        for b in self.switch_map.get(switch_id, ()):
            if self._known_occupancy.get(b, False):
                raise PermissionError(
                    f"Cannot move switch {switch_id}; block {b} is occupied"
                )

    def safe_set_switch(self, switch_id: int, position: str | int | bool) -> None:
        """Set switch position with safety checks.

        Args:
            switch_id: The switch to set.
            position: Target position (Straight/Diverging or 0/1).

        Raises:
            PermissionError: If not in maintenance mode or switch is occupied.
            ValueError: If position is invalid.
        """
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change switches")
        self._check_switch_clear_for_move(switch_id)

        raw = str(position).strip().lower()
        if isinstance(position, bool):
            int_pos, pos_label = (1, "Diverging") if position else (0, "Straight")
        elif raw in ("0", "straight", "normal"):
            int_pos, pos_label = 0, "Straight"
        elif raw in ("1", "diverging", "alternate"):
            int_pos, pos_label = 1, "Diverging"
        else:
            raise ValueError(f"Invalid switch position: {position}")

        self.switches[switch_id] = pos_label
        try:
            if hasattr(self.track_model, "set_switch_position"):
                self.track_model.set_switch_position(switch_id, int_pos)
        except Exception:
            logger.exception("Failed to set switch in track model")

        self._update_switch_signals()

        self._notify_listeners()
        self._send_status_to_ctc()

    def safe_set_crossing(self, crossing_id: int, status: str) -> None:
        """Set crossing status with safety checks.

        Args:
            crossing_id: The crossing to set.
            status: Target status (Active/Inactive).

        Raises:
            PermissionError: If not in maintenance mode.
        """
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to change crossings")
        self.crossings[crossing_id] = status
        if block_id := self.crossing_blocks.get(crossing_id):
            try:
                if hasattr(self.track_model, "set_gate_status"):
                    self.track_model.set_gate_status(block_id, status == "Active")
            except Exception:
                logger.exception("Failed to set crossing gate")
        self._notify_listeners()
        self._send_status_to_ctc()

    def _apply_switch_from_plc(self, switch_id: int, position: str) -> None:
        """Apply switch position from PLC logic."""
        self._check_switch_clear_for_move(switch_id)
        if position == "Normal":
            position = "Straight"
        elif position == "Alternate":
            position = "Diverging"
        self.switches[switch_id] = position
        try:
            if hasattr(self.track_model, "set_switch_position"):
                self.track_model.set_switch_position(
                    switch_id, 0 if position == "Straight" else 1
                )
        except Exception:
            logger.exception("Failed to set switch from PLC")

        self._update_switch_signals()

    def _apply_crossing_from_plc(self, crossing_id: int, status: str) -> None:
        """Apply crossing status from PLC logic."""
        self.crossings[crossing_id] = status
        if block_id := self.crossing_blocks.get(crossing_id):
            try:
                if hasattr(self.track_model, "set_gate_status"):
                    self.track_model.set_gate_status(block_id, status == "Active")
            except Exception:
                logger.exception("Failed to set crossing gate from PLC")

    def set_block_occupancy(self, block: int, status: bool) -> None:
        """Set block occupancy status."""
        if seg := getattr(self.track_model, "segments", {}).get(block):
            try:
                seg.set_occupancy(bool(status))
            except Exception:
                logger.exception("set_occupancy failed for block %s", block)
        self._on_occupancy_change(block, bool(status))
        if not self._batch_updates:
            self._notify_listeners()
            self._send_status_to_ctc()

    def set_signal(
        self,
        block: int,
        color: str | SignalState,
        signal_side: int = 0,
    ) -> None:
        """Set the signal state for a block.

        Args:
            block: The block to set the signal for.
            color: The signal color/state.
            signal_side: Signal side for switches (0=previous, 1=straight, 2=diverging).
        """
        if isinstance(color, SignalState):
            state = color
        else:
            try:
                enum_name = str(color).replace(" ", "").upper()
                state = SignalState[enum_name]
            except (KeyError, AttributeError):
                logger.warning('Invalid signal color "%s"', color)
                return

        if block in self.switch_map:
            if not hasattr(self, "_switch_signals"):
                self._switch_signals = {}
            self._switch_signals[(block, signal_side)] = state
        else:
            self._known_signal[block] = state

        try:
            self.track_model.set_signal_state(block, signal_side, state)
            logger.info(
                "Sent to Track Model: Block %d signal (side %d) -> %s",
                block,
                signal_side,
                state.name,
            )
        except Exception as error:
            logger.warning(
                "Failed to set signal %d (side %d) in Track Model: %s",
                block,
                signal_side,
                error,
            )

        self._notify_listeners()
        self._send_status_to_ctc()

    def set_commanded_speed(self, block: int, speed_mph: int) -> None:
        """Set commanded speed for a block."""
        speed_val = int(speed_mph)
        self._commanded_speed_mph[block] = speed_val
        if speed_val == 0:
            self._expected_stop_blocks[block] = self.time

        try:
            if hasattr(self.track_model, "broadcast_train_command"):
                self.track_model.broadcast_train_command(
                    block, speed_val, self._commanded_auth_yd.get(block, 0)
                )
        except Exception:
            logger.exception("broadcast_train_command failed for speed")
        if not self._batch_updates:
            self._notify_listeners()

    def set_commanded_authority(self, block: int, auth_yd: int) -> None:
        """Set commanded authority for a block."""
        auth_val = int(auth_yd)
        self._commanded_auth_yd[block] = auth_val
        if auth_val == 0:
            self._expected_stop_blocks.setdefault(block, self.time)

        try:
            if hasattr(self.track_model, "broadcast_train_command"):
                self.track_model.broadcast_train_command(
                    block, self._commanded_speed_mph.get(block, 0), auth_val
                )
        except Exception:
            logger.exception("broadcast_train_command failed for authority")
        if not self._batch_updates:
            self._notify_listeners()

    def upload_plc(self, path: str) -> None:
        """Upload PLC logic from file.

        Args:
            path: Path to PLC file (.py or .txt).

        Raises:
            PermissionError: If not in maintenance mode.
        """
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to upload PLC")

        logger.info("upload_plc: %s", path)
        self._begin_batch()
        try:
            if path.lower().endswith(".py"):
                self._upload_plc_python(path)
            else:
                self._upload_plc_text(path)
        except FileNotFoundError:
            logger.error("PLC file not found: %s", path)
        except Exception:
            logger.exception("PLC upload failed for %s", path)
        finally:
            self._sync_after_plc_upload()
            self._end_batch()
            self._send_status_to_ctc()

    def _sync_after_plc_upload(self) -> None:
        """Sync state after PLC upload."""
        segments = getattr(self.track_model, "segments", {})
        if not isinstance(segments, dict):
            return
        for b in self.get_line_block_ids():
            if seg := segments.get(b):
                sig = getattr(seg, "signal_state", None)
                if sig not in (None, "N/A"):
                    self._known_signal[b] = sig

        self._update_switch_signals()

    def _upload_plc_python(self, path: str) -> None:
        """Upload PLC from Python file."""
        ns: dict[str, Any] = {}
        with open(path, "r") as f:
            exec(f.read(), ns, ns)

        if plc_func := ns.get("plc_logic"):
            if callable(plc_func):

                class _PLCHolder:
                    pass

                plc_obj = _PLCHolder()
                for name, value in ns.items():
                    setattr(plc_obj, name, value)
                self._plc_logic_module = plc_obj
                logger.info("Dynamic PLC loaded with plc_logic()")
                try:
                    self._invoke_plc_logic()
                except Exception:
                    logger.exception("Initial PLC logic execution failed")
                return

        self._plc_logic_module = None
        line_blocks = set(self.get_line_block_ids())

        for name, value in ns.items():
            if name.startswith("__"):
                continue
            lname = name.lower()
            try:
                if lname.startswith("block_") and lname.endswith("_occupied"):
                    block_id = int(lname[6:-9])
                    if block_id in line_blocks:
                        self.set_block_occupancy(block_id, bool(value))
                elif lname.startswith("switch_"):
                    self.safe_set_switch(int(lname[7:]), value)
                elif lname.startswith("crossing_"):
                    val_str = (
                        "Active"
                        if isinstance(value, bool) and value
                        else str(value).title()
                    )
                    if isinstance(value, bool):
                        val_str = "Active" if value else "Inactive"
                    self.safe_set_crossing(int(lname[9:]), val_str)
                elif lname.startswith("commanded_speed_") or lname.startswith(
                    "cmd_speed_"
                ):
                    block_id = int(lname.split("_")[-1])
                    if block_id in line_blocks:
                        self.set_commanded_speed(block_id, int(value))
                elif lname.startswith("commanded_auth_") or lname.startswith(
                    "cmd_auth_"
                ):
                    block_id = int(lname.split("_")[-1])
                    if block_id in line_blocks:
                        self.set_commanded_authority(block_id, int(value))
                elif lname.startswith("signal_"):
                    block_id = int(lname[7:])
                    if block_id in line_blocks:
                        val = (
                            "GREEN"
                            if isinstance(value, bool) and value
                            else ("RED" if isinstance(value, bool) else value)
                        )
                        self.set_signal(block_id, val)
            except Exception:
                logger.exception("Failed to apply PLC var: %s", name)

    def _upload_plc_text(self, path: str) -> None:
        """Upload PLC from text file."""
        with open(path, "r") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                cmd = parts[0].upper()
                try:
                    if cmd == "SWITCH" and len(parts) >= 3:
                        pos = (
                            "Normal"
                            if parts[2] == "0"
                            else ("Alternate" if parts[2] == "1" else parts[2])
                        )
                        self.safe_set_switch(int(parts[1]), pos)
                    elif cmd == "CROSSING" and len(parts) >= 3:
                        stat = (
                            "Active"
                            if parts[2].lower() == "true"
                            else (
                                "Inactive"
                                if parts[2].lower() == "false"
                                else parts[2]
                            )
                        )
                        self.safe_set_crossing(int(parts[1]), stat)
                    elif cmd == "SIGNAL" and len(parts) >= 3:
                        self.set_signal(int(parts[1]), parts[2])
                    elif cmd == "CMD_SPEED" and len(parts) >= 3:
                        self.set_commanded_speed(int(parts[1]), int(parts[2]))
                    elif cmd == "CMD_AUTH" and len(parts) >= 3:
                        self.set_commanded_authority(int(parts[1]), int(parts[2]))
                    else:
                        logger.warning("Unknown PLC command: %s", raw_line.rstrip())
                except Exception:
                    logger.exception("Failed to parse PLC line: %r", raw_line)

    def _invoke_plc_logic(self) -> None:
        """Execute loaded PLC logic."""
        plc = self._plc_logic_module
        if not plc or not hasattr(plc, "plc_logic"):
            return

        blocks = self.get_line_block_ids()
        if not blocks:
            return

        max_idx = max(blocks) + 1
        current_occ = [False] * max_idx
        prev_occ = [False] * max_idx
        stop_flags = [False] * max_idx
        signal_bools = [False] * max_idx

        for b in blocks:
            if b < max_idx:
                current_occ[b] = self._known_occupancy.get(b, False)
                prev_occ[b] = self._plc_prev_occupancy.get(b, False)
                sig = self._known_signal.get(b, SignalState.RED)
                signal_bools[b] = sig == SignalState.GREEN

        switch_ids = sorted(self.switches.keys())
        switch_positions = [
            self.switches.get(sid, "Straight") == "Diverging" for sid in switch_ids
        ]

        crossing_ids = sorted(self.crossing_blocks.keys())
        crossing_states = [
            self.crossings.get(cid, "Inactive") == "Active" for cid in crossing_ids
        ]

        try:
            out_switches, out_signals, out_crossings, out_stops = plc.plc_logic(
                current_occ,
                switch_positions,
                signal_bools,
                crossing_states,
                prev_occ,
                stop_flags,
            )
        except Exception:
            logger.exception("PLC plc_logic() raised an exception")
            return

        for idx, sid in enumerate(switch_ids):
            if idx < len(out_switches):
                desired = "Diverging" if bool(out_switches[idx]) else "Straight"
                if self.switches.get(sid) != desired:
                    try:
                        self._apply_switch_from_plc(sid, desired)
                    except Exception:
                        logger.exception("Failed to apply PLC switch %s", sid)

        for b in blocks:
            if b not in self.switch_map and b < len(out_signals):
                state = (
                    SignalState.GREEN if bool(out_signals[b]) else SignalState.RED
                )
                if self._known_signal.get(b) != state:
                    try:
                        self.set_signal(b, state, signal_side=0)
                    except Exception:
                        logger.exception("Failed to apply PLC signal for block %s", b)

        for idx, sid in enumerate(switch_ids):
            signal_idx_base = idx * 3

            if signal_idx_base < len(out_signals):
                state = (
                    SignalState.GREEN
                    if bool(out_signals[signal_idx_base])
                    else SignalState.RED
                )
                if self._switch_signals.get((sid, 0)) != state:
                    try:
                        self.set_signal(sid, state, signal_side=0)
                    except Exception:
                        logger.exception(
                            "Failed to set switch %d previous signal", sid
                        )

            if signal_idx_base + 1 < len(out_signals):
                state = (
                    SignalState.GREEN
                    if bool(out_signals[signal_idx_base + 1])
                    else SignalState.RED
                )
                if self._switch_signals.get((sid, 1)) != state:
                    try:
                        self.set_signal(sid, state, signal_side=1)
                    except Exception:
                        logger.exception(
                            "Failed to set switch %d straight signal", sid
                        )

            if signal_idx_base + 2 < len(out_signals):
                state = (
                    SignalState.GREEN
                    if bool(out_signals[signal_idx_base + 2])
                    else SignalState.RED
                )
                if self._switch_signals.get((sid, 2)) != state:
                    try:
                        self.set_signal(sid, state, signal_side=2)
                    except Exception:
                        logger.exception(
                            "Failed to set switch %d diverging signal", sid
                        )

        for idx, cid in enumerate(crossing_ids):
            if idx < len(out_crossings):
                desired = "Active" if bool(out_crossings[idx]) else "Inactive"
                if self.crossings.get(cid) != desired:
                    try:
                        self._apply_crossing_from_plc(cid, desired)
                    except Exception:
                        logger.exception("Failed to apply PLC crossing %s", cid)

        if out_stops:
            for b in blocks:
                if b < len(out_stops) and bool(out_stops[b]):
                    self.set_commanded_speed(b, 0)
                    self.set_commanded_authority(b, 0)
                elif b in self._suggested_speed_mph:
                    self.set_commanded_speed(b, self._suggested_speed_mph[b])
                    if b in self._suggested_auth_yd:
                        self.set_commanded_authority(b, self._suggested_auth_yd[b])

        for b in blocks:
            self._plc_prev_occupancy[b] = current_occ[b]

        self._update_switch_signals()

    def get_line_block_ids(self) -> list[int]:
        """Get all block IDs for this line."""
        return list(self._line_blocks)

    def get_switch_signal(self, switch_id: int, signal_side: int) -> SignalState:
        """Get the signal state for a switch signal.

        Args:
            switch_id: The switch block ID.
            signal_side: 0=previous, 1=straight, 2=diverging.

        Returns:
            The signal state (defaults to RED).
        """
        return self._switch_signals.get((switch_id, signal_side), SignalState.RED)

    @property
    def switch_signals(self) -> dict[tuple[int, int], SignalState]:
        """Get all switch signals."""
        return self._switch_signals.copy()

    @property
    def blocks(self) -> dict[int, dict[str, object]]:
        """Get formatted block data for all blocks on this line."""
        blocks_dict: dict[int, dict[str, Any]] = {}

        for block_id in self.get_line_block_ids():
            try:
                if block_id in self._known_occupancy:
                    occupied_val = bool(self._known_occupancy[block_id])
                else:
                    occupied_val = "N/A"

                if block_id in self._suggested_speed_mph:
                    suggested_speed_mph = self._suggested_speed_mph[block_id]
                else:
                    suggested_speed_mph = "N/A"

                if block_id in self._suggested_auth_yd:
                    suggested_auth_yd = self._suggested_auth_yd[block_id]
                else:
                    suggested_auth_yd = "N/A"

                if block_id in self._commanded_speed_mph:
                    commanded_speed_mph = self._commanded_speed_mph[block_id]
                else:
                    commanded_speed_mph = "N/A"

                if block_id in self._commanded_auth_yd:
                    commanded_auth_yd = self._commanded_auth_yd[block_id]
                else:
                    commanded_auth_yd = "N/A"

                if block_id in self.switch_map:
                    signal_val = {
                        "previous": self._switch_signals.get((block_id, 0), "N/A"),
                        "straight": self._switch_signals.get((block_id, 1), "N/A"),
                        "diverging": self._switch_signals.get((block_id, 2), "N/A"),
                    }
                elif block_id in self._known_signal:
                    signal_val = self._known_signal[block_id]
                else:
                    signal_val = SignalState.RED

                blocks_dict[block_id] = {
                    "occupied": occupied_val,
                    "suggested_speed": suggested_speed_mph,
                    "suggested_auth": suggested_auth_yd,
                    "commanded_speed": commanded_speed_mph,
                    "commanded_auth": commanded_auth_yd,
                    "signal": signal_val,
                    "view_only": block_id in self._view_blocks,
                }

            except Exception as error:
                logger.debug("Error building block %d data: %s", block_id, error)
                continue

        return blocks_dict

    def report_state(self) -> dict[str, Any]:
        """Get full state report."""
        return {
            "line": self.line_name,
            "maintenance_mode": self.maintenance_mode,
            "blocks": self.blocks,
            "switches": self.switches.copy(),
            "switch_map": self.switch_map.copy(),
            "switch_signals": {
                f"{k[0]}_{k[1]}": v.name for k, v in self._switch_signals.items()
            },
            "crossings": self.crossings.copy(),
            "crossing_blocks": self.crossing_blocks.copy(),
        }

    def debug_ctc_suggestions(self) -> dict[str, Any]:
        """Get debug info for CTC suggestions."""
        return {
            "ctc_backend_connected": self.ctc_backend is not None,
            "ctc_updates_enabled": self._ctc_update_enabled,
            "suggested_speeds": self._suggested_speed_mph.copy(),
            "suggested_authorities": self._suggested_auth_yd.copy(),
            "line_blocks": (
                list(self._line_blocks[:10]) + ["..."]
                if len(self._line_blocks) > 10
                else list(self._line_blocks)
            ),
            "hw_blocks": (
                list(self._hw_blocks[:10]) + ["..."]
                if len(self._hw_blocks) > 10
                else list(self._hw_blocks)
            ),
        }

    def get_failure_report(self) -> dict[str, Any]:
        """Get failure report."""
        return {
            "active": [
                {
                    "type": f.kind,
                    "block": f.block_id,
                    "time": f.time.strftime("%Y-%m-%d %H:%M:%S"),
                    "details": f.details,
                    "cleared": f.cleared,
                }
                for f in self.failures.values()
            ],
            "history": [
                {
                    "type": f.kind,
                    "block": f.block_id,
                    "time": f.time.strftime("%Y-%m-%d %H:%M:%S"),
                    "details": f.details,
                    "cleared": f.cleared,
                }
                for f in self.failure_history[-20:]
            ],
            "pending_commands": len(self._pending_actuator_checks),
        }

    def clear_failures(self) -> None:
        """Clear all active failures.

        Raises:
            PermissionError: If not in maintenance mode.
        """
        if not self.maintenance_mode:
            raise PermissionError("Must be in maintenance mode to clear failures")
        for rec in self.failures.values():
            rec.cleared = True
        self.failures.clear()
        self._pending_actuator_checks.clear()
        self._actuator_retry_count.clear()
        logger.info("%s: failures cleared", self.line_name)
        self._notify_listeners()

    def set_time(self, new_time: datetime) -> None:
        """Set the current time."""
        self.time = new_time

    def manual_set_time(
        self, year: int, month: int, day: int, hour: int, minute: int, second: int
    ) -> None:
        """Manually set the time."""
        self.time = datetime(year, month, day, hour, minute, second)
        logger.info(
            "%s: Time manually set to %s",
            self.line_name,
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._notify_listeners()

    def run_line_test(self, plc_path: str) -> dict[str, Any]:
        """Run a line test with the given PLC file."""
        self.set_maintenance_mode(True)
        self.upload_plc(plc_path)
        blocks = self.blocks
        return {
            "line": self.line_name,
            "switches": self.switches.copy(),
            "crossings": self.crossings.copy(),
            "signals_set": {
                b: (
                    d["signal"].name.title()
                    if hasattr(d["signal"], "name")
                    else d["signal"]
                )
                for b, d in blocks.items()
                if d.get("signal") not in (None, "N/A")
            },
            "commanded": {
                b: {"speed_mph": d["commanded_speed"], "auth_yd": d["commanded_auth"]}
                for b, d in blocks.items()
                if d.get("commanded_speed") != "N/A"
                or d.get("commanded_auth") != "N/A"
            },
        }


def build_backend_for_sim(
    track_model: TrackModelAdapter, line_name: str = "Blue Line"
) -> HardwareTrackControllerBackend:
    """Build a backend instance for simulation."""
    return HardwareTrackControllerBackend(track_model, line_name=line_name)