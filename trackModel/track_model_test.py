"""
Track Model Testing
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from universal.universal import (
    SignalState,
    TrainCommand,
    ConversionFunctions
)

from track_model_backend import (
    TrackNetwork, 
    TrackSegment, 
    TrackSwitch, 
    LevelCrossing,
    Station,
    StationSide,
    TrackFailureType
)
from typing import List, Dict, Optional


"""
Track Segement Individual Testing
"""
def test_segment_construction() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    
    assert segment.block_id == 1
    assert segment.length == 100.0
    assert segment.speed_limit == 30
    assert segment.grade == 2.5
    assert not segment.underground
    assert not segment.occupied
    assert segment.signal_state == SignalState.RED
    assert segment.failures == set()
    assert segment.next_segment is None
    assert segment.previous_segment is None

def test_set_occupancy() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    assert segment.occupied == False
    
    segment.set_occupancy(True)
    assert segment.occupied == True

def test_set_signal_state() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    assert segment.signal_state == SignalState.RED
    
    segment.set_signal_state(SignalState.YELLOW)
    assert segment.signal_state == SignalState.YELLOW
    
    segment.set_signal_state(SignalState.GREEN)
    assert segment.signal_state == SignalState.GREEN
    
    segment.set_signal_state(SignalState.SUPERGREEN)
    assert segment.signal_state == SignalState.SUPERGREEN

def test_set_beacon_data() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    assert segment.beacon_data == ""
    
    segment.set_beacon_data("test")
    assert segment.beacon_data == "test"

def test_segment_set_track_failure() -> None:
    segment = TrackSegment(1, 199, 30, 2.5, False)
    assert segment.failures == set()
    
    segment.set_track_failure(TrackFailureType.BROKEN_RAIL)
    
    assert segment.failures == {TrackFailureType.BROKEN_RAIL}
    segment.set_track_failure(TrackFailureType.BROKEN_RAIL)
    
    assert segment.failures == {TrackFailureType.BROKEN_RAIL}
    segment.set_track_failure(TrackFailureType.POWER_FAILURE)
    
    assert segment.failures == {TrackFailureType.BROKEN_RAIL, TrackFailureType.POWER_FAILURE}
    
    segment.set_track_failure(TrackFailureType.TRACK_CIRCUIT_FAILURE)
    assert segment.failures == {TrackFailureType.BROKEN_RAIL, TrackFailureType.POWER_FAILURE, TrackFailureType.TRACK_CIRCUIT_FAILURE}

def test_segment_clear_track_failure() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    
    segment.set_track_failure(TrackFailureType.BROKEN_RAIL)
    assert segment.failures == {TrackFailureType.BROKEN_RAIL}
    
    segment.clear_track_failure(TrackFailureType.BROKEN_RAIL)
    assert segment.failures == set()
    
    segment.clear_track_failure(TrackFailureType.BROKEN_RAIL)
    assert segment.failures == set()

def test_close_open() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    assert segment.closed == False
    
    segment.close()
    assert segment.closed == True

    segment.open()
    assert segment.closed == False
"""
Switch Individual Testing
"""

def test_switch_construction() -> None:
    switch = TrackSwitch(1, 150, 25, 1.5, False)
    assert switch.block_id == 1
    assert switch.length == 150.0
    assert switch.grade == 1.5
    assert switch.speed_limit == 25
    assert not switch.underground
    assert not switch.occupied
    assert switch.signal_state == SignalState.RED
    assert switch.failures == set()
    assert switch.current_position == 0
    assert switch.straight_segment is None
    assert switch.diverging_segment is None
    assert switch.next_segment is None
    assert switch.previous_segment is None

def test_set_switch_paths() -> None:
    switch = TrackSwitch(1, 150, 25, 1.5, False)
    straight_segment = TrackSegment(2, 100, 25, 0, False)
    diverging_segment = TrackSegment(3, 100, 25, 0, False)
    
    switch.set_switch_paths(straight_segment, diverging_segment)
    assert switch.straight_segment == straight_segment
    assert switch.diverging_segment == diverging_segment

def test_set_switch_position() -> None:
    switch = TrackSwitch(1, 150, 25, 1.5, False)
    straight_segment = TrackSegment(2, 100, 25, 0, False)
    diverging_segment = TrackSegment(3, 100, 25, 0, False)
    switch.set_switch_paths(straight_segment, diverging_segment)

    assert switch.current_position == 0
    assert switch.next_segment == straight_segment
    assert switch.straight_signal_state == SignalState.GREEN
    assert switch.diverging_signal_state == SignalState.RED
    
    switch.set_switch_position(1)
    assert switch.current_position == 1
    assert switch.next_segment == diverging_segment
    assert switch.straight_signal_state == SignalState.RED
    assert switch.diverging_signal_state == SignalState.GREEN
    
    switch.set_switch_position(0)
    assert switch.current_position == 0
    assert switch.next_segment == straight_segment
    assert switch.straight_signal_state == SignalState.GREEN
    assert switch.diverging_signal_state == SignalState.RED

def test_is_straight() -> None:
    switch = TrackSwitch(1, 150, 25, 1.5, False)
    
    assert switch.is_straight() == True
    
    switch.set_switch_position(1)
    assert switch.is_straight() == False
    
    switch.set_switch_position(0)
    assert switch.is_straight() == True

"""
Level Crossing Individual Testing
"""
def test_level_crossing_construction() -> None:
    crossing = LevelCrossing(1, 200, 20, 2.5, False)
    
    assert crossing.block_id == 1
    assert crossing.length == 200.0
    assert crossing.grade == 2.5
    assert crossing.speed_limit == 20
    assert not crossing.underground
    assert not crossing.occupied
    assert crossing.signal_state == SignalState.RED
    assert crossing.failures == set()
    assert crossing.gate_status == False
    assert crossing.next_segment is None
    assert crossing.previous_segment is None

def test_set_gate_status() -> None:
    crossing = LevelCrossing(1, 200, 20, 2.5, False)
    assert crossing.gate_status == False
    
    crossing.set_gate_status(True)
    assert crossing.gate_status == True

    crossing.set_gate_status(False)
    assert crossing.gate_status == False

"""
Station Individual Testing
"""
def test_station_construction() -> None:
    station = Station(2, 300, 69, 0, "test", StationSide.BOTH)
    
    assert station.block_id == 2
    assert station.length == 300
    assert station.speed_limit == 69
    assert station.grade == 0
    assert station.station_name == "test"
    assert station.station_side == StationSide.BOTH
    assert station.passengers_waiting == 0
    assert station.passengers_boarded_total == 0
    assert station.passengers_exited_total == 0
    assert station.tickets_sold_total == 0
    assert station.next_segment is None
    assert station.previous_segment is None

def test_sell_tickets() -> None:
    station = Station(2, 300, 69, 0, "test", StationSide.BOTH)
    assert station.passengers_waiting == 0
    assert station.tickets_sold_total == 0

    station.sell_tickets(10)
    assert station.passengers_waiting == 10
    assert station.tickets_sold_total == 10
    
    station.sell_tickets()
    assert station.passengers_waiting > 10
    assert station.tickets_sold_total > 10

def test_passengers_boarding_valid() -> None:
    station = Station(2, 300, 69, 0, "test", StationSide.BOTH)
    station.sell_tickets(50)
    assert station.passengers_waiting == 50
    assert station.tickets_sold_total == 50
    
    station.passengers_boarding(1, 40)
    assert station.passengers_waiting == 10
    
    station.passengers_boarding(1, 5)
    assert station.passengers_waiting < 10

def test_passengers_boarding_invalid() -> None:
    station = Station(2, 300, 69, 0, "test", StationSide.BOTH)
    station.sell_tickets(30)
    assert station.passengers_waiting == 30
    assert station.tickets_sold_total == 30
    
    with pytest.raises(ValueError):
        station.passengers_boarding(1, 40)
    assert station.passengers_waiting == 30
    
    with pytest.raises(ValueError):
        station.passengers_boarding(1, -5)
    assert station.passengers_waiting == 30

def test_passengers_exiting() -> None:
    station = Station(2, 300, 69, 0, "test", StationSide.BOTH)
    assert station.passengers_exited_total == 0
    
    station.passengers_exiting(20)
    assert station.passengers_exited_total == 20
"""
Track Network Testing
"""
def test_add_segment_valid() -> None:
    network = TrackNetwork()
    segment = TrackSegment(1, 100, 30, 2.5, False)
    switch = TrackSwitch(2, 150, 25, 1.5, False)
    crossing = LevelCrossing(3, 200, 20, 2.5, False)
    station = Station(4, 300, 69, 0, "test", StationSide.BOTH)
    
    network.add_segment(segment)
    assert network.segments[1] == segment
    assert len(network.segments) == 1

    network.add_segment(switch)
    assert network.segments[2] == switch
    assert len(network.segments) == 2

    network.add_segment(crossing)
    assert network.segments[3] == crossing
    assert len(network.segments) == 3

    network.add_segment(station)
    assert network.segments[4] == station
    assert len(network.segments) == 4

def test_add_segment_invalid() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 2.5, False)
    segment2 = TrackSegment(1, 150, 25, 1.5, False)  # Duplicate block_id

    network.add_segment(segment1)
    assert len(network.segments) == 1

    with pytest.raises(ValueError):
        network.add_segment(segment2)
    assert len(network.segments) == 1

def test_connect_segments_segments_valid_single_straight() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    segment3 = TrackSegment(3, 100, 30, 0, False)
    segment4 = TrackSegment(4, 100, 30, 0, False)
    segment5 = TrackSegment(5, 100, 30, 0, False)

    network.add_segment(segment1)
    network.add_segment(segment2)
    network.add_segment(segment3)
    network.add_segment(segment4)
    network.add_segment(segment5)

    network.connect_segments(1, 2, bidirectional=False)
    assert segment1.next_segment == segment2
    assert segment2.previous_segment is None
    
    network.connect_segments(2, 3, bidirectional=False)
    assert segment2.next_segment == segment3
    assert segment3.previous_segment is None

    network.connect_segments(3, 4, bidirectional=False)
    assert segment3.next_segment == segment4
    assert segment4.previous_segment is None

    network.connect_segments(4, 5, bidirectional=False)
    assert segment4.next_segment == segment5
    assert segment5.previous_segment is None
    assert segment1.previous_segment is None
    assert segment5.next_segment is None

def test_connect_segments_segments_valid_bi_straight() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    segment3 = TrackSegment(3, 100, 30, 0, False)
    segment4 = TrackSegment(4, 100, 30, 0, False)
    segment5 = TrackSegment(5, 100, 30, 0, False)

    network.add_segment(segment1)
    network.add_segment(segment2)
    network.add_segment(segment3)
    network.add_segment(segment4)
    network.add_segment(segment5)
    
    network.connect_segments(1, 2, bidirectional=True)
    assert segment1.next_segment == segment2
    assert segment2.previous_segment == segment1

    network.connect_segments(2, 3, bidirectional=True)
    assert segment2.next_segment == segment3
    assert segment3.previous_segment == segment2

    network.connect_segments(3, 4, bidirectional=True)
    assert segment3.next_segment == segment4
    assert segment4.previous_segment == segment3

    network.connect_segments(4, 5, bidirectional=True)
    assert segment4.next_segment == segment5
    assert segment5.previous_segment == segment4
    assert segment1.previous_segment is None
    assert segment5.next_segment is None

def test_connect_segments_segments_valid_single_loop() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    segment3 = TrackSegment(3, 100, 30, 0, False)
    segment4 = TrackSegment(4, 100, 30, 0, False)
    segment5 = TrackSegment(5, 100, 30, 0, False)

    network.add_segment(segment1)
    network.add_segment(segment2)
    network.add_segment(segment3)
    network.add_segment(segment4)
    network.add_segment(segment5)

    network.connect_segments(1, 2, bidirectional=False)
    assert segment1.next_segment == segment2
    assert segment2.previous_segment is None
    
    network.connect_segments(2, 3, bidirectional=False)
    assert segment2.next_segment == segment3
    assert segment3.previous_segment is None
    
    network.connect_segments(3, 4, bidirectional=False)
    assert segment3.next_segment == segment4
    assert segment4.previous_segment is None
    
    network.connect_segments(4, 5, bidirectional=False)
    assert segment4.next_segment == segment5
    assert segment5.previous_segment is None
    
    network.connect_segments(5, 1, bidirectional=False)
    assert segment5.next_segment == segment1
    assert segment1.previous_segment is None

def test_connect_segments_segments_valid_bi_loop() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    segment3 = TrackSegment(3, 100, 30, 0, False)
    segment4 = TrackSegment(4, 100, 30, 0, False)
    segment5 = TrackSegment(5, 100, 30, 0, False)

    network.add_segment(segment1)
    network.add_segment(segment2)
    network.add_segment(segment3)
    network.add_segment(segment4)
    network.add_segment(segment5)

    network.connect_segments(1, 2, bidirectional=True)
    assert segment1.next_segment == segment2
    assert segment2.previous_segment == segment1

    network.connect_segments(2, 3, bidirectional=True)
    assert segment2.next_segment == segment3
    assert segment3.previous_segment == segment2

    network.connect_segments(3, 4, bidirectional=True)
    assert segment3.next_segment == segment4
    assert segment4.previous_segment == segment3

    network.connect_segments(4, 5, bidirectional=True)
    assert segment4.next_segment == segment5
    assert segment5.previous_segment == segment4

    network.connect_segments(5, 1, bidirectional=True)
    assert segment5.next_segment == segment1
    assert segment1.previous_segment == segment5

def test_connect_segments_switch_valid() -> None:
    network = TrackNetwork()
    switch = TrackSwitch(1, 150, 25, 1.5, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    segment3 = TrackSegment(3, 100, 30, 0, False)

    network.add_segment(switch)
    network.add_segment(segment2)
    network.add_segment(segment3)

    network.connect_segments(1, 2, diverging_seg_block_id=3, bidirectional=False)
    assert switch.next_segment == segment2
    assert switch.straight_segment == segment2
    assert switch.diverging_segment == segment3

    switch.set_switch_position(1)
    assert switch.next_segment == segment3

def test_connect_segments_invalid() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    switch = TrackSwitch(3, 150, 25, 1.5, False)

    network.add_segment(segment1)
    network.add_segment(segment2)
    network.add_segment(switch)

    # Invalid connections (segments do not exist)
    with pytest.raises(ValueError):
        network.connect_segments(1, 99, bidirectional=False)
    with pytest.raises(ValueError):
        network.connect_segments(99, 2, bidirectional=False)
    with pytest.raises(ValueError):
        network.connect_segments(3, 2, diverging_seg_block_id=99, bidirectional=False)

    # Invalid connections (to switch without diverging segment)
    with pytest.raises(ValueError):
        network.connect_segments(3, 2, bidirectional=False)

    # Invalid connections (to non-switch with diverging segment)
    with pytest.raises(ValueError):
        network.connect_segments(1, 2, diverging_seg_block_id=3, bidirectional=False)

def test_load_track_layout_valid() -> None:
    #TODO: Implement function before test
    pass

def test_load_track_layout_invalid() -> None:
    #TODO: Implement function before test
    pass

def test_set_environmental_temperature() -> None:
    network = TrackNetwork()
    network.set_environmental_temperature(25.0)
    assert network.environmental_temperature == 25.0
    
    network.set_environmental_temperature(-10.0)
    assert network.environmental_temperature == -10.0

def test_set_heater_threshold() -> None:
    network = TrackNetwork()
    network.set_heater_threshold(30)
    assert network.heater_threshold == 30
    assert network.heaters_active == True

    network.set_heater_threshold(0)
    assert network.heater_threshold == 0
    assert network.heaters_active == False

def test_get_heater_status() -> None:
    network = TrackNetwork()
    network.heaters_active = False
    assert network.get_heater_status() == False

    network.heaters_active = True
    assert network.get_heater_status() == True

def test_network_set_track_failure_valid() -> None:
    network = TrackNetwork()
    segment = TrackSegment(1, 100, 30, 2.5, False)
    network.add_segment(segment)
    
    assert segment.failures == set()
    
    network.set_track_failure(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL)
    assert segment.failures == {TrackFailureType.BROKEN_RAIL}
    
    network.set_track_failure(block_id=1, failure_type=TrackFailureType.POWER_FAILURE)
    assert segment.failures == {TrackFailureType.BROKEN_RAIL, TrackFailureType.POWER_FAILURE}

def test_network_set_track_failure_invalid() -> None:
    network = TrackNetwork()
    
    with pytest.raises(ValueError):
        network.set_track_failure(block_id=99, failure_type=TrackFailureType.BROKEN_RAIL)

def test_network_clear_track_failure_valid() -> None:
    network = TrackNetwork()
    segment = TrackSegment(1, 100, 30, 2.5, False)
    network.add_segment(segment)
    network.set_track_failure(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL)
    network.set_track_failure(block_id=1, failure_type=TrackFailureType.POWER_FAILURE)
    assert segment.failures == {TrackFailureType.BROKEN_RAIL, TrackFailureType.POWER_FAILURE}

    network.clear_track_failure(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL)
    assert segment.failures == {TrackFailureType.POWER_FAILURE}

    network.clear_track_failure(block_id=1, failure_type=TrackFailureType.POWER_FAILURE)
    assert segment.failures == set()

def test_network_clear_track_failure_invalid() -> None:
    network = TrackNetwork()
    
    with pytest.raises(ValueError):
        network.clear_track_failure(block_id=99, failure_type=TrackFailureType.BROKEN_RAIL)

def test_add_failure_log_entry_valid() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    network.add_segment(segment1)
    network.add_segment(segment2)
    assert len(network.failure_log) == 0

    network.add_failure_log_entry(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL, active=True)
    network.add_failure_log_entry(block_id=2, failure_type=TrackFailureType.POWER_FAILURE, active=True)
    network.add_failure_log_entry(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL, active=False)
    
    log = network.failure_log
    assert len(log) == 3
    assert log[0]["block_id"] == 1
    assert log[0]["failure_type"] == TrackFailureType.BROKEN_RAIL
    assert log[0]["active"] == True

    assert log[1]["block_id"] == 2
    assert log[1]["failure_type"] == TrackFailureType.POWER_FAILURE
    assert log[1]["active"] == True

    assert log[2]["block_id"] == 1
    assert log[2]["failure_type"] == TrackFailureType.BROKEN_RAIL
    assert log[2]["active"] == False

def test_add_failure_log_entry_invalid() -> None:
    network = TrackNetwork()
    with pytest.raises(ValueError):
        network.add_failure_log_entry(block_id=99, failure_type=TrackFailureType.BROKEN_RAIL, active=True)

def test_get_failure_log() -> None:
    network = TrackNetwork()
    assert len(network.get_failure_log()) == 0

    segment1 = TrackSegment(1, 100, 30, 0, False)
    segment2 = TrackSegment(2, 100, 30, 0, False)
    network.add_segment(segment1)
    network.add_segment(segment2)
    network.add_failure_log_entry(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL, active=True)
    network.add_failure_log_entry(block_id=2, failure_type=TrackFailureType.POWER_FAILURE, active=True)
    network.add_failure_log_entry(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL, active=False)
    log = network.get_failure_log()
    assert len(log) == 3

def test_close_open_block_valid() -> None:
    network = TrackNetwork()
    segment = TrackSegment(1, 100, 30, 2.5, False)
    network.add_segment(segment)
    
    assert segment.closed == False
    
    network.close_block(1)
    assert segment.closed == True
    
    network.open_block(1)
    assert segment.closed == False

def test_close_open_block_invalid() -> None:
    network = TrackNetwork()
    
    with pytest.raises(ValueError):
        network.close_block(99)
    
    with pytest.raises(ValueError):
        network.open_block(99)

def test_network_set_signal_state_valid() -> None:
    network = TrackNetwork()
    segment = TrackSegment(1, 100, 30, 2.5, False)
    network.add_segment(segment)
    
    assert segment.signal_state == SignalState.RED
    
    network.set_signal_state(block_id=1, signal_state=SignalState.GREEN)
    assert segment.signal_state == SignalState.GREEN
    
    network.set_signal_state(block_id=1, signal_state=SignalState.YELLOW)
    assert segment.signal_state == SignalState.YELLOW
    
    network.set_signal_state(block_id=1, signal_state=SignalState.SUPERGREEN)
    assert segment.signal_state == SignalState.SUPERGREEN

def test_network_set_signal_state_invalid() -> None:
    network = TrackNetwork()
    
    with pytest.raises(ValueError):
        network.set_signal_state(block_id=99, signal_state=SignalState.GREEN)

def test_get_network_status() -> None:
    network = TrackNetwork()
    segment1 = TrackSegment(1, 100, 30, 2.5, False)
    segment2 = TrackSegment(2, 150, 25, 1.5, False)
    network.add_segment(segment1)
    network.add_segment(segment2)
    network.set_track_failure(block_id=1, failure_type=TrackFailureType.BROKEN_RAIL)
    network.close_block(2)

    status = network.get_network_status()

    assert status["environmental_temperature"] == 20.0
    assert status["heater_threshold"] == 0
    assert status["heaters_active"] == False
    assert len(status["segments"]) == 2
    assert len(status["failure_log"]) == 1
    assert status["segments"][1]["block_id"] == 1
    assert status["segments"][1]["failures"] == [TrackFailureType.BROKEN_RAIL]
    assert status["segments"][2]["block_id"] == 2
    assert status["segments"][2]["closed"] == True
    assert status["failure_log"][0]["block_id"] == 1
    assert status["failure_log"][0]["failure_type"] == TrackFailureType.BROKEN_RAIL
    assert status["failure_log"][0]["active"] == True
    
    
def test_get_segment_status_valid() -> None:
    network = TrackNetwork()
    segment = TrackSegment(1, 100, 30, 2.5, False)
    level_crossing = LevelCrossing(2, 150, 25, 1.5, False)
    station = Station(3, 300, 69, 0, "test", StationSide.BOTH)
    switch = TrackSwitch(4, 200, 20, 2.0, False)


    network.add_segment(segment)
    network.add_segment(level_crossing)
    network.add_segment(station)
    network.add_segment(switch)

    network.connect_segments(1, 2, bidirectional=False)
    network.connect_segments(2, 3, bidirectional=False)
    network.connect_segments(3, 4, bidirectional=False)
    network.connect_segments(4, 1, diverging_seg_block_id=2, bidirectional=False)

    # Properties for regular segment
    status = network.get_segment_status(1)
    assert status["block_id"] == 1
    assert status["length"] == 100.0
    assert status["speed_limit"] == 30
    assert status["grade"] == 2.5
    assert status["underground"] == False
    assert status["occupied"] == False
    assert status["signal_state"] == SignalState.RED
    assert status["failures"] == []
    assert status["closed"] == False
    assert status["next_segment"] == 2
    assert status["previous_segment"] == None

    # Properties for level crossing
    status = network.get_segment_status(2)
    assert status["block_id"] == 2
    assert status["length"] == 150.0
    assert status["speed_limit"] == 25
    assert status["grade"] == 1.5
    assert status["underground"] == False
    assert status["occupied"] == False
    assert status["signal_state"] == SignalState.RED
    assert status["failures"] == []
    assert status["closed"] == False
    assert status["next_segment"] == 3
    assert status["previous_segment"] == None
    assert status["gate_status"] == False

    # Properties for station
    status = network.get_segment_status(3)
    assert status["block_id"] == 3
    assert status["length"] == 300.0
    assert status["speed_limit"] == 69
    assert status["grade"] == 0
    assert status["underground"] == False
    assert status["occupied"] == False
    assert status["signal_state"] == SignalState.RED
    assert status["failures"] == []
    assert status["closed"] == False
    assert status["next_segment"] == 4
    assert status["previous_segment"] == None
    assert status["station_name"] == "test"
    assert status["station_side"] == StationSide.BOTH
    assert status["passengers_waiting"] == 0
    assert status["passengers_boarded_total"] == 0
    assert status["passengers_exited_total"] == 0
    assert status["tickets_sold_total"] == 0

    # Properties for switch
    status = network.get_segment_status(4)
    assert status["block_id"] == 4
    assert status["length"] == 200.0
    assert status["speed_limit"] == 20
    assert status["grade"] == 2.0
    assert status["underground"] == False
    assert status["occupied"] == False
    assert status["signal_state"] == SignalState.RED
    assert status["failures"] == []
    assert status["closed"] == False
    assert status["next_segment"] == 1
    assert status["previous_segment"] == None
    assert status["current_position"] == 0
    assert status["straight_segment"] == 1
    assert status["diverging_segment"] == 2

def test_get_segment_status_invalid() -> None:
    network = TrackNetwork()
    with pytest.raises(ValueError):
        network.get_segment_status(99)

def test_everything_blueline() -> None:
    network = TrackNetwork()
    yard = Station(0, 100, 15, 0, "Yard", StationSide.BOTH)
    a1 = TrackSegment(1, 50, 50, 0, False)
    a2 = TrackSegment(2, 50, 50, 0, False)
    a3 = LevelCrossing(3, 50, 50, 0, False)
    a4 = TrackSegment(4, 50, 50, 0, False)
    a5 = TrackSwitch(5, 50, 50, 0, False)
    a5.set_switch_position(0)
    b6 = TrackSegment(6, 50, 50, 0, False)
    b7 = TrackSegment(7, 50, 50, 0, False)
    b8 = TrackSegment(8, 50, 50, 0, False)
    b9 = TrackSegment(9, 50, 50, 0, False)
    b9.beacon_data = "NextStation: Station B"
    b10 = Station(10, 50, 50, 0, "Station B", StationSide.RIGHT)
    c11 = TrackSegment(11, 50, 50, 0, False)
    c12 = TrackSegment(12, 50, 50, 0, False)
    c13 = TrackSegment(13, 50, 50, 0, False)
    c14 = TrackSegment(14, 50, 50, 0, False)
    c14.beacon_data = "NextStation: Station C"
    c15 = Station(15, 50, 50, 0, "Station C", StationSide.RIGHT)
    
    network.add_segment(yard)
    network.add_segment(a1)
    network.add_segment(a2)
    network.add_segment(a3)
    network.add_segment(a4)
    network.add_segment(a5)
    network.add_segment(b6)
    network.add_segment(b7)
    network.add_segment(b8)
    network.add_segment(b9)
    network.add_segment(b10)
    network.add_segment(c11)
    network.add_segment(c12)
    network.add_segment(c13)
    network.add_segment(c14)
    network.add_segment(c15)

    network.connect_segments(0, 1, bidirectional=True)
    network.connect_segments(1, 2, bidirectional=True)
    network.connect_segments(2, 3, bidirectional=True)
    network.connect_segments(3, 4, bidirectional=True)
    network.connect_segments(4, 5, bidirectional=True)
    network.connect_segments(5, 6, diverging_seg_block_id=11, bidirectional=True)
    network.connect_segments(6, 7, bidirectional=True)
    network.connect_segments(7, 8, bidirectional=True)
    network.connect_segments(8, 9, bidirectional=True)
    network.connect_segments(9, 10, bidirectional=True)
    network.connect_segments(11, 12, bidirectional=True)
    network.connect_segments(12, 13, bidirectional=True)
    network.connect_segments(13, 14, bidirectional=True)
    network.connect_segments(14, 15, bidirectional=True)

    current_segment = yard
    forward_path1 = []

    while current_segment is not None:
        forward_path1.append(current_segment.block_id)
        current_segment = current_segment.get_next_segment()

    assert forward_path1 == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    current_segment = network.segments[forward_path1[-1]]
    backward_path = []

    while current_segment is not None:
        backward_path.append(current_segment.block_id)
        current_segment = current_segment.get_previous_segment()

    assert backward_path == [10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]

    a5.set_switch_position(1)

    current_segment = network.segments[backward_path[-1]]
    forward_path2 = []

    while current_segment is not None:
        forward_path2.append(current_segment.block_id)
        current_segment = current_segment.get_next_segment()

    assert forward_path2 == [0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 15]

def test_network_passengers_boarding_invalid() -> None:
    network = TrackNetwork()
    station = Station(2, 300, 69, 0, "test", StationSide.BOTH)
    network.add_segment(station)

    with pytest.raises(ValueError):
        network.passengers_boarding(2, 5, 10)

    with pytest.raises(ValueError):
        network.passengers_boarding(1, -5, 10)

    #TODO #103 : Add unit tests for new functions in backend

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
