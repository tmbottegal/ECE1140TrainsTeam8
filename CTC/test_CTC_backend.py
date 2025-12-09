import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from CTC.CTC_backend import TrackState, ScheduleManager, BLOCK_LEN_M, LINE_SPEED_LIMIT_MPS
from trackModel.track_model_backend import TrackSwitch, Station


@pytest.fixture
def ctc():
    """Create a TrackState object with a real TrackNetwork loaded."""
    return TrackState(line_name="Green Line")

# --------------------------------------------------------
# Test: compute_suggestions
# --------------------------------------------------------

def test_compute_suggestions_valid(ctc):
    speed, auth = ctc.compute_suggestions(1, 4)
    assert speed > 0
    assert auth > 0

def test_compute_suggestions_same_block(ctc):
    speed, auth = ctc.compute_suggestions(5, 5)
    assert speed == LINE_SPEED_LIMIT_MPS
    assert auth == 0

def test_compute_suggestions_invalid_block(ctc):
    speed, auth = ctc.compute_suggestions(999, 1)
    assert speed == LINE_SPEED_LIMIT_MPS
    assert auth == 50.0

# --------------------------------------------------------
# Test: find_path
# --------------------------------------------------------

def test_find_path_valid(ctc):
    path = ctc.find_path(1, 7)
    assert isinstance(path, list)
    assert len(path) > 1

def test_find_path_same_block(ctc):
    path = ctc.find_path(3, 3)
    assert path == [3]

def test_find_path_invalid(ctc):
    path = ctc.find_path(999, 1)
    assert path == []

def test_find_path_substitutes_yard_zero(ctc):
    # 0 should map to block 63
    path = ctc.find_path(0, 63)
    assert path == [63]

# --------------------------------------------------------
# Test: compute_travel_time
# --------------------------------------------------------

def test_compute_travel_time_positive(ctc):
    t = ctc.compute_travel_time(1, 4)
    assert t > 0

def test_compute_travel_time_same_block(ctc):
    t = ctc.compute_travel_time(5, 5)
    assert t == 0  # dwell at station or minimal travel

# --------------------------------------------------------
# Test: schedule manual dispatch storage
# --------------------------------------------------------

def test_schedule_manual_dispatch(ctc):
    ctc.schedule_manual_dispatch("T100", 1, 4, 200, 20.0, 150.0)
    assert len(ctc._pending_dispatches) == 1
    entry = ctc._pending_dispatches[0]
    assert entry["train_id"] == "T100"
    assert entry["start_block"] == 1
    assert entry["dest_block"] == 4

# --------------------------------------------------------
# Test: dispatch_train
# --------------------------------------------------------

def test_dispatch_train_creates_train(ctc):
    ctc.dispatch_train("T1", 1, 4, 20.0, 100.0)
    trains = ctc.track_model.trains
    assert "T1" in trains

def test_dispatch_train_sets_destination(ctc):
    ctc.dispatch_train("T1", 1, 4, 20.0, 100.0)
    assert ctc._train_destinations["T1"] == 4

# --------------------------------------------------------
# Test: maintenance controls
# --------------------------------------------------------

def test_close_block_updates_ui_mirror(ctc):
    ctc.set_block_closed(3, True)
    blk = next(b for b in ctc.get_blocks() if b.block_id == 3)
    assert blk.status == "closed"

def test_open_block_updates_ui_mirror(ctc):
    ctc.set_block_closed(3, False)
    blk = next(b for b in ctc.get_blocks() if b.block_id == 3)
    assert blk.status == "unoccupied"

# --------------------------------------------------------
# Test: station_to_block
# --------------------------------------------------------

def test_station_to_block_yard(ctc):
    assert ctc.station_to_block("Yard") == 63

def test_station_to_block_typo(ctc):
    assert ctc.station_to_block("mtlebonon") == ctc.station_to_block("Mt. Lebonon")

def test_suggestions_sent_to_correct_controller(ctc, mocker):
    # Mock both SW and HW controllers
    sw_mock = mocker.patch.object(ctc.track_controller, "receive_ctc_suggestion")
    hw_mock = mocker.patch.object(ctc.track_controller_hw, "receive_ctc_suggestion")

    # Dispatch in SW territory
    ctc.dispatch_train("T_SW", 5, 10, 20.0, 100.0)
    sw_mock.assert_called()
    hw_mock.assert_not_called()

    # Reset mocks
    sw_mock.reset_mock()
    hw_mock.reset_mock()

    # Dispatch in HW territory
    ctc.dispatch_train("T_HW", 70, 80, 20.0, 100.0)
    hw_mock.assert_called()
    sw_mock.assert_not_called()

def test_compute_travel_time_same_block_station(ctc):
    # Find a real station block (example: Mt. Lebanon on Block 77 depending on CSV)
    station_block = ctc.station_to_block("Dormont")  # or any known station
    
    t = ctc.compute_travel_time(station_block, station_block)
    assert t == 30  # stations add 30s dwell time

def test_block_closure_forces_zero_suggestion(ctc, mocker):
    # Mock TC receivers
    sw_mock = mocker.patch.object(ctc.track_controller, "receive_ctc_suggestion")

    # Dispatch a train in SW territory
    ctc.dispatch_train("T1", 5, 10, 20.0, 100.0)

    # Close the next block
    ctc.set_block_closed(6, True)

    # Run one tick to trigger logic
    ctc.tick_all_modules()

    # CTC should have sent zero speed and zero authority
    sw_mock.assert_any_call(5, 0.0, 0.0)

def test_maintenance_switch_change_updates_ctc(ctc):
    # Change switch in CTC backend
    ctc.update_switch_position("Green Line", 12, "Diverge")

    # Verify CTC UI mirror updated
    blk = next(b for b in ctc.get_blocks() if b.block_id == 12)
    assert blk.switch == "Diverge"

def test_maintenance_switch_change_updates_tc(ctc, mocker):
    # The CTC is already connected to the SW controller in your TrackState()
    sw = ctc.track_controller

    # Enable maintenance mode so switching is allowed
    sw.set_maintenance_mode(True)

    # Patch the correct CTC callback
    ctc_mock = mocker.patch.object(
        ctc, 
        "receive_wayside_status",
        return_value=None
    )

    # Simulate changing switch 12 to Alternate
    # (use a real switch ID from your switch_map if needed)
    sw.switch_map[12] = (11, 12, 13)   # Ensure it's recognized as a switch
    sw.switches[12] = 0               # initial state
    sw.safe_set_switch(12, "Alternate")

    # Assert CTC was notified
    ctc_mock.assert_called()
    
    # Extract the most recent call
    args, kwargs = ctc_mock.call_args
    line_name, updates = args[0], args[1]

    # Find the update for block 12
    sw_update = next((u for u in updates if u.block_id == 12), None)
    
    assert sw_update is not None
    assert sw_update.switch_position == 1  # Alternate = 1


def test_receive_wayside_occupancy(ctc):
    class FakeUpdate:
        def __init__(self):
            self.block_id = 5
            self.occupied = True
            self.signal_state = "GREEN"
            self.switch_position = None
            self.crossing_status = None

    ctc.receive_wayside_status("Green Line", [FakeUpdate()], source="SW")

    blk = next(b for b in ctc.get_blocks() if b.block_id == 5)
    assert blk.status == "occupied"

def test_continuous_suggestion_forwarding(ctc, mocker):
    sw_mock = mocker.patch.object(ctc.track_controller, "receive_ctc_suggestion")

    ctc.dispatch_train("T1", 1, 4, 20.0, 100.0)
    ctc.tick_all_modules()

    sw_mock.assert_called()

def test_mode_toggle_changes_state(ctc):
    # CTC starts in MANUAL mode (actual default)
    assert ctc.mode == "manual"

    # Switch to auto
    ctc.set_mode("auto")
    assert ctc.mode == "auto"

    # Switch back to manual
    ctc.set_mode("manual")
    assert ctc.mode == "manual"



def test_receive_multiple_occupancy_updates(ctc):
    class Update:
        def __init__(self, b, occ):
            self.block_id = b
            self.occupied = occ
            self.signal_state = "GREEN"
            self.switch_position = None
            self.crossing_status = None

    updates = [Update(5, True), Update(6, True), Update(7, False)]

    ctc.receive_wayside_status("Green Line", updates, source="SW")

    blk5 = next(b for b in ctc.get_blocks() if b.block_id == 5)
    blk6 = next(b for b in ctc.get_blocks() if b.block_id == 6)
    blk7 = next(b for b in ctc.get_blocks() if b.block_id == 7)

    assert blk5.status == "occupied"
    assert blk6.status == "occupied"
    assert blk7.status == "unoccupied"

