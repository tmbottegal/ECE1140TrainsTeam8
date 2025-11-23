from __future__ import annotations
import sys, os, logging, pytest
from datetime import datetime
from unittest.mock import Mock

_pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _pkg_root not in sys.path:
    sys.path.append(_pkg_root)

from universal.universal import SignalState, TrainCommand, ConversionFunctions
from track_controller_backend import TrackControllerBackend, SafetyException, TrackModelMessage

class MockTrackNetwork:
    def __init__(self):
        self.segments = {}
        self.broadcast_calls = []
        self.signal_calls = []
        self.switch_calls = []
        self.gate_calls = []
        
    def broadcast_train_command(self, block_id: int, speed: int, authority: int):
        self.broadcast_calls.append((block_id, speed, authority))
        
    def set_signal_state(self, block_id: int, state: SignalState):
        self.signal_calls.append((block_id, state))
        
    def set_switch_position(self, switch_id: int, position: int):
        self.switch_calls.append((switch_id, position))
        
    def set_gate_status(self, block_id: int, status: bool):
        self.gate_calls.append((block_id, status))
        
    def get_wayside_status(self):
        return {"segments": {}}

class MockSegment:
    def __init__(self, block_id: int):
        self.block_id = block_id
        self.occupied = False
        self.signal_state = SignalState.RED
        self.current_position = 0
        self.gate_status = False
        self.active_command = None
        
    def set_occupancy(self, status: bool):
        self.occupied = status


@pytest.fixture
def mock_track_model():
    track = MockTrackNetwork()
    for i in range(1, 151):
        track.segments[i] = MockSegment(i)
    return track


@pytest.fixture
def controller(mock_track_model):
    return TrackControllerBackend(mock_track_model, "Green Line")

#ctc test
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

#commanded test
def test_set_commanded_speed(controller, mock_track_model):
    block_id = 10
    speed_mps = 15
    controller.set_commanded_speed(block_id, speed_mps)
    assert controller._commanded_speed_mps[block_id] == speed_mps
    assert controller._known_commanded_speed[block_id] == speed_mps
    assert (block_id, speed_mps, 0) in mock_track_model.broadcast_calls
    
def test_set_commanded_authority(controller, mock_track_model):
    block_id = 10
    authority_m = 200
    controller.set_commanded_authority(block_id, authority_m)
    assert controller._commanded_auth_m[block_id] == authority_m
    assert controller._known_commanded_auth[block_id] == authority_m
    assert (block_id, 0, authority_m) in mock_track_model.broadcast_calls
    
def test_commanded_speed_invalid_block(controller, caplog):
    invalid_block = 999
    with caplog.at_level(logging.WARNING):
        controller.set_commanded_speed(invalid_block, 20)
    assert invalid_block not in controller._commanded_speed_mps
    assert "not in" in caplog.text.lower()

#signal test
def test_set_signal_with_enum(controller, mock_track_model):
    block_id = 15
    controller.set_signal(block_id, SignalState.GREEN)
    assert controller._known_signal[block_id] == SignalState.GREEN
    assert (block_id, SignalState.GREEN) in mock_track_model.signal_calls
    
def test_set_signal_with_string(controller, mock_track_model):
    block_id = 15
    controller.set_signal(block_id, "YELLOW")
    assert controller._known_signal[block_id] == SignalState.YELLOW
    
def test_set_signal_invalid_color(controller):
    block_id = 15
    with pytest.raises(ValueError, match="Invalid signal color"):
        controller.set_signal(block_id, "PURPLE")

#switch test
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

#crossing gate test
def test_safe_set_crossing_maintenance_mode(controller):
    controller.set_maintenance_mode(True)
    controller.crossings[1] = False
    controller.crossing_blocks[1] = 10
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
    controller.crossing_blocks[1] = 10
    mock_track_model.segments[10].occupied = True
    with pytest.raises(SafetyException, match="occupied"):
        controller.safe_set_crossing(1, False)
        
def test_crossing_string_conversion(controller):
    controller.set_maintenance_mode(True)
    controller.crossings[1] = False
    controller.crossing_blocks[1] = 10
    controller.safe_set_crossing(1, "Active")
    assert controller.crossings[1] == True
    controller.safe_set_crossing(1, "Inactive")
    assert controller.crossings[1] == False

#occupancy test
def test_set_block_occupancy(controller, mock_track_model):
    block_id = 20
    controller.set_block_occupancy(block_id, True)
    assert controller._known_occupancy[block_id] == True
    assert mock_track_model.segments[block_id].occupied == True
    
def test_occupancy_clears_authority(controller):
    block_id = 20
    controller._commanded_auth_m[block_id] = 100
    controller._update_occupancy_from_model(block_id, True)
    assert controller._commanded_auth_m[block_id] == 0
    
def test_occupancy_cleared_restores_authority(controller):
    block_id = 20
    controller._suggested_auth_m[block_id] = 150
    controller._update_occupancy_from_model(block_id, False)
    assert controller._commanded_auth_m[block_id] == 150

# plc file test
def test_plc_upload_requires_maintenance_mode(controller, tmp_path):
    controller.set_maintenance_mode(False)
    plc_file = tmp_path / "test.txt"
    plc_file.write_text("SIGNAL 1 GREEN")
    with pytest.raises(PermissionError, match="maintenance mode"):
        controller.upload_plc(str(plc_file))
        
def test_plc_text_file_signal(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.txt"
    plc_file.write_text("SIGNAL 10 GREEN\nSIGNAL 11 YELLOW")
    controller.upload_plc(str(plc_file))
    assert controller._known_signal[10] == SignalState.GREEN
    assert controller._known_signal[11] == SignalState.YELLOW
    
def test_plc_text_file_speed_conversion(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.txt"
    plc_file.write_text("CMD_SPEED 10 40")
    controller.upload_plc(str(plc_file))
    assert controller._commanded_speed_mps[10] == pytest.approx(17, abs=2)
    
def test_plc_text_file_authority_conversion(controller, tmp_path):
    controller.set_maintenance_mode(True)
    plc_file = tmp_path / "test.txt"
    plc_file.write_text("CMD_AUTH 10 100")
    controller.upload_plc(str(plc_file))
    assert controller._commanded_auth_m[10] == pytest.approx(91, abs=2)

#receive stuff track model test
def test_receive_occupancy_update(controller):
    block_id = 25
    controller.receive_model_update(block_id, "occupancy", True)
    assert len(controller.incoming_messages) == 0
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

#state reporting test
def test_report_state_structure(controller):
    state = controller.report_state()
    assert "line" in state
    assert "maintenance_mode" in state
    assert "blocks" in state
    assert "switches" in state
    assert "crossing" in state
    
def test_blocks_property_conversions(controller):
    block_id = 30
    controller._suggested_speed_mps[block_id] = 20.0
    controller._suggested_auth_m[block_id] = 100.0
    blocks = controller.blocks
    assert blocks[block_id]["suggested_speed"] > 0
    assert blocks[block_id]["suggested_auth"] > 0

#listener test
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

#time test 
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

# maintenance mode test yippee
def test_enable_maintenance_mode(controller):
    controller.set_maintenance_mode(True)
    assert controller.maintenance_mode == True
    
def test_disable_maintenance_mode(controller):
    controller.set_maintenance_mode(True)
    controller.set_maintenance_mode(False)
    assert controller.maintenance_mode == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])