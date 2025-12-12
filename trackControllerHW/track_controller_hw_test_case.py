"""Hardware Track Controller Test Cases."""
from __future__ import annotations

import logging
import os
import sys
import tempfile

import pytest
from datetime import timedelta

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)

from track_controller_hw_backend import (
    HardwareTrackControllerBackend,
    SignalState,
)


class MockTrackNetwork:
    """Mock track network for testing."""

    def __init__(self):
        self.segments = {}
        self.broadcast_calls = []
        self.signal_calls = []
        self.switch_calls = []
        self.gate_calls = []

    def broadcast_train_command(self, block_id: int, speed: int, authority: int):
        self.broadcast_calls.append((block_id, speed, authority))

    def set_signal_state(self, block_id: int, signal_side: int, state: SignalState):
        self.signal_calls.append((block_id, signal_side, state))

    def set_switch_position(self, switch_id: int, position: int):
        self.switch_calls.append((switch_id, position))

    def set_gate_status(self, block_id: int, status: bool):
        self.gate_calls.append((block_id, status))

    def ensure_blocks(self, ids: list[int]):
        for i in ids:
            if i not in self.segments:
                self.segments[i] = MockSegment(i)


class MockSegment:
    """Mock track segment for testing."""

    def __init__(self, block_id: int):
        self.block_id = block_id
        self.occupied = False
        self.signal_state = SignalState.RED
        self.current_position = 0
        self.gate_status = False

    def set_occupancy(self, status: bool):
        self.occupied = status

    def set_gate_status(self, status: bool):
        self.gate_status = status


class MockCTCBackend:
    """Mock CTC backend for testing."""

    def __init__(self):
        self.occupancy_updates = []
        self.signal_updates = []
        self.switch_updates = []
        self.crossing_updates = []
        self.wayside_status_calls = []

    def update_block_occupancy(self, line: str, block: int, occupied: bool):
        self.occupancy_updates.append((line, block, occupied))

    def update_signal_state(self, line: str, block: int, state: SignalState):
        self.signal_updates.append((line, block, state))

    def update_switch_position(self, line: str, block: int, position: int):
        self.switch_updates.append((line, block, position))

    def update_crossing_status(self, line: str, block: int, status: bool):
        self.crossing_updates.append((line, block, status))

    def receive_wayside_status(self, line: str, status_updates: list):
        self.wayside_status_calls.append((line, status_updates))


@pytest.fixture
def mock_track_model():
    """Create mock track model with segments."""
    track = MockTrackNetwork()
    for i in range(1, 151):
        track.segments[i] = MockSegment(i)
    return track


@pytest.fixture
def green_controller(mock_track_model):
    """Create Green Line hardware controller."""
    return HardwareTrackControllerBackend(mock_track_model, "Green Line")


@pytest.fixture
def red_controller(mock_track_model):
    """Create Red Line hardware controller."""
    return HardwareTrackControllerBackend(mock_track_model, "Red Line")


@pytest.fixture
def mock_ctc():
    """Create mock CTC backend."""
    return MockCTCBackend()


class TestApplyPLCCommandsToBlock:
    """Test PLC command application to blocks."""

    def test_plc_sets_signal_red_on_occupied_next_block(self, green_controller):
        """PLC sets RED signal when next block is occupied."""
        green_controller.set_maintenance_mode(True)
        green_controller._known_occupancy[65] = True

        plc_content = """
TERRITORY = list(range(63, 122))

def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    n = len(block_occupancies)
    for b in range(63, 122):
        if b < len(light_signals):
            next_block = b + 1
            if next_block < n and block_occupancies[next_block]:
                light_signals[b] = False
            else:
                light_signals[b] = True
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller._known_signal.get(64) == SignalState.RED
        finally:
            os.unlink(plc_path)

    def test_plc_sets_signal_green_on_clear_next_block(self, green_controller):
        """PLC sets GREEN signal when next block is clear."""
        green_controller.set_maintenance_mode(True)
        green_controller._known_occupancy[65] = False
        green_controller._known_occupancy[64] = False

        plc_content = """
TERRITORY = list(range(63, 122))

def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    n = len(block_occupancies)
    for b in range(63, 122):
        if b < len(light_signals):
            next_block = b + 1
            if next_block < n and block_occupancies[next_block]:
                light_signals[b] = False
            else:
                light_signals[b] = True
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller._known_signal.get(64) == SignalState.GREEN
        finally:
            os.unlink(plc_path)

    def test_plc_sets_stop_flag_on_collision_risk(self, green_controller):
        """PLC sets stop flag on collision risk."""
        green_controller.set_maintenance_mode(True)
        green_controller._known_occupancy[70] = True
        green_controller._known_occupancy[71] = True

        plc_content = """
TERRITORY = list(range(63, 122))

def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    n = len(block_occupancies)
    for b in range(63, 121):
        if b < len(stop):
            next_block = b + 1
            if next_block < n and block_occupancies[next_block]:
                stop[b] = True
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller._commanded_speed_mph.get(70) == 0
        finally:
            os.unlink(plc_path)

    def test_plc_commands_applied_to_correct_territory(self, green_controller):
        """PLC commands only affect blocks in territory."""
        green_controller.set_maintenance_mode(True)

        plc_content = """
TERRITORY = list(range(63, 122))

def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    for b in range(63, 122):
        if b < len(light_signals):
            light_signals[b] = True
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            for b in range(63, 122):
                if b not in green_controller.switch_map:
                    assert green_controller._known_signal.get(b) == SignalState.GREEN
        finally:
            os.unlink(plc_path)


class TestPLCFileUploading:
    """Test PLC file upload."""

    def test_upload_python_plc_file(self, green_controller):
        """Upload Python PLC file."""
        green_controller.set_maintenance_mode(True)

        plc_content = """
def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller._plc_logic_module is not None
        finally:
            os.unlink(plc_path)

    def test_upload_text_plc_file(self, green_controller):
        """Upload text PLC file with commands."""
        green_controller.set_maintenance_mode(True)

        plc_content = """SIGNAL 70 GREEN
CMD_SPEED 70 25
CMD_AUTH 70 100
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller._known_signal.get(70) == SignalState.GREEN
            assert green_controller._commanded_speed_mph.get(70) == 25
            assert green_controller._commanded_auth_yd.get(70) == 100
        finally:
            os.unlink(plc_path)

    def test_upload_plc_requires_maintenance_mode(self, green_controller):
        """PLC upload requires maintenance mode."""
        green_controller.set_maintenance_mode(False)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("# empty")
            plc_path = f.name

        try:
            with pytest.raises(PermissionError):
                green_controller.upload_plc(plc_path)
        finally:
            os.unlink(plc_path)

    def test_upload_plc_nonexistent_file(self, green_controller, caplog):
        """Upload fails for nonexistent file."""
        green_controller.set_maintenance_mode(True)
        with caplog.at_level(logging.ERROR):
            green_controller.upload_plc("/nonexistent/path/plc.py")
        assert "not found" in caplog.text.lower()

    def test_upload_plc_with_invalid_syntax(self, green_controller, caplog):
        """Upload handles invalid Python syntax."""
        green_controller.set_maintenance_mode(True)

        plc_content = """
def plc_logic(
    this is not valid python
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            with caplog.at_level(logging.ERROR):
                green_controller.upload_plc(plc_path)
        finally:
            os.unlink(plc_path)


class TestCrossingGateChange:
    """Test crossing gate changes."""

    def test_crossing_activates_on_train_approach(self, green_controller):
        """Crossing activates when train approaches."""
        green_controller.crossing_blocks[1] = 108
        green_controller.crossings[1] = "Inactive"

        green_controller._on_occupancy_change(108, True)

        assert green_controller.crossings[1] == "Active"

    def test_crossing_deactivates_when_train_leaves(self, green_controller):
        """Crossing deactivates when train leaves."""
        green_controller.crossing_blocks[1] = 108
        green_controller.crossings[1] = "Active"

        green_controller._on_occupancy_change(108, False)

        assert green_controller.crossings[1] == "Inactive"

    def test_manual_crossing_change_requires_maintenance(self, green_controller):
        """Manual crossing change requires maintenance mode."""
        green_controller.set_maintenance_mode(False)

        with pytest.raises(PermissionError):
            green_controller.safe_set_crossing(1, "Active")

    def test_manual_crossing_change_in_maintenance_mode(self, green_controller):
        """Manual crossing change works in maintenance mode."""
        green_controller.set_maintenance_mode(True)
        green_controller.crossing_blocks[1] = 108
        green_controller.crossings[1] = "Inactive"

        green_controller.safe_set_crossing(1, "Active")

        assert green_controller.crossings[1] == "Active"

    def test_crossing_status_sent_to_track_model(
        self, green_controller, mock_track_model
    ):
        """Crossing status sent to track model."""
        green_controller.crossing_blocks[1] = 108
        green_controller.crossings[1] = "Inactive"

        green_controller._on_occupancy_change(108, True)

        assert any(
            call[0] == 108 and call[1] is True for call in mock_track_model.gate_calls
        )

    def test_plc_controls_crossing(self, green_controller):
        """PLC logic controls crossing gates."""
        green_controller.set_maintenance_mode(True)
        green_controller._known_occupancy[107] = True

        plc_content = """
def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    if len(crossing_signals) > 0:
        train_near = any(
            block_occupancies[b] if b < len(block_occupancies) else False
            for b in range(105, 112)
        )
        crossing_signals[0] = train_near
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller.crossings.get(1) == "Active"
        finally:
            os.unlink(plc_path)


class TestSwitchChange:
    """Test switch position changes."""

    def test_switch_change_requires_maintenance_mode(self, green_controller):
        """Switch change requires maintenance mode."""
        green_controller.set_maintenance_mode(False)

        with pytest.raises(PermissionError):
            green_controller.safe_set_switch(77, "Diverging")

    def test_switch_change_in_maintenance_mode(self, green_controller):
        """Switch change works in maintenance mode."""
        green_controller.set_maintenance_mode(True)
        green_controller.switches[77] = "Straight"

        green_controller.safe_set_switch(77, "Diverging")

        assert green_controller.switches[77] == "Diverging"

    def test_switch_blocked_when_occupied(self, green_controller):
        """Switch cannot change when blocks are occupied."""
        green_controller.set_maintenance_mode(True)
        green_controller.switches[77] = "Straight"
        green_controller._known_occupancy[77] = True

        with pytest.raises(PermissionError):
            green_controller.safe_set_switch(77, "Diverging")

    def test_switch_position_straight(self, green_controller):
        """Switch can be set to straight."""
        green_controller.set_maintenance_mode(True)
        green_controller.switches[77] = "Diverging"

        green_controller.safe_set_switch(77, "Straight")

        assert green_controller.switches[77] == "Straight"

    def test_switch_position_diverging(self, green_controller):
        """Switch can be set to diverging."""
        green_controller.set_maintenance_mode(True)
        green_controller.switches[77] = "Straight"

        green_controller.safe_set_switch(77, "Diverging")

        assert green_controller.switches[77] == "Diverging"

    def test_switch_signals_update_on_position_change(self, green_controller):
        """Switch signals update on position change."""
        green_controller.set_maintenance_mode(True)
        green_controller.switches[77] = "Straight"

        green_controller.safe_set_switch(77, "Diverging")

        assert green_controller._switch_signals.get((77, 1)) == SignalState.RED
        assert green_controller._switch_signals.get((77, 2)) == SignalState.GREEN

    def test_switch_sent_to_track_model(self, green_controller, mock_track_model):
        """Switch changes sent to track model."""
        green_controller.set_maintenance_mode(True)
        green_controller.switches[77] = "Straight"

        green_controller.safe_set_switch(77, "Diverging")

        assert any(
            call[0] == 77 and call[1] == 1 for call in mock_track_model.switch_calls
        )

    def test_plc_controls_switch(self, green_controller):
        """PLC logic controls switches."""
        green_controller.set_maintenance_mode(True)
        green_controller._known_occupancy[100] = True

        plc_content = """
def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    if len(switch_positions) > 0:
        train_on_diverging = (
            block_occupancies[100] if 100 < len(block_occupancies) else False
        )
        if train_on_diverging:
            switch_positions[0] = True
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller.switches.get(77) == "Diverging"
        finally:
            os.unlink(plc_path)


class TestSuggestedToCommandedConversion:
    """Test suggested to commanded value conversion."""

    def test_suggested_speed_stored_correctly(self, green_controller):
        """Suggested speed stored after unit conversion."""
        green_controller.receive_ctc_suggestion(70, 10.0, 100.0)

        expected_mph = int(round(10.0 * 2.23694))
        assert green_controller._suggested_speed_mph[70] == expected_mph

    def test_suggested_authority_stored_correctly(self, green_controller):
        """Suggested authority stored after unit conversion."""
        green_controller.receive_ctc_suggestion(70, 10.0, 100.0)

        expected_yd = int(round(100.0 * 1.09361))
        assert green_controller._suggested_auth_yd[70] == expected_yd

    def test_suggested_values_become_commanded_via_plc(self, green_controller):
        """Suggested values become commanded when PLC approves."""
        green_controller.set_maintenance_mode(True)
        green_controller.receive_ctc_suggestion(70, 10.0, 100.0)
        green_controller._known_occupancy[70] = False
        green_controller._known_occupancy[71] = False

        plc_content = """
def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    for b in range(len(stop)):
        stop[b] = False
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            expected_mph = int(round(10.0 * 2.23694))
            expected_yd = int(round(100.0 * 1.09361))
            assert green_controller._commanded_speed_mph.get(70) == expected_mph
            assert green_controller._commanded_auth_yd.get(70) == expected_yd
        finally:
            os.unlink(plc_path)

    def test_suggested_values_blocked_by_plc_stop(self, green_controller):
        """Suggested values blocked when PLC sets stop flag."""
        green_controller.set_maintenance_mode(True)
        green_controller.receive_ctc_suggestion(70, 10.0, 100.0)
        green_controller._known_occupancy[71] = True

        plc_content = """
def plc_logic(block_occupancies, switch_positions, light_signals,
              crossing_signals, previous_occupancies, stop):
    n = len(block_occupancies)
    for b in range(n - 1):
        if b < len(stop) and b + 1 < n and block_occupancies[b + 1]:
            stop[b] = True
    return switch_positions, light_signals, crossing_signals, stop
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(plc_content)
            plc_path = f.name

        try:
            green_controller.upload_plc(plc_path)
            assert green_controller._commanded_speed_mph.get(70) == 0
            assert green_controller._commanded_auth_yd.get(70) == 0
        finally:
            os.unlink(plc_path)

    def test_conversion_mps_to_mph(self, green_controller):
        """Speed conversion from m/s to mph."""
        speed_mps = 15.0
        green_controller.receive_ctc_suggestion(70, speed_mps, 100.0)

        expected_mph = int(round(speed_mps * 2.23694))
        assert green_controller._suggested_speed_mph[70] == expected_mph

    def test_conversion_meters_to_yards(self, green_controller):
        """Authority conversion from meters to yards."""
        auth_m = 500.0
        green_controller.receive_ctc_suggestion(70, 10.0, auth_m)

        expected_yd = int(round(auth_m * 1.09361))
        assert green_controller._suggested_auth_yd[70] == expected_yd

    def test_suggestion_ignored_for_invalid_block(self, green_controller, caplog):
        """Suggestion ignored for blocks outside territory."""
        invalid_block = 999
        with caplog.at_level(logging.DEBUG):
            green_controller.receive_ctc_suggestion(invalid_block, 10.0, 100.0)

        assert invalid_block not in green_controller._suggested_speed_mph

    def test_commanded_values_broadcast_to_track_model(
        self, green_controller, mock_track_model
    ):
        """Commanded values broadcast to track model."""
        green_controller.set_commanded_speed(70, 25)
        green_controller.set_commanded_authority(70, 100)

        assert any(
            call[0] == 70 and call[1] == 25 for call in mock_track_model.broadcast_calls
        )
        assert any(
            call[0] == 70 and call[2] == 100
            for call in mock_track_model.broadcast_calls
        )


class TestInitialization:
    """Test controller initialization."""

    def test_green_line_initialization(self, mock_track_model):
        """Green Line controller initializes correctly."""
        controller = HardwareTrackControllerBackend(mock_track_model, "Green Line")
        assert controller.line_name == "Green Line"
        assert 77 in controller.switch_map
        assert 85 in controller.switch_map
        assert controller.crossing_blocks.get(1) == 108

    def test_red_line_initialization(self, mock_track_model):
        """Red Line controller initializes correctly."""
        controller = HardwareTrackControllerBackend(mock_track_model, "Red Line")
        assert controller.line_name == "Red Line"
        assert 38 in controller.switch_map
        assert 43 in controller.switch_map
        assert 52 in controller.switch_map
        assert controller.crossing_blocks.get(1) == 47


class TestMaintenanceMode:
    """Test maintenance mode."""

    def test_maintenance_mode_default_off(self, green_controller):
        """Maintenance mode off by default."""
        assert green_controller.maintenance_mode is False

    def test_set_maintenance_mode(self, green_controller):
        """Maintenance mode can be enabled."""
        green_controller.set_maintenance_mode(True)
        assert green_controller.maintenance_mode is True

    def test_clear_failures_requires_maintenance(self, green_controller):
        """Clearing failures requires maintenance mode."""
        green_controller.set_maintenance_mode(False)

        with pytest.raises(PermissionError):
            green_controller.clear_failures()


class TestCTCIntegration:
    """Test CTC backend integration."""

    def test_set_ctc_backend(self, green_controller, mock_ctc):
        """CTC backend can be set."""
        green_controller.set_ctc_backend(mock_ctc)
        assert green_controller.ctc_backend == mock_ctc

    def test_ctc_updates_can_be_disabled(self, green_controller):
        """CTC updates can be disabled."""
        green_controller.enable_ctc_updates(False)
        assert green_controller._ctc_update_enabled is False

    def test_status_sent_to_ctc(self, green_controller, mock_ctc):
        """Status updates sent to CTC."""
        green_controller.set_ctc_backend(mock_ctc)
        green_controller._known_occupancy[70] = True
        green_controller._send_status_to_ctc()

        assert len(mock_ctc.wayside_status_calls) > 0


class TestSignals:
    """Test signal functionality."""

    def test_set_signal_with_enum(self, green_controller):
        """Signal set with SignalState enum."""
        green_controller.set_signal(70, SignalState.GREEN)
        assert green_controller._known_signal[70] == SignalState.GREEN

    def test_set_signal_with_string(self, green_controller):
        """Signal set with string."""
        green_controller.set_signal(70, "YELLOW")
        assert green_controller._known_signal[70] == SignalState.YELLOW

    def test_set_invalid_signal(self, green_controller, caplog):
        """Invalid signal color logged."""
        with caplog.at_level(logging.WARNING):
            green_controller.set_signal(70, "PURPLE")


class TestFailureDetection:
    """Test failure detection."""

    def test_broken_rail_detection(self, green_controller):
        """Broken rail detected when block occupied without adjacency."""
        green_controller._known_occupancy[70] = False
        green_controller._occupancy_timestamps[69] = (
            green_controller.time - timedelta(seconds=60)
        )
        green_controller._occupancy_timestamps[71] = (
            green_controller.time - timedelta(seconds=60)
        )

        green_controller._check_broken_rail(70, True)

        assert any("broken_rail" in key for key in green_controller.failures.keys())

    def test_get_failure_report(self, green_controller):
        """Failure report can be retrieved."""
        report = green_controller.get_failure_report()
        assert "active" in report
        assert "history" in report
        assert "pending_commands" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])