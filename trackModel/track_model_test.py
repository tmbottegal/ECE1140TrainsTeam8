"""
Track Model Testing
"""
import pytest
import sys
sys.path.append('../')

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
    # create new track segment with arbitrary input values
    segment = TrackSegment(
        block_id=1,
        length=100.0,
        grade=2.5,
        speed_limit=30,
        underground=False
    )
    # check values and match
    assert segment.block_id == 1
    assert segment.length == 100.0
    assert segment.grade == 2.5
    assert segment.speed_limit == 30
    assert not segment.underground
    assert not segment.occupied
    assert segment.signal_state == SignalState.RED
    assert segment.failures == set()

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
    segment.set_beacon_data("Bababooey")
    assert segment.beacon_data == "Bababooey"

def test_set_track_failure() -> None:
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

def test_clear_track_failure() -> None:
    segment = TrackSegment(1, 100, 30, 2.5, False)
    segment.set_track_failure(TrackFailureType.BROKEN_RAIL)
    assert segment.failures == {TrackFailureType.BROKEN_RAIL}
    segment.clear_track_failure(TrackFailureType.BROKEN_RAIL)
    assert segment.failures == set()
    segment.clear_track_failure(TrackFailureType.BROKEN_RAIL)
    assert segment.failures == set()

def test_report_track_failure() -> None:
    # TODO: Implement
    pass

"""
Switch Individual Testing
"""

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

def test_set_gate_status() -> None:
    crossing = LevelCrossing(1, 200, 20, 2.5, False)
    assert crossing.gate_status == False
    crossing.set_gate_status(True)
    assert crossing.gate_status == True

def test_automatic_gate_status() -> None:
    crossing = LevelCrossing(1, 200, 20, 2.5, False)
    assert crossing.gate_status == False
    crossing.set_occupancy(True)
    assert crossing.gate_status == True
    crossing.set_occupancy(False)
    assert crossing.gate_status == False
"""
Station Individual Testing
"""
def test_station_construction() -> None:
    station = Station(2, 300, 69, 0, "balls", StationSide.BOTH)
    assert station.block_id == 2
    assert station.length == 300
    assert station.speed_limit == 69
    assert station.grade == 0
    assert station.station_name == "balls"
    assert station.station_side == StationSide.BOTH
    assert station.passengers_waiting == 0
    assert station.passengers_boarded_total == 0
    assert station.passengers_exited_total == 0
    assert station.tickets_sold_total == 0

def test_sell_tickets() -> None:
    station = Station(2, 300, 69, 0, "balls", StationSide.BOTH)
    station.sell_tickets(10)
    assert station.passengers_waiting == 10
    assert station.tickets_sold_total == 10
    station.sell_tickets()
    assert station.passengers_waiting > 10
    assert station.tickets_sold_total > 10

def test_passengers_boarding() -> None:
    station = Station(2, 300, 69, 0, "balls", StationSide.BOTH)
    station.sell_tickets(50)
    assert station.passengers_waiting == 50
    assert station.tickets_sold_total == 50
    station.passengers_boarding(1, 40)
    assert station.passengers_waiting == 10
    station.passengers_boarding(1, 5)
    assert station.passengers_waiting < 10

def test_passengers_exiting() -> None:
    station = Station(2, 300, 69, 0, "balls", StationSide.BOTH)
    assert station.passengers_exited_total == 0
    station.passengers_exiting(20)
    assert station.passengers_exited_total == 20
"""
Track Network Testing
"""
if __name__ == "__main__":
    pytest.main([__file__, "-v"])