"""
Track Model Sandbox
"""
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
    TrackFailureType,
    Train
)
from typing import List, Dict, Optional

if __name__ == "__main__":
    network = TrackNetwork()
    network.load_track_layout("trackModel/blue_line.csv")
    train = Train(1)
    network.set_signal_state(3, SignalState.GREEN)
    network.set_signal_state(2, SignalState.GREEN)
    network.set_signal_state(1, SignalState.GREEN)
    network.add_train(train)
    network.connect_train(1, 2, 0)
    print(f"Current Segment: {train.current_segment.block_id}, Position in Segment: {train.segment_displacement}")
    train.move(60)
    print(f"Current Segment: {train.current_segment.block_id}, Position in Segment: {train.segment_displacement}")
    train.move(-40)
    print(f"Current Segment: {train.current_segment.block_id}, Position in Segment: {train.segment_displacement}")
    train.move(-40)
    print(f"Current Segment: {train.current_segment.block_id}, Position in Segment: {train.segment_displacement}")
    train.move(-300)
    print(f"Current Segment: {train.current_segment.block_id}, Position in Segment: {train.segment_displacement}")
    train.move(500)
    print(f"Current Segment: {train.current_segment.block_id}, Position in Segment: {train.segment_displacement}")