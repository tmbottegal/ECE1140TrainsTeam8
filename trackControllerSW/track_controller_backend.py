"""Track Controller Backend module.

This module provides the core backend logic for the track controller system,
including PLC integration, failure detection, and Track Model communication.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

_PKG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PKG_ROOT not in sys.path:
    sys.path.append(_PKG_ROOT)

from trackModel.track_model_backend import TrackNetwork
from universal.universal import ConversionFunctions, SignalState

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class SafetyException(Exception):
    """Exception raised when safety constraints are violated."""


LINE_BLOCK_MAP: Dict[str, range] = {
    'Red Line': range(1, 77),
    'Green Line': range(1, 151),
    'Blue Line': range(1, 16),
}


@dataclass
class TrackModelMessage:
    """Message from Track Model about block state changes."""

    block_id: int
    attribute: str
    value: Any


@dataclass
class WaysideStatusUpdate:
    """Status update to send to CTC."""

    block_id: int
    occupied: bool
    signal_state: SignalState
    switch_position: Optional[int] = None
    crossing_status: Optional[bool] = None


@dataclass
class FailureRecord:
    """Record of a detected system failure."""

    failure_type: str
    block_id: int
    timestamp: datetime
    details: str
    resolved: bool = False


@dataclass
class CommandVerification:
    """Tracking record for verifying command execution."""

    block_id: int
    command_type: str
    expected_value: Any
    timestamp: datetime
    verified: bool = False


class FailureDetection:
    """Mixin class providing failure detection and handling capabilities."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize failure detection system."""
        super().__init__(*args, **kwargs)

    def _detect_broken_rail(self, block_id: int, occupied: bool) -> None:
        """Detect broken rail conditions on a block.

        Args:
            block_id: The block to check.
            occupied: Current occupancy status.
        """
        if block_id in self._expected_occupancy and not occupied:
            failure_key = f'broken_rail_{block_id}'
            if failure_key not in self.failures:
                failure = FailureRecord(
                    failure_type='broken_rail',
                    block_id=block_id,
                    timestamp=self.time,
                    details=(
                        f'Block {block_id} did not register occupancy when '
                        f'train passed through'
                    ),
                )
                self.failures[failure_key] = failure
                self.failure_history.append(failure)
                logger.error('Broken rail detected at block %d', block_id)
                self._handle_broken_rail(block_id)

        prev_occupied = self._previous_occupancy.get(block_id, False)
        if prev_occupied != occupied:
            self._occupancy_changes[block_id] = self.time
            self._previous_occupancy[block_id] = occupied
            self._check_occupancy_consistency(block_id, occupied)

    def _check_occupancy_consistency(
        self, block_id: int, occupied: bool
    ) -> None:
        """Check if occupancy change is consistent with adjacent blocks.

        Args:
            block_id: The block to check.
            occupied: Current occupancy status.
        """
        if not occupied:
            return

        adjacent_blocks = self._get_adjacent_blocks(block_id)
        recent_threshold = timedelta(seconds=10)
        has_recent_adjacent = False

        for adj_block in adjacent_blocks:
            if adj_block in self._occupancy_changes:
                time_diff = self.time - self._occupancy_changes[adj_block]
                if time_diff < recent_threshold:
                    has_recent_adjacent = True
                    break

        if not has_recent_adjacent and block_id not in self._occupancy_changes:
            logger.warning(
                'Block %d occupied with no adjacent block activity; '
                'rail may be broken',
                block_id,
            )

    def _detect_power_failure(
        self, block_id: int, command_type: str, expected_value: Any
    ) -> None:
        """Detect power failure based on command verification.

        Args:
            block_id: The block where command was sent.
            command_type: Type of command (e.g., 'signal', 'switch').
            expected_value: The expected value after command execution.
        """
        verification_key = f'{command_type}_{block_id}'
        verification = CommandVerification(
            block_id=block_id,
            command_type=command_type,
            expected_value=expected_value,
            timestamp=self.time,
        )
        self._pending_verifications[verification_key] = verification

        if verification_key not in self._command_retry_count:
            self._command_retry_count[verification_key] = 0

        self._command_retry_count[verification_key] += 1

        if self._command_retry_count[verification_key] >= 3:
            failure_key = f'power_failure_{command_type}_{block_id}'
            if failure_key not in self.failures:
                failure = FailureRecord(
                    failure_type='power_failure',
                    block_id=block_id,
                    timestamp=self.time,
                    details=(
                        f'Power failure for {command_type} at block {block_id}; '
                        f'no response after 3 attempts'
                    ),
                )
                self.failures[failure_key] = failure
                self.failure_history.append(failure)
                logger.error(
                    'Power failure detected at block %d for %s',
                    block_id,
                    command_type,
                )
                self._handle_power_failure(block_id, command_type)

    def _verify_commands(self) -> None:
        """Verify that pending commands have been executed."""
        current_time = self.time
        expired_verifications = []

        for key, verification in self._pending_verifications.items():
            if verification.verified:
                continue

            time_since_command = current_time - verification.timestamp
            if time_since_command > self._verification_timeout:
                self._detect_power_failure(
                    verification.block_id,
                    verification.command_type,
                    verification.expected_value,
                )
                expired_verifications.append(key)

        for key in expired_verifications:
            del self._pending_verifications[key]

    def _detect_track_circuit_failure(self, block_id: int) -> None:
        """Detect track circuit failures on a block.

        Args:
            block_id: The block to check.
        """
        if not self._known_occupancy.get(block_id, False):
            return

        commanded_speed = self._commanded_speed_mps.get(block_id)
        commanded_auth = self._commanded_auth_m.get(block_id)

        if commanded_speed is None or commanded_auth is None:
            logger.debug(
                'Skipping track circuit failure detection for block %d: '
                'missing commanded values',
                block_id,
            )
            return

        if commanded_speed == 0:
            if self._check_train_movement(block_id):
                failure_key = f'track_circuit_{block_id}'
                if failure_key not in self.failures:
                    failure = FailureRecord(
                        failure_type='track_circuit',
                        block_id=block_id,
                        timestamp=self.time,
                        details=(
                            f'Track circuit failure: train not responding to '
                            f'stop command at block {block_id}'
                        ),
                    )
                    self.failures[failure_key] = failure
                    self.failure_history.append(failure)
                    logger.error(
                        'Track circuit failure detected at block %d',
                        block_id,
                    )
                    self._handle_track_circuit_failure(block_id)

    def _check_train_movement(self, block_id: int) -> bool:
        """Check if a train has recently moved through a block.

        Args:
            block_id: The block to check.

        Returns:
            True if recent movement detected, False otherwise.
        """
        if block_id not in self._occupancy_changes:
            return False

        if self._known_occupancy.get(block_id, False):
            return False

        time_since_change = self.time - self._occupancy_changes[block_id]
        return time_since_change < timedelta(seconds=5)

    def _handle_broken_rail(self, block_id: int) -> None:
        """Handle a broken rail failure by setting safe conditions.

        Args:
            block_id: The block with the broken rail.
        """
        logger.critical(
            'CRITICAL: Broken rail at block %d - immediate maintenance required',
            block_id,
        )

        try:
            self.set_signal(block_id, SignalState.RED)
            for adj_block in self._get_adjacent_blocks(block_id):
                self.set_signal(adj_block, SignalState.RED)
        except Exception:
            logger.exception('Failed to set signals for broken rail handling')

        try:
            self.set_commanded_speed(block_id, 0)
            self.set_commanded_authority(block_id, 0)
            for adj_block in self._get_adjacent_blocks(block_id):
                self.set_commanded_speed(adj_block, 0)
                self.set_commanded_authority(adj_block, 0)
        except Exception:
            logger.exception('Failed to stop trains for broken rail handling')

    def _handle_power_failure(
        self, block_id: int, command_type: str
    ) -> None:
        """Handle a power failure by taking safe actions.

        Args:
            block_id: The block with the power failure.
            command_type: The type of command that failed.
        """
        logger.critical(
            'CRITICAL: Power failure at block %d (%s) - '
            'immediate maintenance required',
            block_id,
            command_type,
        )

        if command_type == 'signal':
            logger.warning(
                'Block %d signal assumed RED due to power failure', block_id
            )
        elif command_type == 'switch':
            logger.warning('Block %d switch inoperative due to power failure', block_id)
            self.set_commanded_speed(block_id, 0)

    def _handle_track_circuit_failure(self, block_id: int) -> None:
        """Handle a track circuit failure by setting safe conditions.

        Args:
            block_id: The block with the track circuit failure.
        """
        logger.critical(
            'CRITICAL: Track circuit failure at block %d - '
            'immediate maintenance required',
            block_id,
        )

        try:
            nearby_range = range(
                max(1, block_id - 2), min(block_id + 3, self.num_blocks + 1)
            )
            for nearby_block in nearby_range:
                if nearby_block in self._line_block_ids():
                    self.set_signal(nearby_block, SignalState.RED)
        except Exception:
            logger.exception('Failed to set signals for track circuit failure')

    def _get_adjacent_blocks(self, block_id: int) -> List[int]:
        """Get the adjacent blocks for a given block.

        Args:
            block_id: The block to find adjacent blocks for.

        Returns:
            List of adjacent block IDs that are valid for this line.
        """
        adjacent = []
        if block_id > 1:
            adjacent.append(block_id - 1)
        if block_id < self.num_blocks:
            adjacent.append(block_id + 1)
        return [b for b in adjacent if b in self._line_block_ids()]

    def get_failure_report(self) -> Dict[str, Any]:
        """Get a comprehensive failure report.

        Returns:
            Dictionary containing active failures, history, and statistics.
        """
        return {
            'active_failures': [
                {
                    'type': f.failure_type,
                    'block': f.block_id,
                    'time': f.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'details': f.details,
                    'resolved': f.resolved,
                }
                for f in self.failures.values()
            ],
            'failure_history': [
                {
                    'type': f.failure_type,
                    'block': f.block_id,
                    'time': f.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'details': f.details,
                    'resolved': f.resolved,
                }
                for f in self.failure_history[-10:]
            ],
            'pending_verifications': len(self._pending_verifications),
            'total_failures': len(self.failure_history),
        }

    def resolve_failure(self, failure_key: str) -> None:
        """Mark a failure as resolved.

        Args:
            failure_key: The key identifying the failure to resolve.
        """
        if failure_key in self.failures:
            self.failures[failure_key].resolved = True
            logger.info('Failure %s has been resolved', failure_key)
            del self.failures[failure_key]
            self._command_retry_count.clear()

    def clear_all_failures(self) -> None:
        """Clear all failure records.

        Raises:
            PermissionError: If not in maintenance mode.
        """
        if not self.maintenance_mode:
            raise PermissionError(
                'Must be in maintenance mode to clear failures'
            )

        self.failures.clear()
        self._command_retry_count.clear()
        self._pending_verifications.clear()
        logger.info('All failures cleared')

    def _apply_dynamic_plc_logic(self, plc_module) -> None:
        """Apply dynamic PLC logic from uploaded module.

        Args:
            plc_module: The loaded PLC module containing logic functions.
        """
        logger.info('Applying dynamic PLC logic for %s', self.line_name)

        # Extract PLC functions
        get_speed_for_signal = getattr(
            plc_module, 'get_speed_for_signal', None
        )
        get_authority_for_signal = getattr(
            plc_module, 'get_authority_for_signal', None
        )
        adjust_for_crossing = getattr(plc_module, 'adjust_for_crossing', None)
        adjust_for_switch = getattr(plc_module, 'adjust_for_switch', None)
        check_ahead_occupancy = getattr(
            plc_module, 'check_ahead_occupancy', None
        )
        check_proximity_occupancy = getattr(
            plc_module, 'check_proximity_occupancy', None
        )

        # Extract PLC constants
        speed_limit = getattr(plc_module, 'SPEED_LIMIT', 70)
        yellow_factor = getattr(plc_module, 'YELLOW_SPEED_FACTOR', 0.5)
        approach_factor = getattr(plc_module, 'APPROACH_SPEED_FACTOR', 0.7)

        for block_id in self._line_block_ids():
            try:
                # Get base values from PLC module
                base_speed = getattr(
                    plc_module, f'commanded_speed_{block_id}', None
                )
                base_auth = getattr(
                    plc_module, f'commanded_auth_{block_id}', None
                )

                if base_speed is None or base_auth is None:
                    continue

                # Get current state
                signal_state = self._known_signal.get(block_id, SignalState.RED)
                if isinstance(signal_state, SignalState):
                    signal_str = signal_state.name
                else:
                    signal_str = str(signal_state)

                occupied = self._known_occupancy.get(block_id, False)

                # Initialize adjusted values
                adjusted_speed = base_speed
                adjusted_auth = base_auth
                new_signal = SignalState.GREEN

                # Apply signal-based adjustments
                if get_speed_for_signal:
                    adjusted_speed = get_speed_for_signal(base_speed, signal_str)
                else:
                    if signal_str == 'RED':
                        adjusted_speed = 0
                    elif signal_str == 'YELLOW':
                        adjusted_speed = int(base_speed * yellow_factor)
                    elif signal_str == 'SUPERGREEN':
                        adjusted_speed = min(base_speed, speed_limit)

                if get_authority_for_signal:
                    adjusted_auth = get_authority_for_signal(
                        base_auth, signal_str, occupied
                    )
                else:
                    if signal_str == 'RED':
                        adjusted_auth = 0
                    elif occupied:
                        adjusted_auth = max(int(base_auth * 0.5), 50)

                # Determine new signal state
                if adjusted_speed == 0:
                    new_signal = SignalState.RED
                elif adjusted_speed < base_speed * 0.5:
                    new_signal = SignalState.YELLOW
                elif adjusted_speed >= speed_limit:
                    new_signal = SignalState.SUPERGREEN
                else:
                    new_signal = SignalState.GREEN

                # Check ahead occupancy
                if check_ahead_occupancy:
                    next_blocks = self._get_next_blocks(block_id)
                    next_occupied = [
                        self._known_occupancy.get(nb, False)
                        for nb in next_blocks
                    ]
                    occupancy_factor = check_ahead_occupancy(
                        block_id, next_occupied
                    )
                    adjusted_speed = int(adjusted_speed * occupancy_factor)
                else:
                    next_block = block_id + 1
                    if next_block in self._line_block_ids():
                        if self._known_occupancy.get(next_block, False):
                            adjusted_speed = int(
                                adjusted_speed * approach_factor
                            )

                # Check proximity occupancy
                if check_proximity_occupancy:
                    proximity_factor = check_proximity_occupancy(
                        block_id, self._known_occupancy
                    )
                    adjusted_speed = int(adjusted_speed * proximity_factor)
                else:
                    for distance in [1, 2]:
                        prev_block = block_id - distance
                        next_block = block_id + distance
                        prev_occupied = (
                            self._known_occupancy.get(prev_block, False)
                            if prev_block in self._line_block_ids()
                            else False
                        )
                        next_occupied = (
                            self._known_occupancy.get(next_block, False)
                            if next_block in self._line_block_ids()
                            else False
                        )
                        if prev_occupied or next_occupied:
                            adjusted_speed = int(adjusted_speed * 0.5)
                            break

                # Adjust for crossings
                for cid, cblock in self.crossing_blocks.items():
                    crossing_active = self.crossings.get(cid, False)
                    blocks_to_crossing = abs(block_id - cblock)

                    if adjust_for_crossing:
                        adjusted_speed, adjusted_auth = adjust_for_crossing(
                            adjusted_speed,
                            adjusted_auth,
                            crossing_active,
                            blocks_to_crossing,
                        )
                    else:
                        if crossing_active and blocks_to_crossing <= 2:
                            adjusted_speed = min(adjusted_speed, 25)
                            adjusted_auth = min(adjusted_auth, 75)

                # Adjust for switches
                for sid, spos in self.switches.items():
                    blocks_to_switch = abs(block_id - sid)

                    if adjust_for_switch:
                        adjusted_speed, adjusted_auth = adjust_for_switch(
                            adjusted_speed,
                            adjusted_auth,
                            spos,
                            blocks_to_switch,
                        )
                    else:
                        if blocks_to_switch <= 1 and spos == 1:
                            adjusted_speed = int(adjusted_speed * 0.7)
                            adjusted_auth = min(adjusted_auth, 100)

                # Convert units and set commands
                speed_mps = ConversionFunctions.mph_to_mps(adjusted_speed)
                auth_m = ConversionFunctions.yards_to_meters(adjusted_auth)

                self.set_commanded_speed(block_id, int(speed_mps))
                self.set_commanded_authority(block_id, int(auth_m))
                self.set_signal(block_id, new_signal)

                logger.debug(
                    'Block %d: base_speed=%d mph -> adjusted=%d mph (%.1f m/s), '
                    'base_auth=%d yd -> adjusted=%d yd (%.1f m), '
                    'signal=%s, occupied=%s',
                    block_id,
                    base_speed,
                    adjusted_speed,
                    speed_mps,
                    base_auth,
                    adjusted_auth,
                    auth_m,
                    signal_str,
                    occupied,
                )

            except Exception:
                logger.exception(
                    'Failed to apply dynamic logic for block %d', block_id
                )
                continue

        logger.info(
            'Dynamic PLC logic applied to %d blocks', len(self._line_block_ids())
        )

    def _get_next_blocks(self, block_id: int) -> List[int]:
        """Get the next blocks after a given block.

        Args:
            block_id: The block to find next blocks for.

        Returns:
            List of next block IDs.
        """
        next_blocks = []

        if block_id in self.switch_map:
            next_blocks.extend(self.switch_map[block_id])
        else:
            next_block = block_id + 1
            if next_block in self._line_block_ids():
                next_blocks.append(next_block)

        return next_blocks


class TrackControllerBackend(FailureDetection):
    """Main backend controller for track operations.

    This class manages all track control operations including block commands,
    switch positions, crossing gates, and failure detection.
    """

    def __init__(
        self, track_model: TrackNetwork, line_name: str = 'Green Line'
    ) -> None:
        """Initialize the Track Controller Backend.

        Args:
            track_model: The track model this controller manages.
            line_name: The name of the railway line.
        """
        self.track_model = track_model
        self.line_name = line_name

        # Speed and authority tracking
        self._suggested_speed_mps: Dict[int, float] = {}
        self._suggested_auth_m: Dict[int, float] = {}
        self._commanded_speed_mps: Dict[int, int] = {}
        self._commanded_auth_m: Dict[int, int] = {}

        # Infrastructure tracking
        self.switches: Dict[int, int] = {}
        self.switch_map: Dict[int, Tuple[int, ...]] = {}
        self.crossings: Dict[int, bool] = {}
        self.crossing_blocks: Dict[int, int] = {}

        # State tracking
        self._listeners: List[Callable[[], None]] = []
        self.time = datetime(2000, 1, 1, 0, 0, 0)
        self.maintenance_mode: bool = False

        # Known state from Track Model
        self._known_occupancy: Dict[int, bool] = {}
        self._known_signal: Dict[int, SignalState] = {}
        self._known_commanded_speed: Dict[int, int] = {}
        self._known_commanded_auth: Dict[int, int] = {}

        # Message queue
        self.incoming_messages: deque[TrackModelMessage] = deque()

        # Failure detection
        self.failures: Dict[str, FailureRecord] = {}
        self.failure_history: List[FailureRecord] = []
        self._previous_occupancy: Dict[int, bool] = {}
        self._occupancy_changes: Dict[int, datetime] = {}
        self._pending_verifications: Dict[str, CommandVerification] = {}
        self._verification_timeout = timedelta(seconds=5)
        self._train_positions: Dict[int, int] = {}
        self._expected_occupancy: Set[int] = set()
        self._last_command_attempt: Dict[int, datetime] = {}
        self._command_retry_count: Dict[str, int] = {}

        # PLC module
        self._plc_module = None
        self._previous_occupancies: Dict[int, bool] = {}

        # Threading
        self._live_thread_lock = threading.Lock()
        self._live_thread_running: bool = False

        # CTC integration
        self.ctc_backend = None
        self._ctc_update_enabled: bool = True

        # Switch signals
        self._switch_signals: Dict[Tuple[int, int], SignalState] = {}

        # Initialize crossing blocks based on line
        if self.line_name == 'Green Line':
            self.crossing_blocks = {1: 19}
        elif self.line_name == 'Red Line':
            self.crossing_blocks = {1: 11, 2: 47}
        else:
            self.crossing_blocks = {}

        # Setup
        self._initialize_infrastructure()
        self._initial_sync()

    def set_ctc_backend(self, ctc_backend: Any) -> None:
        """Connect this controller to a CTC backend.

        Args:
            ctc_backend: The CTC backend to connect to.
        """
        self.ctc_backend = ctc_backend
        logger.info('%s: CTC backend connected', self.line_name)

    def enable_ctc_updates(self, enabled: bool = True) -> None:
        """Enable or disable CTC status updates.

        Args:
            enabled: Whether to enable CTC updates.
        """
        self._ctc_update_enabled = enabled
        logger.info(
            '%s: CTC updates %s',
            self.line_name,
            'enabled' if enabled else 'disabled',
        )

    def receive_ctc_suggestion(
        self, block: int, suggested_speed_mps: float, suggested_auth_m: float
    ) -> None:
        """Receive speed and authority suggestion from CTC.

        Args:
            block: The block ID for the suggestion.
            suggested_speed_mps: Suggested speed in meters per second.
            suggested_auth_m: Suggested authority in meters.
        """
        if block not in self._line_block_ids():
            logger.warning(
                'CTC provided invalid block %d for %s', block, self.line_name
            )
            return

        self._suggested_speed_mps[block] = suggested_speed_mps
        self._suggested_auth_m[block] = suggested_auth_m
        logger.info(
            '%s: CTC suggestion for block %d: %.2f m/s, %.2f m',
            self.line_name,
            block,
            suggested_speed_mps,
            suggested_auth_m,
        )
        self._notify_listeners()

    def _send_status_to_ctc(self) -> None:
        """Send current wayside status to CTC."""
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
                crossing_status=crossing_status,
            )
            status_updates.append(status)

        try:
            if hasattr(self.ctc_backend, 'receive_wayside_status'):
                self.ctc_backend.receive_wayside_status(
                    self.line_name, status_updates
                )
                logger.debug(
                    '%s: Sent %d status updates to CTC',
                    self.line_name,
                    len(status_updates),
                )
            else:
                for status in status_updates:
                    self._send_single_status_to_ctc(status)
        except Exception:
            logger.exception('%s: Failed to send status to CTC', self.line_name)

    def _send_single_status_to_ctc(
        self, status: WaysideStatusUpdate
    ) -> None:
        """Send a single status update to CTC using individual methods.

        Args:
            status: The status update to send.
        """
        if self.ctc_backend is None:
            return

        try:
            if hasattr(self.ctc_backend, 'update_block_occupancy'):
                self.ctc_backend.update_block_occupancy(
                    self.line_name, status.block_id, status.occupied
                )

            if hasattr(self.ctc_backend, 'update_signal_state'):
                self.ctc_backend.update_signal_state(
                    self.line_name, status.block_id, status.signal_state
                )

            if (
                status.switch_position is not None
                and hasattr(self.ctc_backend, 'update_switch_position')
            ):
                self.ctc_backend.update_switch_position(
                    self.line_name, status.block_id, status.switch_position
                )

            if (
                status.crossing_status is not None
                and hasattr(self.ctc_backend, 'update_crossing_status')
            ):
                self.ctc_backend.update_crossing_status(
                    self.line_name, status.block_id, status.crossing_status
                )
        except Exception:
            logger.exception(
                '%s: Failed to send status for block %d',
                self.line_name,
                status.block_id,
            )

    def _initialize_infrastructure(self) -> None:
        """Initialize switches and crossings to default states."""
        for switch_id in self.switch_map:
            self.switches[switch_id] = 0

        for crossing_id in self.crossing_blocks:
            self.crossings[crossing_id] = False

    def _initial_sync(self) -> None:
        """Perform initial synchronization with Track Model."""
        logger.info('Synchronizing with Track Model for %s', self.line_name)

        try:
            status = self.track_model.get_wayside_status()
            if isinstance(status, dict) and 'segments' in status:
                segments = status.get('segments', {})
                for block_id, info in segments.items():
                    try:
                        block_id_int = int(block_id)
                    except (ValueError, TypeError):
                        continue

                    if block_id_int not in self._line_block_ids():
                        continue

                    if not isinstance(info, dict):
                        continue

                    if 'occupied' in info:
                        occupancy_status = bool(info['occupied'])
                        self._known_occupancy[block_id_int] = occupancy_status
                        self._previous_occupancies[block_id_int] = occupancy_status
                        self._previous_occupancy[block_id_int] = occupancy_status
                        logger.debug(
                            'Block %d occupancy: %s',
                            block_id_int,
                            info['occupied'],
                        )

                    if 'signal_state' in info:
                        self._known_signal[block_id_int] = info['signal_state']
                        logger.debug(
                            'Block %d signal: %s',
                            block_id_int,
                            info['signal_state'],
                        )

                    if (
                        'current_position' in info
                        and block_id_int in self.switches
                    ):
                        self.switches[block_id_int] = int(info['current_position'])
                        logger.debug(
                            'Switch %d position: %d',
                            block_id_int,
                            self.switches[block_id_int],
                        )

                    if 'gate_status' in info:
                        for cid, cblock in self.crossing_blocks.items():
                            if cblock == block_id_int:
                                self.crossings[cid] = bool(info['gate_status'])
                                logger.debug(
                                    'Synced crossing %d status: %s',
                                    cid,
                                    self.crossings[cid],
                                )

            # Direct segment access
            if hasattr(self.track_model, 'segments'):
                for block_id in self._line_block_ids():
                    if block_id in self.track_model.segments:
                        seg = self.track_model.segments[block_id]

                        if hasattr(seg, 'occupied'):
                            occupancy_status = bool(seg.occupied)
                            self._known_occupancy[block_id] = occupancy_status
                            self._previous_occupancies[block_id] = occupancy_status
                            self._previous_occupancy[block_id] = occupancy_status
                            logger.debug(
                                'Direct sync block %d occupancy: %s',
                                block_id,
                                seg.occupied,
                            )

                        if hasattr(seg, 'signal_state'):
                            self._known_signal[block_id] = seg.signal_state
                            logger.debug(
                                'Direct sync block %d signal: %s',
                                block_id,
                                seg.signal_state,
                            )

            logger.info('Synchronization completed for %s', self.line_name)

        except Exception:
            logger.exception('Failed to synchronize with Track Model')

    def receive_model_update(
        self, block_id: int, attribute: str, value: Any
    ) -> None:
        """Receive an update from the Track Model.

        Args:
            block_id: The block ID that changed.
            attribute: The attribute that changed.
            value: The new value.
        """
        msg = TrackModelMessage(block_id, attribute, value)
        self.incoming_messages.append(msg)
        logger.info(
            'Received Track Model update: block=%d, attr=%s, value=%s',
            block_id,
            attribute,
            value,
        )
        self._process_next_model_message()

    def _process_next_model_message(self) -> None:
        """Process the next message from the Track Model queue."""
        if not self.incoming_messages:
            return

        msg = self.incoming_messages.popleft()

        match msg.attribute.lower():
            case 'occupancy':
                self._update_occupancy_from_model(msg.block_id, bool(msg.value))

            case 'signal':
                self._known_signal[msg.block_id] = msg.value
                logger.info(
                    'Signal %d state updated: %s', msg.block_id, msg.value
                )

            case 'switch':
                self.switches[msg.block_id] = int(msg.value)
                logger.info(
                    'Switch %d position updated: %d', msg.block_id, msg.value
                )

            case 'crossing':
                for cid, cblock in self.crossing_blocks.items():
                    if cblock == msg.block_id:
                        self.crossings[cid] = bool(msg.value)
                logger.info(
                    'Crossing at block %d status updated: %s',
                    msg.block_id,
                    msg.value,
                )

            case _:
                logger.warning(
                    'Unknown Track Model attribute: %s', msg.attribute
                )

        self._notify_listeners()
        self._send_status_to_ctc()

    def set_commanded_speed(self, block_id: int, speed_mps: int) -> None:
        """Set the commanded speed for a block.

        Args:
            block_id: The block to command.
            speed_mps: Speed in meters per second.
        """
        if block_id not in self._line_block_ids():
            logger.warning(
                'Cannot set commanded speed: block %d not in %s',
                block_id,
                self.line_name,
            )
            return

        self._commanded_speed_mps[block_id] = speed_mps
        self._known_commanded_speed[block_id] = speed_mps
        logger.info(
            '[%s] Commanded speed: block %d = %d m/s',
            self.line_name,
            block_id,
            speed_mps,
        )

        try:
            auth_m = self._commanded_auth_m.get(block_id, 0)
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(auth_m)
            )
            logger.info(
                'Sent to Track Model: block %d, speed=%d m/s, auth=%d m',
                block_id,
                int(speed_mps),
                int(auth_m),
            )
        except Exception:
            logger.exception(
                'Track Model rejected commanded speed for block %d', block_id
            )

        self._notify_listeners()

    def set_commanded_authority(self, block_id: int, authority_m: int) -> None:
        """Set the commanded authority for a block.

        Args:
            block_id: The block to command.
            authority_m: Authority in meters.
        """
        if block_id not in self._line_block_ids():
            logger.warning(
                'Cannot set commanded authority: block %d not in %s',
                block_id,
                self.line_name,
            )
            return

        self._commanded_auth_m[block_id] = authority_m
        self._known_commanded_auth[block_id] = authority_m
        logger.info(
            '[%s] Commanded authority: block %d = %d m',
            self.line_name,
            block_id,
            authority_m,
        )

        try:
            speed_mps = self._commanded_speed_mps.get(block_id, 0)
            self.track_model.broadcast_train_command(
                block_id, int(speed_mps), int(authority_m)
            )
            logger.info(
                'Sent to Track Model: block %d, speed=%d m/s, auth=%d m',
                block_id,
                int(speed_mps),
                int(authority_m),
            )
        except Exception:
            logger.exception(
                'Track Model rejected commanded authority for block %d',
                block_id,
            )

        self._notify_listeners()

    def upload_plc(self, filepath: str) -> None:
        """Upload and execute a PLC program file.

        Args:
            filepath: Path to the PLC file.

        Raises:
            PermissionError: If not in maintenance mode.
        """
        if not self.maintenance_mode:
            raise PermissionError('Must be in maintenance mode to upload PLC')

        ext = os.path.splitext(filepath)[1].lower()
        logger.info('Uploading PLC file: %s', filepath)

        self._set_placeholder_suggested_values()

        if ext == '.py':
            self._upload_plc_python(filepath)
        else:
            logger.error('Unsupported PLC file format: %s', ext)
            return

        self._sync_after_plc_upload()
        self._notify_listeners()
        self._send_status_to_ctc()
        logger.info('PLC uploaded successfully for %s', self.line_name)

    def _set_placeholder_suggested_values(self) -> None:
         default_speed_mps = 20
         default_authority_m = 150
         for block_id in self._line_block_ids():
             if block_id not in self._suggested_speed_mps: self._suggested_speed_mps[block_id] = default_speed_mps
             if block_id not in self._suggested_auth_m: self._suggested_auth_m[block_id] = default_authority_m

    def _upload_plc_python(self, filepath: str) -> None:
        """Load and execute a Python PLC file.

        Args:
            filepath: Path to the Python PLC file.
        """
        spec = importlib.util.spec_from_file_location('plc_module', filepath)
        if spec is None or spec.loader is None:
            logger.error('Could not load PLC module from %s', filepath)
            return

        plc_module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(plc_module)
            self._plc_module = plc_module
            logger.info('PLC module loaded successfully')
        except Exception:
            logger.exception('Failed to execute PLC Python file %s', filepath)
            return

        if hasattr(plc_module, 'plc_logic'):
            logger.info('Found plc_logic function in PLC module')
            self._execute_plc_logic()
        else:
            logger.error('PLC module missing plc_logic function')

    def _execute_plc_logic(self) -> None:
        """Execute the PLC logic function with current system state."""
        if self._plc_module is None or not hasattr(
            self._plc_module, 'plc_logic'
        ):
            logger.warning(
                'No PLC module loaded or plc_logic function not found'
            )
            return

        try:
            # Prepare occupancy arrays
            max_blocks = (
                max(self._line_block_ids()) + 1
                if self._line_block_ids()
                else 151
            )
            block_occupancies = [False] * max_blocks
            previous_occupancies = [False] * max_blocks
            stop = [False] * max_blocks

            for block_id in self._line_block_ids():
                if block_id < len(block_occupancies):
                    block_occupancies[block_id] = self._known_occupancy.get(
                        block_id, False
                    )
                    previous_occupancies[block_id] = (
                        self._previous_occupancies.get(block_id, False)
                    )

            # Prepare switch positions
            switch_positions = [0] * max(10, len(self.switches))
            for idx, (switch_id, position) in enumerate(self.switches.items()):
                if idx < len(switch_positions):
                    switch_positions[idx] = position

            # Prepare signals
            light_signals = [False] * (len(self.switches) * 3)

            # Prepare crossing signals
            crossing_signals = [False] * max(10, len(self.crossings))
            for idx, (crossing_id, status) in enumerate(self.crossings.items()):
                if idx < len(crossing_signals):
                    crossing_signals[idx] = status

            logger.info('Executing PLC logic')

            # Execute PLC logic
            (
                switch_positions,
                light_signals,
                crossing_signals,
                stop,
            ) = self._plc_module.plc_logic(
                block_occupancies,
                switch_positions,
                light_signals,
                crossing_signals,
                previous_occupancies,
                stop,
            )

            # Apply switch positions
            for idx, (switch_id, _) in enumerate(self.switches.items()):
                if (
                    idx < len(switch_positions)
                    and switch_positions[idx] is not None
                ):
                    new_position = switch_positions[idx]
                    if self.switches[switch_id] != new_position:
                        self.switches[switch_id] = new_position
                        try:
                            self.track_model.set_switch_position(
                                switch_id, new_position
                            )
                            logger.info(
                                'PLC set switch %d to position %d',
                                switch_id,
                                new_position,
                            )
                        except Exception:
                            logger.exception(
                                'Failed to set switch %d', switch_id
                            )

            # Apply switch signals
            for idx, (switch_id, _) in enumerate(self.switches.items()):
                signal_idx_base = idx * 3

                # Previous signal
                if signal_idx_base < len(light_signals):
                    signal_state = (
                        SignalState.GREEN
                        if light_signals[signal_idx_base]
                        else SignalState.RED
                    )
                    try:
                        self.track_model.set_signal_state(
                            switch_id, 0, signal_state
                        )
                        self._switch_signals[(switch_id, 0)] = signal_state
                        logger.debug(
                            'PLC set switch %d previous signal: %s',
                            switch_id,
                            signal_state,
                        )
                    except Exception:
                        logger.exception(
                            'Failed to set switch %d previous signal',
                            switch_id,
                        )

                # Straight signal
                if signal_idx_base + 1 < len(light_signals):
                    signal_state = (
                        SignalState.GREEN
                        if light_signals[signal_idx_base + 1]
                        else SignalState.RED
                    )
                    try:
                        self.track_model.set_signal_state(
                            switch_id, 1, signal_state
                        )
                        self._switch_signals[(switch_id, 1)] = signal_state
                        logger.debug(
                            'PLC set switch %d straight signal: %s',
                            switch_id,
                            signal_state,
                        )
                    except Exception:
                        logger.exception(
                            'Failed to set switch %d straight signal',
                            switch_id,
                        )

                # Diverging signal
                if signal_idx_base + 2 < len(light_signals):
                    signal_state = (
                        SignalState.GREEN
                        if light_signals[signal_idx_base + 2]
                        else SignalState.RED
                    )
                    try:
                        self.track_model.set_signal_state(
                            switch_id, 2, signal_state
                        )
                        self._switch_signals[(switch_id, 2)] = signal_state
                        logger.debug(
                            'PLC set switch %d diverging signal: %s',
                            switch_id,
                            signal_state,
                        )
                    except Exception:
                        logger.exception(
                            'Failed to set switch %d diverging signal',
                            switch_id,
                        )

            # Apply crossing states
            for idx, (crossing_id, _) in enumerate(self.crossings.items()):
                if idx < len(crossing_signals):
                    new_status = crossing_signals[idx]
                    if self.crossings[crossing_id] != new_status:
                        self.crossings[crossing_id] = new_status
                        cblock = self.crossing_blocks.get(crossing_id)
                        if cblock:
                            try:
                                seg = self.track_model.segments.get(cblock)
                                if seg and hasattr(seg, 'set_gate_status'):
                                    seg.set_gate_status(new_status)
                                    logger.info(
                                        'PLC set crossing %d to %s',
                                        crossing_id,
                                        'Active' if new_status else 'Inactive',
                                    )
                            except Exception:
                                logger.exception(
                                    'Failed to set crossing %d', crossing_id
                                )

            # Apply stop commands and suggestions
            for block_id in self._line_block_ids():
                if block_id < len(stop):
                    if stop[block_id]:
                        self.set_commanded_speed(block_id, 0)
                        self.set_commanded_authority(block_id, 0)
                        logger.debug('PLC: Block %d commanded to STOP', block_id)
                    elif (
                        block_id in self._suggested_speed_mps
                        and block_id in self._suggested_auth_m
                    ):
                        suggested_speed = self._suggested_speed_mps[block_id]
                        suggested_auth = self._suggested_auth_m[block_id]
                        self.set_commanded_speed(block_id, int(suggested_speed))
                        self.set_commanded_authority(
                            block_id, int(suggested_auth)
                        )
                        logger.debug(
                            'PLC: Block %d commanded speed=%d, auth=%d',
                            block_id,
                            int(suggested_speed),
                            int(suggested_auth),
                        )

            # Update previous occupancies
            for block_id in self._line_block_ids():
                if block_id < len(block_occupancies):
                    self._previous_occupancies[block_id] = block_occupancies[
                        block_id
                    ]

            logger.info('PLC logic executed successfully')

        except Exception:
            logger.exception('PLC logic execution failed')

    def _sync_after_plc_upload(self) -> None:
        """Synchronize state after PLC upload."""
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

    def report_state(self) -> Dict[str, Any]:
        """Generate a comprehensive state report.

        Returns:
            Dictionary containing all system state information.
        """
        switches_display = {}
        for switch_id, pos in self.switches.items():
            switches_display[switch_id] = 'Normal' if pos == 0 else 'Alternate'

        crossings_display = {}
        for crossing_id, status in self.crossings.items():
            crossings_display[crossing_id] = {
                'block': self.crossing_blocks.get(crossing_id),
                'status': 'Active' if status else 'Inactive',
            }

        blocks_data = {}
        for block_id, data in self.blocks.items():
            signal_value = data['signal']
            if isinstance(signal_value, SignalState):
                signal_str = signal_value.name.title()
            elif isinstance(signal_value, str):
                signal_str = signal_value
            else:
                signal_str = 'N/A'

            blocks_data[block_id] = {
                'occupied': data['occupied'],
                'suggested_speed': data['suggested_speed'],
                'suggested_auth': data['suggested_auth'],
                'commanded_speed': data['commanded_speed'],
                'commanded_auth': data['commanded_auth'],
                'signal': signal_str,
            }

        return {
            'line': self.line_name,
            'maintenance_mode': self.maintenance_mode,
            'blocks': blocks_data,
            'switches': switches_display,
            'switch_map': self.switch_map.copy(),
            'crossing': crossings_display,
            'failures': self.get_failure_report(),
        }

    def _update_occupancy_from_model(
        self, block_id: int, occupied: bool
    ) -> None:
        """Update occupancy state from Track Model.

        Args:
            block_id: The block that changed occupancy.
            occupied: New occupancy status.
        """
        old_state = self._known_occupancy.get(block_id)
        self._known_occupancy[block_id] = occupied
        logger.info(
            '%s: Block %d occupancy updated from model -> %s',
            self.line_name,
            block_id,
            occupied,
        )

        # Only re-execute PLC if not in maintenance mode
        if old_state != occupied and self._plc_module is not None:
            if not self.maintenance_mode:
                logger.info(
                    'Occupancy changed for block %d, re-executing PLC logic',
                    block_id,
                )
                self._execute_plc_logic()
            else:
                logger.info(
                    'Occupancy changed for block %d, but PLC execution skipped (maintenance mode)',
                    block_id,
                )

        # Auto-manage crossing gates
        for cid, cblock in self.crossing_blocks.items():
            if cblock == block_id:
                try:
                    seg = self.track_model.segments.get(block_id)
                    if seg and hasattr(seg, 'set_gate_status'):
                        seg.set_gate_status(occupied)
                        self.crossings[cid] = occupied
                        logger.info(
                            'Auto-managed crossing %d gates: %s '
                            '(block %d occupancy=%s)',
                            cid,
                            self.crossings[cid],
                            block_id,
                            occupied,
                        )
                except Exception:
                    logger.exception(
                        'Failed to auto-update crossing gate for block %d',
                        block_id,
                    )

        # Update authority when block becomes unoccupied
        if not occupied:
            suggested_auth = self._suggested_auth_m.get(block_id, 50)
            self._commanded_auth_m[block_id] = int(suggested_auth)
            self._known_commanded_auth[block_id] = int(suggested_auth)

        self._detect_broken_rail(block_id, occupied)
        self._detect_track_circuit_failure(block_id)


    def start_live_link(self, poll_interval: float = 1.0) -> None:
        """Start live polling of Track Model state.

        Args:
            poll_interval: Polling interval in seconds.
        """
        with self._live_thread_lock:
            if self._live_thread_running:
                logger.warning(
                    'Live link already running for %s', self.line_name
                )
                return
            self._live_thread_running = True

        def poll_loop() -> None:
            """Polling loop that runs in a separate thread."""
            while True:
                with self._live_thread_lock:
                    if not self._live_thread_running:
                        break

                try:
                    self._poll_track_model()
                except Exception:
                    logger.exception('Error during Track Model polling loop')

                time.sleep(poll_interval)

        thread = threading.Thread(
            target=poll_loop,
            daemon=True,
            name=f'TrackPoll-{self.line_name}',
        )
        thread.start()
        logger.info(
            'Live link started for %s (poll interval: %.1fs)',
            self.line_name,
            poll_interval,
        )

    def stop_live_link(self) -> None:
        """Stop live polling of Track Model state."""
        with self._live_thread_lock:
            self._live_thread_running = False
        logger.info('Live link stopped for %s', self.line_name)

    def _poll_track_model(self) -> None:
        """Poll the Track Model for state changes."""
        if not hasattr(self.track_model, 'segments'):
            return

        state_changed = False
        occupancy_changed = False

        for block_id in self._line_block_ids():
            segment = self.track_model.segments.get(block_id)
            if segment is None:
                continue

            try:
                # Check occupancy
                current_occ = getattr(segment, 'occupied', None)
                if current_occ is not None:
                    known_occ = self._known_occupancy.get(block_id)
                    if known_occ != current_occ:
                        self._update_occupancy_from_model(block_id, current_occ)
                        state_changed = True
                        occupancy_changed = True

                # Check switch signals
                if hasattr(segment, 'straight_signal_state'):
                    if hasattr(segment, 'previous_signal_state'):
                        current_prev = segment.previous_signal_state
                        known_prev = self._switch_signals.get((block_id, 0))
                        if known_prev != current_prev:
                            self._switch_signals[(block_id, 0)] = current_prev
                            logger.info(
                                'Switch %d previous signal updated from model: %s',
                                block_id,
                                current_prev,
                            )
                            state_changed = True

                    current_straight = segment.straight_signal_state
                    known_straight = self._switch_signals.get((block_id, 1))
                    if known_straight != current_straight:
                        self._switch_signals[(block_id, 1)] = current_straight
                        logger.info(
                            'Switch %d straight signal updated from model: %s',
                            block_id,
                            current_straight,
                        )
                        state_changed = True

                    if hasattr(segment, 'diverging_signal_state'):
                        current_div = segment.diverging_signal_state
                        known_div = self._switch_signals.get((block_id, 2))
                        if known_div != current_div:
                            self._switch_signals[(block_id, 2)] = current_div
                            logger.info(
                                'Switch %d diverging signal updated from model: %s',
                                block_id,
                                current_div,
                            )
                            state_changed = True
                else:
                    # Regular signal
                    current_signal = getattr(segment, 'signal_state', None)
                    if current_signal is not None:
                        known_signal = self._known_signal.get(block_id)
                        if known_signal != current_signal:
                            self._known_signal[block_id] = current_signal
                            logger.info(
                                'Signal %d state updated from model -> %s',
                                block_id,
                                current_signal,
                            )
                            state_changed = True

                # Check switch position
                if hasattr(segment, 'current_position'):
                    current_pos = int(segment.current_position)
                    known_pos = self.switches.get(block_id)
                    if known_pos != current_pos:
                        self.switches[block_id] = current_pos
                        logger.info(
                            'Switch %d position updated from model -> %d',
                            block_id,
                            current_pos,
                        )
                        state_changed = True

                # Check crossing gate status
                if hasattr(segment, 'gate_status'):
                    current_gate = bool(segment.gate_status)
                    for cid, cblock in self.crossing_blocks.items():
                        if cblock == block_id:
                            known_state = self.crossings.get(cid)
                            if known_state != current_gate:
                                self.crossings[cid] = current_gate
                                logger.info(
                                    'Crossing %d status updated from model -> %s',
                                    cid,
                                    current_gate,
                                )
                                state_changed = True
                                break

                # Check commanded values
                if hasattr(segment, 'active_command') and segment.active_command:
                    cmd = segment.active_command

                    if hasattr(cmd, 'commanded_speed') and cmd.commanded_speed:
                        speed_mps = int(cmd.commanded_speed)
                        known_speed = self._known_commanded_speed.get(block_id)
                        if known_speed != speed_mps:
                            self._commanded_speed_mps[block_id] = speed_mps
                            self._known_commanded_speed[block_id] = speed_mps
                            logger.debug(
                                'Block %d commanded speed synced: %d m/s',
                                block_id,
                                speed_mps,
                            )

                    if hasattr(cmd, 'authority') and cmd.authority:
                        auth_m = int(cmd.authority)
                        known_auth = self._known_commanded_auth.get(block_id)
                        if known_auth != auth_m:
                            self._commanded_auth_m[block_id] = auth_m
                            self._known_commanded_auth[block_id] = auth_m
                            logger.debug(
                                'Block %d commanded authority synced: %d m',
                                block_id,
                                auth_m,
                            )

            except Exception as error:
                logger.debug('Error polling block %d: %s', block_id, error)
                continue

        # Only execute PLC if not in maintenance mode
        if occupancy_changed and self._plc_module is not None:
            if not self.maintenance_mode:
                logger.info('Occupancy changed, re-executing PLC logic')
                self._execute_plc_logic()
            else:
                logger.info('Occupancy changed, but PLC execution skipped (maintenance mode)')

        if state_changed:
            self._notify_listeners()
            self._send_status_to_ctc()

        self._verify_commands()

    def _line_block_ids(self) -> List[int]:
        """Get the list of block IDs for this line.

        Returns:
            List of block IDs that belong to this line.
        """
        block_range = LINE_BLOCK_MAP.get(self.line_name)
        if block_range is None:
            return sorted(self.track_model.segments.keys())
        return [b for b in block_range if b in self.track_model.segments]

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Add a listener callback for state changes.

        Args:
            callback: Function to call when state changes.
        """
        if callback not in self._listeners:
            self._listeners.append(callback)
            logger.debug(
                'Added listener %r for %s', callback, self.line_name
            )

    def remove_listener(self, callback: Callable[[], None]) -> None:
        """Remove a listener callback.

        Args:
            callback: The callback function to remove.
        """
        try:
            self._listeners.remove(callback)
            logger.debug(
                'Removed listener %r for %s', callback, self.line_name
            )
        except ValueError:
            logger.debug(
                'Listener %r not registered for %s',
                callback,
                self.line_name,
            )

    def _notify_listeners(self) -> None:
        """Notify all registered listeners of state changes."""
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.exception(
                    'Listener %r raised exception while notifying', callback
                )

    def set_maintenance_mode(self, enabled: bool) -> None:
        """Enable or disable maintenance mode.

        Args:
            enabled: Whether to enable maintenance mode.
        """
        self.maintenance_mode = bool(enabled)
        logger.info(
            '%s: Maintenance mode -> %s', self.line_name, self.maintenance_mode
        )
        self._notify_listeners()

    def _get_segment(self, block: int):
        """Get the Track Model segment for a block.

        Args:
            block: The block ID to get.

        Returns:
            The track segment object.

        Raises:
            ValueError: If block is invalid or not part of this line.
        """
        seg = self.track_model.segments.get(block)
        if seg is None:
            raise ValueError(f'Invalid block {block}')
        if block not in self._line_block_ids():
            raise ValueError(f'Block {block} is not part of {self.line_name}')
        return seg

    @property
    def blocks(self) -> Dict[int, Dict[str, Any]]:
        """Get formatted block data for all blocks on this line.

        Returns:
            Dictionary mapping block IDs to their data.
        """
        blocks_dict: Dict[int, Dict[str, Any]] = {}

        for block_id in self._line_block_ids():
            if block_id not in self.track_model.segments:
                continue

            try:
                # Occupancy
                if block_id in self._known_occupancy:
                    occupied_val = bool(self._known_occupancy[block_id])
                else:
                    occupied_val = 'N/A'

                # Suggested speed
                if block_id in self._suggested_speed_mps:
                    suggested_speed_mps = self._suggested_speed_mps[block_id]
                    suggested_speed_mph = ConversionFunctions.mps_to_mph(
                        suggested_speed_mps
                    )
                    suggested_speed_mph = int(round(suggested_speed_mph))
                else:
                    suggested_speed_mph = 'N/A'

                # Suggested authority
                if block_id in self._suggested_auth_m:
                    suggested_auth_m = self._suggested_auth_m[block_id]
                    suggested_auth_yd = ConversionFunctions.meters_to_yards(
                        suggested_auth_m
                    )
                    suggested_auth_yd = int(round(suggested_auth_yd))
                else:
                    suggested_auth_yd = 'N/A'

                # Commanded speed
                if block_id in self._commanded_speed_mps:
                    commanded_speed_mps = self._commanded_speed_mps[block_id]
                    commanded_speed_mph = ConversionFunctions.mps_to_mph(
                        commanded_speed_mps
                    )
                    commanded_speed_mph = int(math.ceil(commanded_speed_mph))
                elif block_id in self._known_commanded_speed:
                    commanded_speed_mps = self._known_commanded_speed[block_id]
                    commanded_speed_mph = ConversionFunctions.mps_to_mph(
                        commanded_speed_mps
                    )
                    commanded_speed_mph = int(math.ceil(commanded_speed_mph))
                else:
                    commanded_speed_mph = 'N/A'

                # Commanded authority
                if block_id in self._commanded_auth_m:
                    commanded_auth_m = self._commanded_auth_m[block_id]
                    commanded_auth_yd = ConversionFunctions.meters_to_yards(
                        commanded_auth_m
                    )
                    commanded_auth_yd = int(math.ceil(commanded_auth_yd))
                elif block_id in self._known_commanded_auth:
                    commanded_auth_m = self._known_commanded_auth[block_id]
                    commanded_auth_yd = ConversionFunctions.meters_to_yards(
                        commanded_auth_m
                    )
                    commanded_auth_yd = int(math.ceil(commanded_auth_yd))
                else:
                    commanded_auth_yd = 'N/A'

                # Signal state
                if block_id in self.switches:
                    signal_val = {
                        'previous': self._switch_signals.get(
                            (block_id, 0), 'N/A'
                        ),
                        'straight': self._switch_signals.get(
                            (block_id, 1), 'N/A'
                        ),
                        'diverging': self._switch_signals.get(
                            (block_id, 2), 'N/A'
                        ),
                    }
                elif block_id in self._known_signal:
                    signal_val = self._known_signal[block_id]
                else:
                    signal_val = 'N/A'

                blocks_dict[block_id] = {
                    'occupied': occupied_val,
                    'suggested_speed': suggested_speed_mph,
                    'suggested_auth': suggested_auth_yd,
                    'commanded_speed': commanded_speed_mph,
                    'commanded_auth': commanded_auth_yd,
                    'signal': signal_val,
                }

            except Exception as error:
                logger.debug('Error building block %d data: %s', block_id, error)
                continue

        return blocks_dict

    @property
    def num_blocks(self) -> int:
        """Get the number of blocks on this line.

        Returns:
            Number of blocks.
        """
        return len(self._line_block_ids())

    def set_block_occupancy(self, block: int, status: bool) -> None:
        """Manually set block occupancy status.

        Args:
            block: The block to set.
            status: The occupancy status.
        """
        seg = self._get_segment(block)
        seg.set_occupancy(bool(status))
        self._known_occupancy[block] = bool(status)
        logger.info(
            '%s: Block %d occupancy -> %s', self.line_name, block, status
        )
        self._notify_listeners()
        self._send_status_to_ctc()

    def set_signal(
        self,
        block: int,
        color: Union[str, SignalState],
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
                enum_name = str(color).replace(' ', '').upper()
                state = SignalState[enum_name]
            except (KeyError, AttributeError):
                raise ValueError(f'Invalid signal color "{color}"')

        if block in self.switches:
            if not hasattr(self, '_switch_signals'):
                self._switch_signals = {}
            self._switch_signals[(block, signal_side)] = state
        else:
            self._known_signal[block] = state

        try:
            self.track_model.set_signal_state(block, signal_side, state)
            logger.info(
                'Sent to Track Model: Block %d signal (side %d) -> %s',
                block,
                signal_side,
                state.name,
            )
        except Exception as error:
            logger.warning(
                'Failed to set signal %d (side %d) in Track Model: %s',
                block,
                signal_side,
                error,
            )

        self._notify_listeners()
        self._send_status_to_ctc()
        self._detect_power_failure(block, f'signal_{signal_side}', state)

    def safe_set_switch(
        self, switch_id: int, position: Union[int, str]
    ) -> None:
        """Safely set switch position with occupancy checks.

        Args:
            switch_id: The switch to control.
            position: Switch position (0/'Normal' or 1/'Alternate').

        Raises:
            PermissionError: If not in maintenance mode.
            ValueError: If position is invalid.
            SafetyException: If blocks are occupied.
        """
        if not self.maintenance_mode:
            raise PermissionError(
                'Must be in maintenance mode to change switches'
            )

        if isinstance(position, str):
            pos_str = position.title()
            if pos_str == 'Normal':
                pos_int = 0
            elif pos_str == 'Alternate':
                pos_int = 1
            else:
                raise ValueError(f'Invalid switch position: {position}')
        else:
            pos_int = int(position)
            if pos_int not in (0, 1):
                raise ValueError('Invalid switch position. Must be 0 or 1.')

        # Get blocks connected to switch
        blocks = self.switch_map.get(switch_id)
        if not blocks and switch_id in self.track_model.segments:
            seg = self.track_model.segments[switch_id]
            if hasattr(seg, 'straight_segment') and hasattr(
                seg, 'diverging_segment'
            ):
                blocks = tuple(
                    b.block_id
                    for b in (seg.straight_segment, seg.diverging_segment)
                    if b is not None
                )
                self.switch_map[switch_id] = blocks

        # Safety check: ensure no blocks are occupied
        if blocks:
            for block_id in blocks:
                if block_id in self.track_model.segments:
                    if getattr(
                        self.track_model.segments[block_id], 'occupied', False
                    ):
                        raise SafetyException(
                            f'Cannot change switch {switch_id}: '
                            f'block {block_id} is occupied'
                        )

        # Store old position in case we need to revert
        old_position = self.switches.get(switch_id, 0)
        
        # Update local state
        self.switches[switch_id] = pos_int

        try:
            # Update Track Model
            self.track_model.set_switch_position(switch_id, pos_int)
            logger.info(
                'Sent to Track Model: Switch %d -> %d', switch_id, pos_int
            )
            
            # Verify the update by reading back from Track Model
            if switch_id in self.track_model.segments:
                segment = self.track_model.segments[switch_id]
                if hasattr(segment, 'current_position'):
                    actual_position = segment.current_position
                    if actual_position != pos_int:
                        logger.error(
                            'Switch %d position mismatch: expected %d, got %d',
                            switch_id, pos_int, actual_position
                        )
                        # Revert local state
                        self.switches[switch_id] = old_position
                        raise RuntimeError(
                            f'Switch {switch_id} failed to update in Track Model'
                        )
                    else:
                        logger.info(
                            'Verified switch %d position: %d', 
                            switch_id, actual_position
                        )
                        
        except Exception as error:
            logger.exception(
                'Failed to set switch %d in Track Model: %s',
                switch_id,
                error,
            )
            # Revert local state on failure
            self.switches[switch_id] = old_position
            raise  # Re-raise to show error in UI

        self._notify_listeners()
        self._send_status_to_ctc()


    def safe_set_crossing(
        self, crossing_id: int, status: Union[bool, str]
    ) -> None:
        """Safely set crossing gate status with occupancy checks.

        Args:
            crossing_id: The crossing to control.
            status: Gate status (True/'Active' or False/'Inactive').

        Raises:
            PermissionError: If not in maintenance mode.
            ValueError: If status is invalid.
            SafetyException: If trying to deactivate while occupied.
        """
        if not self.maintenance_mode:
            raise PermissionError(
                'Must be in maintenance mode to change crossings'
            )

        if isinstance(status, str):
            stat_str = status.title()
            if stat_str == 'Active':
                stat_bool = True
            elif stat_str == 'Inactive':
                stat_bool = False
            else:
                raise ValueError(f'Invalid crossing status: {status}')
        else:
            stat_bool = bool(status)

        # Safety check: cannot deactivate if block is occupied
        block = self.crossing_blocks.get(crossing_id)
        if block and block in self.track_model.segments:
            if getattr(self.track_model.segments[block], 'occupied', False):
                if not stat_bool:
                    raise SafetyException(
                        f'Cannot set crossing {crossing_id} inactive: '
                        f'block {block} is occupied'
                    )

        # Store old status in case we need to revert
        old_status = self.crossings.get(crossing_id, False)
        
        # Update local state
        self.crossings[crossing_id] = stat_bool

        if block:
            try:
                seg = self.track_model.segments[block]
                if hasattr(seg, 'set_gate_status'):
                    seg.set_gate_status(stat_bool)
                    logger.info(
                        'Track Model: Crossing %d (block %d) gate status set to: %s',
                        crossing_id,
                        block,
                        stat_bool,
                    )
                    
                    # Verify the update by reading back from Track Model
                    if hasattr(seg, 'gate_status'):
                        actual_status = seg.gate_status
                        if actual_status != stat_bool:
                            logger.error(
                                'Crossing %d status mismatch: expected %s, got %s',
                                crossing_id, stat_bool, actual_status
                            )
                            # Revert local state
                            self.crossings[crossing_id] = old_status
                            raise RuntimeError(
                                f'Crossing {crossing_id} failed to update in Track Model'
                            )
                        else:
                            logger.info(
                                'Verified crossing %d status: %s',
                                crossing_id, actual_status
                            )
                else:
                    logger.warning(
                        'Block %d does not have set_gate_status method', block
                    )
                    # Revert since we can't actually set it
                    self.crossings[crossing_id] = old_status
                    raise RuntimeError(
                        f'Block {block} does not support crossing control'
                    )
            except Exception as error:
                logger.exception(
                    'Failed to set crossing %d in Track Model: %s',
                    crossing_id,
                    error,
                )
                # Revert local state on failure
                self.crossings[crossing_id] = old_status
                raise  # Re-raise to show error in UI

        self._notify_listeners()
        self._send_status_to_ctc()
