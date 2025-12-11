from __future__ import annotations
import sys, os, logging, pytest, tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from collections import deque

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)

from universal.universal import SignalState, TrainCommand, ConversionFunctions
from track_controller_backend import (
    TrackControllerBackend, 
    SafetyException, 
    TrackModelMessage,
    WaysideStatusUpdate,
    FailureRecord,
    CommandVerification
)

class MockTrackNetwork:
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
        
    def get_wayside_status(self):
        return {"segments": {str(i): {"occupied": False, "signal_state": SignalState.RED} 
                for i in range(1, 151)}}

class MockSegment:
    def __init__(self, block_id: int):
        self.block_id = block_id
        self.occupied = False
        self.signal_state = SignalState.RED
        self.current_position = 0
        self.gate_status = False
        self.active_command = None
        self.straight_signal_state = SignalState.RED
        self.diverging_signal_state = SignalState.RED
        self.previous_signal_state = SignalState.RED
        
    def set_occupancy(self, status: bool):
        self.occupied = status
        
    def set_gate_status(self, status: bool):
        self.gate_status = status

class MockCTCBackend:
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
    track = MockTrackNetwork()
    for i in range(1, 151):
        track.segments[i] = MockSegment(i)
    return track

@pytest.fixture
def controller(mock_track_model):
    return TrackControllerBackend(mock_track_model, "Green Line")

@pytest.fixture
def mock_ctc():
    return MockCTCBackend()

# shit works
def test_initialization_green_line(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Green Line")
    assert controller.line_name == "Green Line"
    assert not controller.maintenance_mode
    assert controller.crossing_blocks == {1: 19}

def test_initialization_red_line(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Red Line")
    assert controller.line_name == "Red Line"
    assert controller.crossing_blocks == {1: 11, 2: 47}

def test_initial_sync(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Green Line")
    assert len(controller._known_occupancy) > 0

# ctc connection
def test_set_ctc_backend(controller, mock_ctc):
    controller.set_ctc_backend(mock_ctc)
    assert controller.ctc_backend == mock_ctc

def test_receive_ctc_suggestion(controller):
    block_id = 5
    suggested_speed = 25.0
    suggested_auth = 100.0
    controller.receive_ctc_suggestion(block_id, suggested_speed, suggested_auth)
    assert controller._suggested_speed_mps[block_id] == suggested_speed
    assert controller._suggested_auth_m[block_id] == suggested_auth

def test_receive_ctc_suggestion_invalid_block(controller, caplog):
    invalid_block = 999
    with caplog.at_level(logging.WARNING):
        controller.receive_ctc_suggestion(invalid_block, 20.0, 50.0)
    assert invalid_block not in controller._suggested_speed_mps
    assert "invalid block" in caplog.text.lower()

def test_ctc_updates_can_be_disabled(controller):
    controller.enable_ctc_updates(False)
    assert not controller._ctc_update_enabled
    controller.enable_ctc_updates(True)
    assert controller._ctc_update_enabled

def test_send_status_to_ctc(controller, mock_ctc):
    controller.set_ctc_backend(mock_ctc)
    controller._known_occupancy[5] = True
    controller._known_signal[5] = SignalState.GREEN
    controller._send_status_to_ctc()
    assert len(mock_ctc.wayside_status_calls) > 0

def test_send_status_to_ctc_disabled(controller, mock_ctc):
    controller.set_ctc_backend(mock_ctc)
    controller.enable_ctc_updates(False)
    controller._send_status_to_ctc()
    assert len(mock_ctc.wayside_status_calls) == 0

# commanded speed and commanded authority
def test_set_commanded_speed(controller, mock_track_model):
    block_id = 10
    speed_mps = 15
    controller.set_commanded_speed(block_id, speed_mps)
    assert controller._commanded_speed_mps[block_id] == speed_mps
    assert controller._known_commanded_speed[block_id] == speed_mps
    assert any(block_id == call[0] and speed_mps == call[1] 
               for call in mock_track_model.broadcast_calls)
    
def test_set_commanded_authority(controller, mock_track_model):
    block_id = 10
    authority_m = 200
    controller.set_commanded_authority(block_id, authority_m)
    assert controller._commanded_auth_m[block_id] == authority_m
    assert controller._known_commanded_auth[block_id] == authority_m
    assert any(block_id == call[0] and authority_m == call[2] 
               for call in mock_track_model.broadcast_calls)
    
def test_commanded_speed_invalid_block(controller, caplog):
    invalid_block = 999
    with caplog.at_level(logging.WARNING):
        controller.set_commanded_speed(invalid_block, 20)
    assert invalid_block not in controller._commanded_speed_mps

def test_commanded_authority_invalid_block(controller, caplog):
    invalid_block = 999
    with caplog.at_level(logging.WARNING):
        controller.set_commanded_authority(invalid_block, 100)
    assert invalid_block not in controller._commanded_auth_m

# signal
def test_set_signal_with_enum(controller, mock_track_model):
    block_id = 15
    controller.set_signal(block_id, SignalState.GREEN)
    assert controller._known_signal[block_id] == SignalState.GREEN

def test_set_signal_with_string(controller, mock_track_model):
    block_id = 15
    controller.set_signal(block_id, "YELLOW")
    assert controller._known_signal[block_id] == SignalState.YELLOW

def test_set_signal_invalid_color(controller):
    block_id = 15
    with pytest.raises(ValueError, match="Invalid signal color"):
        controller.set_signal(block_id, "PURPLE")

def test_set_signal_with_side(controller, mock_track_model):
    block_id = 15
    controller.set_signal(block_id, SignalState.GREEN, signal_side=2)
    assert any(block_id == call[0] and 2 == call[1] 
               for call in mock_track_model.signal_calls)

def test_set_signal_all_colors(controller):
    controller.set_signal(10, SignalState.RED)
    assert controller._known_signal[10] == SignalState.RED
    controller.set_signal(11, SignalState.YELLOW)
    assert controller._known_signal[11] == SignalState.YELLOW
    controller.set_signal(12, SignalState.GREEN)
    assert controller._known_signal[12] == SignalState.GREEN
    controller.set_signal(13, SignalState.SUPERGREEN)
    assert controller._known_signal[13] == SignalState.SUPERGREEN

# switches
def test_safe_set_switch_maintenance_mode(controller):
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    controller.safe_set_switch(5, 1)
    assert controller.switches[5] == 1
    
def test_safe_set_switch_no_maintenance_mode(controller):
    controller.set_maintenance_mode(False)
    controller.switches[5] = 0
    with pytest.raises(PermissionError, match="maintenance mode"):
        controller.safe_set_switch(5, 1)

def test_safe_set_switch_occupied_block(controller, mock_track_model):
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    controller.switch_map[5] = (5, 6)
    mock_track_model.segments[5].occupied = True
    with pytest.raises(SafetyException, match="occupied"):
        controller.safe_set_switch(5, 1)

def test_switch_position_string_conversion(controller):
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    controller.safe_set_switch(5, "Alternate")
    assert controller.switches[5] == 1
    controller.safe_set_switch(5, "Normal")
    assert controller.switches[5] == 0

def test_switch_position_invalid_value(controller):
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    with pytest.raises(ValueError):
        controller.safe_set_switch(5, 5)

def test_plc_set_switch(controller, mock_track_model):
    controller.switches[5] = 0
    controller._plc_set_switch(5, 1)
    assert controller.switches[5] == 1
    assert any(5 == call[0] and 1 == call[1] 
               for call in mock_track_model.switch_calls)

# crossing 
def test_safe_set_crossing_maintenance_mode(controller, mock_track_model):
    controller.set_maintenance_mode(True)
    controller.crossings[1] = False
    controller.crossing_blocks[1] = 19
    controller.safe_set_crossing(1, True)
    assert controller.crossings[1] == True

def test_safe_set_crossing_no_maintenance_mode(controller):
    controller.set_maintenance_mode(False)
    controller.crossings[1] = False
    with pytest.raises(PermissionError, match="maintenance mode"):
        controller.safe_set_crossing(1, True)

def test_crossing_occupied_block_safety(controller, mock_track_model):
    controller.set_maintenance_mode(True)
    controller.crossings[1] = True
    controller.crossing_blocks[1] = 19
    mock_track_model.segments[19].occupied = True
    with pytest.raises(SafetyException, match="occupied"):
        controller.safe_set_crossing(1, False)
        
def test_crossing_string_conversion(controller):
    controller.set_maintenance_mode(True)
    controller.crossings[1] = False
    controller.crossing_blocks[1] = 19
    controller.safe_set_crossing(1, "Active")
    assert controller.crossings[1] == True
    controller.safe_set_crossing(1, "Inactive")
    assert controller.crossings[1] == False

def test_plc_set_crossing(controller, mock_track_model):
    controller.crossings[1] = False
    controller.crossing_blocks[1] = 19
    controller._plc_set_crossing(1, True)
    assert controller.crossings[1] == True

def test_crossing_auto_management_on_occupancy(controller, mock_track_model):
    controller.crossing_blocks[1] = 19
    controller._update_occupancy_from_model(19, True)
    assert controller.crossings[1] == True

# occupancy
def test_set_block_occupancy(controller, mock_track_model):
    block_id = 20
    controller.set_block_occupancy(block_id, True)
    assert controller._known_occupancy[block_id] == True
    assert mock_track_model.segments[block_id].occupied == True
    
def test_occupancy_cleared_restores_authority(controller):
    block_id = 20
    controller._suggested_auth_m[block_id] = 150
    controller._update_occupancy_from_model(block_id, False)
    assert controller._commanded_auth_m[block_id] == 150

def test_update_occupancy_from_model(controller):
    block_id = 25
    controller._update_occupancy_from_model(block_id, True)
    assert controller._known_occupancy[block_id] == True

def test_occupancy_triggers_plc_execution(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.py"
    plc_file.write_text("""def plc_logic(block_occupancies, switch_positions, light_signals, crossing_signals, previous_occupancies, stop): return switch_positions, light_signals, crossing_signals, stop""")
    controller.upload_plc(str(plc_file))
    old_state = controller._known_occupancy.get(10, False)
    controller._update_occupancy_from_model(10, not old_state)

# plc upload
def test_plc_upload_requires_maintenance_mode(controller, tmp_path):
    controller.set_maintenance_mode(False)
    plc_file = tmp_path / "test.txt"
    plc_file.write_text("SIGNAL 1 GREEN")
    with pytest.raises(PermissionError, match="maintenance mode"):
        controller.upload_plc(str(plc_file))

def test_plc_python_file(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.py"
    plc_file.write_text("""def plc_logic(block_occupancies, switch_positions, light_signals, crossing_signals, previous_occupancies, stop): return switch_positions, light_signals, crossing_signals, stop""")
    controller.upload_plc(str(plc_file))
    assert controller._plc_module is not None

def test_plc_python_execution(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.py"
    plc_file.write_text("""def plc_logic(block_occupancies, switch_positions, light_signals, crossing_signals, previous_occupancies, stop): switch_positions[0] = return switch_positions, light_signals, crossing_signals, stop""")
    controller.switches[1] = 0
    controller.upload_plc(str(plc_file))

def test_plc_invalid_file(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.py"
    plc_file.write_text("invalid python syntax !!!")
    controller.upload_plc(str(plc_file))

# track model connection 
def test_receive_occupancy_update(controller):
    block_id = 25
    controller.receive_model_update(block_id, "occupancy", True)
    assert controller._known_occupancy[block_id] == True

def test_receive_signal_update(controller):
    block_id = 25
    controller.receive_model_update(block_id, "signal", SignalState.GREEN)
    assert controller._known_signal[block_id] == SignalState.GREEN

def test_receive_switch_update(controller):
    switch_id = 5
    controller.switches[switch_id] = 0
    controller.receive_model_update(switch_id, "switch", 1)
    assert controller.switches[switch_id] == 1

def test_receive_crossing_update(controller):
    controller.crossing_blocks[1] = 19
    controller.receive_model_update(19, "crossing", True)
    assert controller.crossings[1] == True

def test_receive_unknown_attribute(controller, caplog):
    with caplog.at_level(logging.WARNING):
        controller.receive_model_update(10, "unknown_attr", "value")
    assert "unknown" in caplog.text.lower()

def test_message_queue(controller):
    controller.receive_model_update(10, "occupancy", True)
    assert len(controller.incoming_messages) == 0

# state reporting
def test_report_state_structure(controller):
    state = controller.report_state()
    assert "line" in state
    assert "maintenance_mode" in state
    assert "blocks" in state
    assert "switches" in state
    assert "crossing" in state
    assert "failures" in state

def test_blocks_property_conversions(controller):
    block_id = 30
    controller._suggested_speed_mps[block_id] = 20.0
    controller._suggested_auth_m[block_id] = 100.0
    blocks = controller.blocks
    assert blocks[block_id]["suggested_speed"] > 0
    assert blocks[block_id]["suggested_auth"] > 0

def test_blocks_property_with_commands(controller):
    block_id = 30
    controller._commanded_speed_mps[block_id] = 15
    controller._commanded_auth_m[block_id] = 80
    blocks = controller.blocks
    assert blocks[block_id]["commanded_speed"] != "N/A"
    assert blocks[block_id]["commanded_auth"] != "N/A"

def test_blocks_property_occupancy(controller):
    block_id = 30
    controller._known_occupancy[block_id] = True
    blocks = controller.blocks
    assert blocks[block_id]["occupied"] == True

def test_blocks_property_signal_state(controller):
    block_id = 30
    controller._known_signal[block_id] = SignalState.GREEN
    blocks = controller.blocks
    assert blocks[block_id]["signal"] == SignalState.GREEN

def test_num_blocks_property(controller):
    assert controller.num_blocks > 0

# listeners
def test_add_listener(controller):
    callback = Mock()
    controller.add_listener(callback)
    assert callback in controller._listeners
    
def test_listener_called_on_update(controller):
    callback = Mock()
    controller.add_listener(callback)
    controller.set_maintenance_mode(True)
    callback.assert_called()
    
def test_remove_listener(controller):
    callback = Mock()
    controller.add_listener(callback)
    controller.remove_listener(callback)
    assert callback not in controller._listeners

def test_listener_exception_handling(controller):
    def bad_callback():
        raise Exception("Test exception")
    controller.add_listener(bad_callback)
    controller._notify_listeners()

def test_multiple_listeners(controller):
    callback1 = Mock()
    callback2 = Mock()
    controller.add_listener(callback1)
    controller.add_listener(callback2)
    controller._notify_listeners()
    callback1.assert_called()
    callback2.assert_called()


# time
def test_set_time(controller):
    new_time = datetime(2024, 1, 1, 12, 0, 0)
    controller.set_time(new_time)
    assert controller.time == new_time

def test_manual_set_time(controller):
    controller.manual_set_time(2024, 6, 15, 14, 30, 45)
    assert controller.time.year == 2024
    assert controller.time.month == 6
    assert controller.time.day == 15
    assert controller.time.hour == 14
    assert controller.time.minute == 30
    assert controller.time.second == 45

# maintenance mode
def test_enable_maintenance_mode(controller):
    controller.set_maintenance_mode(True)
    assert controller.maintenance_mode == True

def test_disable_maintenance_mode(controller):
    controller.set_maintenance_mode(True)
    controller.set_maintenance_mode(False)
    assert controller.maintenance_mode == False

def test_maintenance_mode_enables_switch_control(controller):
    controller.set_maintenance_mode(False)
    with pytest.raises(PermissionError):
        controller.safe_set_switch(5, 1)
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    controller.safe_set_switch(5, 1)

def test_maintenance_mode_enables_crossing_control(controller):
    controller.set_maintenance_mode(False)
    with pytest.raises(PermissionError):
        controller.safe_set_crossing(1, True)
    controller.set_maintenance_mode(True)
    controller.crossing_blocks[1] = 19

# failure test
def test_detect_broken_rail(controller):
    block_id = 20
    controller._expected_occupancy.add(block_id)
    controller._detect_broken_rail(block_id, False)
    failure_key = f"broken_rail_{block_id}"
    assert failure_key in controller.failures

def test_detect_power_failure(controller):
    block_id = 15
    controller._detect_power_failure(block_id, "signal", SignalState.GREEN)
    verification_key = f"signal_{block_id}"
    assert verification_key in controller._pending_verifications

def test_detect_track_circuit_failure(controller):
    block_id = 25
    controller._known_occupancy[block_id] = True
    controller._commanded_speed_mps[block_id] = 0
    controller._commanded_auth_m[block_id] = 0
    controller._occupancy_changes[block_id] = controller.time - timedelta(seconds=3)
    controller._detect_track_circuit_failure(block_id)

def test_failure_record_creation(controller):
    failure = FailureRecord(
        failure_type="broken_rail",
        block_id=10,
        timestamp=datetime.now(),
        details="Test failure"
    )
    assert failure.failure_type == "broken_rail"
    assert failure.block_id == 10
    assert not failure.resolved

def test_get_failure_report(controller):
    report = controller.get_failure_report()
    assert "active_failures" in report
    assert "failure_history" in report
    assert "pending_verifications" in report
    assert "total_failures" in report

def test_resolve_failure(controller):
    controller.set_maintenance_mode(True)
    block_id = 20
    controller._expected_occupancy.add(block_id)
    controller._detect_broken_rail(block_id, False)
    failure_key = f"broken_rail_{block_id}"
    controller.resolve_failure(failure_key)
    assert failure_key not in controller.failures

def test_clear_all_failures_requires_maintenance(controller):
    controller.set_maintenance_mode(False)
    with pytest.raises(PermissionError):
        controller.clear_all_failures()

def test_clear_all_failures(controller):
    controller.set_maintenance_mode(True)
    controller.failures["test"] = FailureRecord(
        failure_type="test",
        block_id=1,
        timestamp=datetime.now(),
        details="Test"
    )
    controller.clear_all_failures()
    assert len(controller.failures) == 0

# live link test
def test_start_live_link(controller):
    controller.start_live_link(poll_interval=0.1)
    assert controller._live_thread_running
    controller.stop_live_link()

def test_stop_live_link(controller):
    controller.start_live_link(poll_interval=0.1)
    controller.stop_live_link()
    assert not controller._live_thread_running

def test_live_link_already_running(controller, caplog):
    controller.start_live_link(poll_interval=0.1)
    with caplog.at_level(logging.WARNING):
        controller.start_live_link(poll_interval=0.1)
    assert "already running" in caplog.text.lower()
    controller.stop_live_link()

def test_poll_track_model(controller, mock_track_model):
    mock_track_model.segments[10].occupied = True
    controller._poll_track_model()
    assert controller._known_occupancy.get(10) == True

# command verification
def test_command_verification_creation(controller):
    verification = CommandVerification(
        block_id=10,
        command_type="signal",
        expected_value=SignalState.GREEN,
        timestamp=datetime.now()
    )
    assert verification.block_id == 10
    assert not verification.verified

def test_verify_commands_timeout(controller):
    controller.time = datetime.now()
    verification = CommandVerification(
        block_id=10,
        command_type="signal",
        expected_value=SignalState.GREEN,
        timestamp=controller.time - timedelta(seconds=10)
    )
    controller._pending_verifications["signal_10"] = verification
    controller._verify_commands()

# adjacency
def test_get_adjacent_blocks(controller):
    block_id = 10
    adjacent = controller._get_adjacent_blocks(block_id)
    assert 9 in adjacent
    assert 11 in adjacent

def test_get_adjacent_blocks_boundary(controller):
    block_id = 1
    adjacent = controller._get_adjacent_blocks(block_id)
    assert 1 not in adjacent
    assert 2 in adjacent

def test_get_next_blocks(controller):
    block_id = 10
    next_blocks = controller._get_next_blocks(block_id)
    assert len(next_blocks) > 0

def test_get_next_blocks_with_switch(controller):
    controller.switch_map[10] = (11, 12)
    next_blocks = controller._get_next_blocks(10)
    assert 11 in next_blocks or 12 in next_blocks

# line block map
def test_line_block_ids_green_line(controller):
    block_ids = controller._line_block_ids()
    assert 1 in block_ids
    assert 62 in block_ids
    assert 122 in block_ids
    assert 150 in block_ids

def test_line_block_ids_red_line(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Red Line")
    block_ids = controller._line_block_ids()
    assert len(block_ids) <= 76

def test_line_block_ids_blue_line(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Blue Line")
    block_ids = controller._line_block_ids()
    assert len(block_ids) <= 15

# dataclass
def test_track_model_message():
    msg = TrackModelMessage(
        block_id=10,
        attribute="occupancy",
        value=True
    )
    assert msg.block_id == 10
    assert msg.attribute == "occupancy"
    assert msg.value

def test_wayside_status_update():
    status = WaysideStatusUpdate(
        block_id=10,
        occupied=True,
        signal_state=SignalState.GREEN,
        switch_position=1,
        crossing_status=True
    )
    assert status.block_id == 10
    assert status.occupied == True
    assert status.signal_state == SignalState.GREEN
    assert status.switch_position == 1
    assert status.crossing_status == True

def test_failure_record():
    failure = FailureRecord(
        failure_type="broken_rail",
        block_id=20,
        timestamp=datetime.now(),
        details="Test failure details"
    )
    assert failure.failure_type == "broken_rail"
    assert failure.block_id == 20
    assert not failure.resolved

def test_command_verification():
    verification = CommandVerification(
        block_id=15,
        command_type="signal",
        expected_value=SignalState.GREEN,
        timestamp=datetime.now()
    )
    assert verification.block_id == 15
    assert verification.command_type == "signal"
    assert not verification.verified

# exceptions
def test_safety_exception():
    with pytest.raises(SafetyException):
        raise SafetyException("Test safety violation")

def test_switch_safety_prevents_collision(controller, mock_track_model):
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    controller.switch_map[5] = (5, 6, 7)
    mock_track_model.segments[6].occupied = True
    with pytest.raises(SafetyException):
        controller.safe_set_switch(5, 1)

def test_crossing_safety_prevents_accident(controller, mock_track_model):
    controller.set_maintenance_mode(True)
    controller.crossings[1] = True
    controller.crossing_blocks[1] = 19
    mock_track_model.segments[19].occupied = True
    with pytest.raises(SafetyException):
        controller.safe_set_crossing(1, False)

# infrastructure
def test_initialize_infrastructure(controller):
    controller.switch_map = {1: (2, 3), 5: (6, 7)}
    controller._initialize_infrastructure()
    assert controller.switches[1] == 0
    assert controller.switches[5] == 0

def test_crossing_blocks_green_line(controller):
    assert 1 in controller.crossing_blocks
    assert controller.crossing_blocks[1] == 19

def test_crossing_blocks_red_line(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Red Line")
    assert 1 in controller.crossing_blocks
    assert 2 in controller.crossing_blocks
    assert controller.crossing_blocks[1] == 11
    assert controller.crossing_blocks[2] == 47

# switch signals
def test_switch_signals_storage(controller):
    controller._switch_signals[(5, 0)] = SignalState.GREEN
    controller._switch_signals[(5, 1)] = SignalState.YELLOW
    controller._switch_signals[(5, 2)] = SignalState.RED
    assert controller._switch_signals[(5, 0)] == SignalState.GREEN
    assert controller._switch_signals[(5, 1)] == SignalState.YELLOW
    assert controller._switch_signals[(5, 2)] == SignalState.RED

def test_switch_with_signals(controller):
    controller.switches[5] = 0
    controller.set_signal(5, SignalState.GREEN, signal_side=0)
    controller.set_signal(5, SignalState.RED, signal_side=2)
    assert controller._switch_signals.get((5, 0)) == SignalState.GREEN
    assert controller._switch_signals.get((5, 2)) == SignalState.RED

# occupancy more
def test_occupancy_change_timestamp(controller):
    block_id = 30
    controller._update_occupancy_from_model(block_id, True)
    assert block_id in controller._occupancy_changes

def test_previous_occupancy_tracking(controller):
    block_id = 30
    controller._update_occupancy_from_model(block_id, True)
    assert controller._previous_occupancy.get(block_id) == True

def test_check_occupancy_consistency(controller):
    block_id = 30
    controller._check_occupancy_consistency(block_id, True)

def test_occupancy_consistency_with_adjacent(controller):
    block_id = 30
    controller._occupancy_changes[29] = controller.time - timedelta(seconds=5)
    controller._check_occupancy_consistency(block_id, True)

# handle failure
def test_handle_broken_rail(controller, mock_track_model):
    block_id = 25
    controller._handle_broken_rail(block_id)
    assert any(block_id == call[0] for call in mock_track_model.signal_calls)

def test_handle_power_failure(controller):
    block_id = 30
    controller._handle_power_failure(block_id, "signal")

def test_handle_track_circuit_failure(controller):
    block_id = 35
    controller._handle_track_circuit_failure(block_id)

def test_check_train_movement(controller):
    block_id = 40
    controller._occupancy_changes[block_id] = controller.time - timedelta(seconds=3)
    controller._known_occupancy[block_id] = False
    result = controller._check_train_movement(block_id)
    assert result == True

def test_check_train_movement_no_recent_change(controller):
    block_id = 40
    controller._occupancy_changes[block_id] = controller.time - timedelta(seconds=10)
    result = controller._check_train_movement(block_id)
    assert result == False

# retry
def test_command_retry_count_increment(controller):
    verification_key = "signal_10"
    controller._command_retry_count[verification_key] = 0
    controller._detect_power_failure(10, "signal", SignalState.GREEN)
    assert controller._command_retry_count[verification_key] >= 1

def test_command_retry_triggers_failure(controller):
    verification_key = "signal_15"
    controller._command_retry_count[verification_key] = 3
    controller._detect_power_failure(15, "signal", SignalState.GREEN)
    failure_key = f"power_failure_signal_15"
    assert failure_key in controller.failures

#sync
def test_sync_after_plc_upload(controller, mock_track_model):
    block_id = 20
    mock_track_model.segments[block_id].signal_state = SignalState.GREEN
    controller._sync_after_plc_upload()
    assert controller._known_signal.get(block_id) == SignalState.GREEN

def test_initial_sync_with_segments(mock_track_model):
    mock_track_model.segments[10].occupied = True
    mock_track_model.segments[10].signal_state = SignalState.YELLOW
    controller = TrackControllerBackend(mock_track_model, "Green Line")
    assert controller._known_occupancy.get(10) == True
    assert controller._known_signal.get(10) == SignalState.YELLOW

# edge cases
def test_empty_switch_map(controller):
    controller.switch_map = {}
    controller._initialize_infrastructure()
    assert len(controller.switches) == 0

def test_empty_crossing_blocks(mock_track_model):
    controller = TrackControllerBackend(mock_track_model, "Blue Line")
    assert len(controller.crossing_blocks) == 0

def test_block_without_segment(controller):
    result = controller.blocks
    assert 999 not in result

def test_signal_state_na_handling(controller):
    blocks = controller.blocks
    for block_data in blocks.values():
        signal = block_data.get("signal")
        if signal == "N/A":
            assert signal == "N/A"

def test_commanded_values_na_handling(controller):
    block_id = 50
    blocks = controller.blocks
    if block_id not in controller._commanded_speed_mps:
        assert blocks[block_id]["commanded_speed"] == "N/A"

# polling and update
def test_poll_updates_switch_signals(controller, mock_track_model):
    mock_track_model.segments[5].previous_signal_state = SignalState.GREEN
    controller.switches[5] = 0
    controller._poll_track_model()

def test_poll_updates_gate_status(controller, mock_track_model):
    controller.crossing_blocks[1] = 19
    mock_track_model.segments[19].gate_status = True
    controller._poll_track_model()
    assert controller.crossings[1] == True

def test_poll_handles_missing_segment(controller):
    controller._poll_track_model()

def test_poll_handles_exceptions(controller, mock_track_model):
    mock_track_model.segments[10] = None
    controller._poll_track_model()

# different lines
def test_multiple_controllers_different_lines(mock_track_model):
    green = TrackControllerBackend(mock_track_model, "Green Line")
    red = TrackControllerBackend(mock_track_model, "Red Line")
    assert green.line_name == "Green Line"
    assert red.line_name == "Red Line"

def test_controllers_independent_state(mock_track_model):
    controller1 = TrackControllerBackend(mock_track_model, "Green Line")
    controller2 = TrackControllerBackend(mock_track_model, "Green Line")
    controller1.set_maintenance_mode(True)
    assert controller2.maintenance_mode == False

# complex test
def test_train_journey_scenario(controller):
    controller._update_occupancy_from_model(10, True)
    assert controller._known_occupancy[10] == True
    controller._update_occupancy_from_model(10, False)
    controller._update_occupancy_from_model(11, True)
    assert controller._known_occupancy[10] == False
    assert controller._known_occupancy[11] == True

def test_switch_divergence_scenario(controller):
    controller.set_maintenance_mode(True)
    controller.switches[5] = 0
    controller.switch_map[5] = (6, 7)
    controller.safe_set_switch(5, 0)
    controller._update_occupancy_from_model(4, True)
    controller._update_occupancy_from_model(4, False)
    controller._update_occupancy_from_model(6, True)

def test_crossing_activation_scenario(controller):
    controller.crossing_blocks[1] = 19
    controller._update_occupancy_from_model(18, True)
    controller._update_occupancy_from_model(19, True)
    assert controller.crossings[1] == True
    controller._update_occupancy_from_model(19, False)
    controller._update_occupancy_from_model(20, True)

def test_emergency_stop_scenario(controller):
    blocks = [10, 11, 12, 13, 14]
    for block in blocks:
        controller.set_commanded_speed(block, 0)
        controller.set_commanded_authority(block, 0)
    for block in blocks:
        assert controller._commanded_speed_mps[block] == 0
        assert controller._commanded_auth_m[block] == 0

# stress test
def test_many_occupancy_updates(controller):
    for i in range(1, 51):
        controller._update_occupancy_from_model(i, True)
    for i in range(1, 51):
        assert controller._known_occupancy[i] == True

def test_many_signal_changes(controller):
    signals = [SignalState.RED, SignalState.YELLOW, SignalState.GREEN]
    for i in range(1, 31):
        for sig in signals:
            controller.set_signal(i, sig)

def test_many_listeners(controller):
    callbacks = [Mock() for _ in range(50)]
    for cb in callbacks:
        controller.add_listener(cb)
    controller._notify_listeners()
    for cb in callbacks:
        cb.assert_called()

# failure history 
def test_failure_history_append(controller):
    initial_count = len(controller.failure_history)
    controller._expected_occupancy.add(25)
    controller._detect_broken_rail(25, False)
    assert len(controller.failure_history) > initial_count

def test_failure_history_limit(controller):
    for i in range(20):
        failure = FailureRecord(
            failure_type="test",
            block_id=i,
            timestamp=controller.time,
            details=f"Test {i}"
        )
        controller.failure_history.append(failure)
    report = controller.get_failure_report()
    assert len(report["failure_history"]) == 10

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
